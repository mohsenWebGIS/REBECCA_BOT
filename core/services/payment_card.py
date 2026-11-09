"""Payment card configuration, visibility rules, and notifications."""
from __future__ import annotations

from typing import Any, Optional

from core.config import settings
from core.db import queries as q
from core.i18n import format_number, normalize_lang, t, use_lang
from core.notifications import notify

CARD_NUMBER_KEY = "payment_card_number"
CARD_HOLDER_KEY = "payment_card_holder"
CARD_MODE_KEY = "payment_card_mode"

MODES = ("all", "request", "none")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def card_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "").translate(_DIGITS) if ch.isdigit())


def grouped_card(digits: str) -> str:
    return " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))


def valid_card_number(value: Any) -> bool:
    return len(card_digits(value)) == 16


async def get_card_config() -> dict[str, Any]:
    stored_number = await q.get_meta(CARD_NUMBER_KEY)
    stored_holder = await q.get_meta(CARD_HOLDER_KEY)
    stored_mode = await q.get_meta(CARD_MODE_KEY)

    number = card_digits(
        stored_number if stored_number is not None else settings.payment_card_number
    )
    holder = " ".join(
        str(
            stored_holder
            if stored_holder is not None
            else (settings.payment_card_holder or "")
        ).split()
    )
    mode = (stored_mode or "request").strip().lower()
    if mode not in MODES:
        mode = "request"
    return {"number": number, "holder": holder, "mode": mode}


async def card_state(telegram_id: int) -> dict[str, Any]:
    config = await get_card_config()
    access = await q.get_card_access(telegram_id)
    status = (access or {}).get("status")
    approved = status == "approved"
    pending = status == "pending"
    history = False
    if config["mode"] == "request" and not approved:
        history = await q.user_has_purchase_history(telegram_id)
    show = bool(config["number"]) and (
        config["mode"] == "all" or approved or history
    )
    allow_request = (
        bool(config["number"])
        and config["mode"] == "request"
        and not show
        and not pending
    )
    return {
        **config,
        "access": dict(access) if access is not None else None,
        "status": status,
        "show": show,
        "pending": pending,
        "approved": approved,
        "allow_request": allow_request,
    }


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


async def _user_lang(telegram_id: int) -> str:
    user = await q.get_user(telegram_id)
    return normalize_lang(user.get("preferred_lang") if user else "en")


async def notify_managers_card_request(telegram_id: int, username: Optional[str]) -> None:
    name = username or "—"
    for chat_id in _manager_targets():
        with use_lang(await _manager_lang(chat_id)):
            await notify(
                chat_id,
                "card_request",
                t("💳 Card number request"),
                t(
                    "User {uid} (@{username}) requested the payment card.",
                    uid=format_number(telegram_id),
                    username=name,
                ),
            )


async def notify_user_card_approved(telegram_id: int) -> None:
    with use_lang(await _user_lang(telegram_id)):
        await notify(
            telegram_id,
            "card_approved",
            t("💳 Card number available"),
            t("Open the payment page to see the card number."),
        )


async def notify_user_card_rejected(telegram_id: int) -> None:
    with use_lang(await _user_lang(telegram_id)):
        await notify(
            telegram_id,
            "card_rejected",
            t("💳 Card request rejected"),
            t("Contact support if you need help."),
        )


__all__ = [
    "CARD_NUMBER_KEY",
    "CARD_HOLDER_KEY",
    "CARD_MODE_KEY",
    "MODES",
    "card_digits",
    "grouped_card",
    "valid_card_number",
    "get_card_config",
    "card_state",
    "notify_managers_card_request",
    "notify_user_card_approved",
    "notify_user_card_rejected",
]
