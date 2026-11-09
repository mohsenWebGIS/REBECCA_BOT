"""Manager-bot helpers: authorization gate, formatting and attachment sending."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from telegram import CallbackQuery, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from core.config import settings
from core.db import queries as q
from core.i18n import format_number, format_toman, normalize_lang, t
from core.rebecca_api import RebeccaClient

F = TypeVar("F", bound=Callable[..., Any])


def is_manager(user_id: Optional[int]) -> bool:
    return user_id is not None and user_id in settings.manager_id_list


def manager_only(func: F) -> F:
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
        user = update.effective_user
        if not is_manager(user.id if user else None):
            if update.callback_query is not None:
                await answer(update.callback_query, t("Not authorized."))
            elif update.message is not None:
                await update.message.reply_text(t("⛔ Not authorized."))
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def client(context: ContextTypes.DEFAULT_TYPE) -> RebeccaClient:
    return context.application.bot_data["rebecca"]


async def answer(query: CallbackQuery, text: Optional[str] = None, alert: bool = False) -> None:
    try:
        await query.answer(text=text, show_alert=alert)
    except BadRequest:
        pass


async def safe_edit(
    query: CallbackQuery,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
    *,
    disable_preview: bool = True,
) -> None:
    kwargs: dict[str, Any] = {"parse_mode": "HTML", "reply_markup": markup}
    if disable_preview:
        kwargs["disable_web_page_preview"] = True
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest:
        if query.message is not None:
            await query.message.reply_text(text, **kwargs)


def fmt_money(value: Any) -> str:
    try:
        return format_toman(float(value))
    except (TypeError, ValueError):
        return format_toman(0)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def rel_time(value: Optional[str]) -> str:
    dt = parse_dt(value)
    if dt is None:
        return t("unknown")
    delta = datetime.now(timezone.utc) - dt
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return t("{minutes}m ago", minutes=format_number(max(minutes, 0)))
    hours = minutes // 60
    if hours < 24:
        return t("{hours}h ago", hours=format_number(hours))
    return t("{days}d ago", days=format_number(hours // 24))


def age_minutes(value: Optional[str]) -> int:
    dt = parse_dt(value)
    if dt is None:
        return 0
    return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))


async def user_lang(telegram_id: int) -> str:
    user = await q.get_user(telegram_id)
    return normalize_lang(user.get("preferred_lang") if user else "en")


def age_dot(minutes: int) -> str:
    if minutes < 30:
        return "🟢"
    if minutes < 120:
        return "🟡"
    return "🔴"


async def send_attachment(bot: Any, chat_id: int, path: Optional[str], caption: str) -> None:
    if not path or not os.path.exists(path):
        await bot.send_message(
            chat_id=chat_id,
            text=t("⚠️ {caption}: file not found ({path})", caption=caption, path=path),
        )
        return
    ext = path.lower().rsplit(".", 1)[-1]
    with open(path, "rb") as handle:
        if ext == "pdf":
            await bot.send_document(chat_id=chat_id, document=handle, caption=caption)
        else:
            await bot.send_photo(chat_id=chat_id, photo=handle, caption=caption)


__all__ = [
    "is_manager", "manager_only", "client", "answer", "safe_edit", "fmt_money",
    "parse_dt", "rel_time", "age_minutes", "age_dot", "send_attachment", "user_lang",
]
