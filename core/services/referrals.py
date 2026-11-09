"""Invitation codes and referral traffic bonuses."""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import settings
from core.db import queries as q
from core.i18n import format_gb, normalize_lang, t, use_lang
from core.notifications import notify
from core.rebecca_api import GB, RebeccaClient

logger = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
_credit_lock = asyncio.Lock()


def normalize_code(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


async def ensure_invite_code(telegram_id: int) -> Optional[str]:
    user = await q.get_user(telegram_id)
    if user is None:
        return None
    code = normalize_code(user.get("invite_code"))
    if code:
        return code
    for _ in range(20):
        candidate = _generate_code()
        if await q.get_user_by_invite_code(candidate) is None:
            await q.update_user(telegram_id, invite_code=candidate)
            return candidate
    raise RuntimeError("could not allocate invite code")


async def validate_invite_code(
    code: Any, invitee_id: int
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    normalized = normalize_code(code)
    if not normalized:
        return None, "Invalid invitation code."
    inviter = await q.get_user_by_invite_code(normalized)
    if inviter is None:
        return None, "Invalid invitation code."
    if int(inviter["telegram_id"]) == int(invitee_id):
        return None, "You cannot use your own invitation code."
    if await q.user_has_purchase_history(invitee_id):
        return None, "Invitation codes are only for first purchases."
    if await q.get_active_referral_for_invitee(invitee_id) is not None:
        return None, "You have already used an invitation code."
    return inviter, None


def bonus_for_plan(plan_gb: Any) -> float:
    percent = max(0.0, float(settings.referral_bonus_percent or 0.0))
    return round(max(0.0, float(plan_gb or 0)) * percent / 100.0, 2)


async def record_referral(
    order_id: int,
    invitee_id: int,
    code: Any,
    plan_gb: float,
) -> Optional[int]:
    inviter, _reason = await validate_invite_code(code, invitee_id)
    if inviter is None:
        return None
    normalized = normalize_code(code)
    return await q.create_referral(
        order_id=order_id,
        inviter_id=int(inviter["telegram_id"]),
        invitee_id=int(invitee_id),
        invite_code=normalized,
        plan_gb=float(plan_gb),
        bonus_gb=bonus_for_plan(plan_gb),
    )


def _parse_expiry(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _pick_active_subscription(subs: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    for sub in subs:
        if (sub.get("status") or "").lower() != "active":
            continue
        expires = _parse_expiry(sub.get("expires_at"))
        if expires is not None and expires <= now:
            continue
        return sub
    return None


def _sub_name(sub: dict[str, Any]) -> str:
    return (
        sub.get("display_name")
        or sub.get("plan_name")
        or sub.get("rebecca_username")
        or "subscription"
    )


async def _notify_inviter(
    inviter_id: int, bonus_gb: float, sub: dict[str, Any], order_id: int
) -> None:
    inviter = await q.get_user(inviter_id)
    lang = normalize_lang(inviter.get("preferred_lang") if inviter else "en")
    with use_lang(lang):
        await notify(
            inviter_id,
            "referral_credit",
            t("🎉 Referral bonus: +{gb}", gb=format_gb(bonus_gb)),
            t("Added to subscription {name}.", name=_sub_name(sub)),
            dedupe_key=f"referral_credit:{order_id}",
        )


async def credit_referral_for_order(order_id: int, client: RebeccaClient) -> str:
    async with _credit_lock:
        referral = await q.get_referral_by_order(order_id)
        if referral is None or referral.get("status") != "pending":
            return "skipped"
        order = await q.get_order(order_id)
        if order is None or order.get("status") != "approved":
            return "not_approved"
        subs = await q.list_subscriptions_for_user(int(referral["inviter_id"]))
        target = _pick_active_subscription(subs)
        if target is None:
            return "no_subscription"
        try:
            data = await client.get_user(target["rebecca_username"])
            if not data:
                return "missing_panel_user"
            current = int(data.get("data_limit") or 0)
            bonus_bytes = int(round(float(referral["bonus_gb"]) * GB))
            new_limit = current + bonus_bytes
            await client.update_user(
                target["rebecca_username"], data_limit=new_limit
            )
        except Exception:
            logger.exception(
                "referral credit failed for order %s (inviter %s)",
                order_id,
                referral["inviter_id"],
            )
            return "error"
        await q.update_subscription(
            int(target["id"]), traffic_total_gb=new_limit / GB
        )
        await q.set_referral_status(
            int(referral["id"]), "credited", int(target["id"])
        )
        await _notify_inviter(
            int(referral["inviter_id"]),
            float(referral["bonus_gb"]),
            target,
            order_id,
        )
        return "credited"


async def referral_stats(inviter_id: int) -> dict[str, Any]:
    stats = {
        "total": 0,
        "pending": 0,
        "credited": 0,
        "cancelled": 0,
        "total_bonus_gb": 0.0,
    }
    for row in await q.referral_stats(inviter_id):
        status = str(row.get("status") or "unknown")
        count = int(row.get("n") or 0)
        if status != "cancelled":
            stats["total"] += count
        stats[status] = stats.get(status, 0) + count
        if status == "credited":
            stats["total_bonus_gb"] += float(row.get("total") or 0)
    return stats


__all__ = [
    "normalize_code",
    "ensure_invite_code",
    "validate_invite_code",
    "bonus_for_plan",
    "record_referral",
    "credit_referral_for_order",
    "referral_stats",
]
