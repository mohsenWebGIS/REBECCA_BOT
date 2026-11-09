"""Per-update language context for the manager bot."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.db import queries as q
from core.i18n import normalize_lang, set_lang
from manager_bot.util import is_manager


async def attach_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or not is_manager(user.id):
        set_lang("en")
        return
    lang = await q.get_manager_lang(user.id)
    set_lang(normalize_lang(lang) if lang else "en")


__all__ = ["attach_language"]
