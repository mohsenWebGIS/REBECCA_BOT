"""Per-update language context for the user bot."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.db import queries as q
from core.i18n import normalize_lang, set_lang


async def attach_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        set_lang("en")
        return
    db_user = await q.get_user(user.id)
    if db_user is None:
        detected = normalize_lang(user.language_code)
        db_user = await q.upsert_user(
            user.id, user.username, user.full_name, preferred_lang=detected
        )
    set_lang((db_user or {}).get("preferred_lang") or "en")
    await q.touch_user(user.id)


__all__ = ["attach_language"]
