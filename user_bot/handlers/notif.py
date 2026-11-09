"""Notifications inbox, detail, mark-all-read and mute toggle."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import t
from user_bot import ui
from user_bot.handlers.util import answer, safe_edit


async def show_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    text, markup = await ui.render_notifications(update.effective_user.id)
    await safe_edit(query, text, markup)


async def show_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    notification_id = int(query.data.rsplit(":", 1)[-1])
    notif = await q.get_notification(notification_id)
    if notif is None or int(notif["telegram_id"]) != update.effective_user.id:
        await answer(query, t("Notification not found."))
        return
    await q.mark_notification_read(notification_id)
    await answer(query)
    text, markup = ui.render_notification(notif)
    await safe_edit(query, text, markup)


async def mark_all_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await q.mark_all_read(update.effective_user.id)
    await answer(query, t("Marked all as read."))
    text, markup = await ui.render_notifications(update.effective_user.id)
    await safe_edit(query, text, markup)


async def toggle_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    user = await q.get_user(update.effective_user.id)
    muted = bool(user and user.get("mute_broadcasts"))
    await q.set_user_muted(update.effective_user.id, not muted)
    await answer(query, t("Broadcasts muted." if not muted else "Broadcasts unmuted."))
    text, markup = await ui.render_notifications(update.effective_user.id)
    await safe_edit(query, text, markup)


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(show_inbox, pattern=r"^notif:list$"))
    application.add_handler(CallbackQueryHandler(show_detail, pattern=r"^notif:view:\d+$"))
    application.add_handler(CallbackQueryHandler(mark_all_read, pattern=r"^notif:readall$"))
    application.add_handler(CallbackQueryHandler(toggle_mute, pattern=r"^notif:mute$"))
