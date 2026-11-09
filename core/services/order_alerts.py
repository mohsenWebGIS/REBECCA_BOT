"""Immediate manager alerts for payment receipts awaiting review."""
from __future__ import annotations

import json
import logging
from typing import Any

from core.config import settings
from core.db import queries as q
from core.i18n import format_number, format_toman, normalize_lang, t, use_lang
from core.notifications import notify

logger = logging.getLogger(__name__)


def _plan_name(order: dict[str, Any]) -> str:
    raw = order.get("plan_snapshot")
    snapshot: Any = raw
    if isinstance(raw, str):
        try:
            snapshot = json.loads(raw)
        except (ValueError, TypeError):
            snapshot = None
    if isinstance(snapshot, dict):
        return str(snapshot.get("name") or snapshot.get("plan_name") or "—")
    return "—"


def _manager_targets() -> list[int]:
    ids = list(settings.manager_id_list)
    if settings.manager_group_id:
        ids.append(int(settings.manager_group_id))
    return list(dict.fromkeys(ids))


async def _manager_lang(chat_id: int) -> str:
    lang = await q.get_manager_lang(chat_id)
    if settings.manager_group_id and chat_id == int(settings.manager_group_id):
        return normalize_lang(lang) if lang else "fa"
    return normalize_lang(lang) if lang else "en"


async def notify_managers_pending_order(
    order: dict[str, Any],
    *,
    resend: bool = False,
    receipt_index: int = 1,
) -> None:
    user = await q.get_user(int(order["telegram_id"]))
    username = (user or {}).get("username") or "—"
    plan = _plan_name(order)
    order_id = int(order["id"])
    public_id = str(order["public_id"])
    dedupe = (
        f"receipt:{order_id}:{receipt_index}"
        if resend
        else f"new_order:{order_id}"
    )
    notification_type = "order_new_receipt" if resend else "new_order"
    renewal = order.get("kind") == "renewal"

    for chat_id in _manager_targets():
        try:
            with use_lang(await _manager_lang(chat_id)):
                if resend:
                    title = t("🧾 New receipt for #{public_id}", public_id=public_id)
                elif renewal:
                    title = t("🔄 Renewal receipt")
                else:
                    title = t("💳 New payment receipt")
                body = t(
                    "Order #{public_id}\nUser: @{username} ({uid})\nPlan: {plan}\nAmount: {amount}\n\nReview and approve or reject it.",
                    public_id=public_id,
                    username=username,
                    uid=format_number(int(order["telegram_id"])),
                    plan=plan,
                    amount=format_toman(order.get("final_price") or 0),
                )
                if renewal and order.get("subscription_id"):
                    body += "\n" + t(
                        "Renewal for subscription #{sub_id}",
                        sub_id=format_number(order["subscription_id"]),
                    )
                await notify(
                    chat_id,
                    notification_type,
                    title,
                    body,
                    order_id=order_id,
                    dedupe_key=dedupe,
                )
        except Exception:
            logger.exception("failed to queue order alert for %s", chat_id)


__all__ = ["notify_managers_pending_order"]
