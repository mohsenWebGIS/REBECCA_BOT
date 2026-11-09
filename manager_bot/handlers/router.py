"""Route pending-text input to the handler that owns the current state."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from core.i18n import t
from manager_bot import states
from manager_bot.handlers import broadcast, card, discounts, orders, tickets, users
from manager_bot.util import is_manager

MODULES = (card, orders, tickets, users, discounts, broadcast)


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if not is_manager(update.effective_user.id):
        await update.message.reply_text(t("⛔ Not authorized."))
        return
    state = states.get_state(update.effective_user.id)
    if not state:
        await update.message.reply_text(t("Use /admin to open the manager menu."))
        return
    text = update.message.text or ""
    for module in MODULES:
        if await module.handle_text(update, context, state, text):
            return
    await update.message.reply_text(t("Unrecognized input. Use /cancel to abort."))


def register(application: Application) -> None:
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_text))
