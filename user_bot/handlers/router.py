"""Single entry point for free-text and media messages routed by FSM state."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from core.i18n import t
from user_bot import states, ui
from user_bot.handlers import ai, buy, subs, tickets


async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    flow = states.get_flow(uid)
    if flow == states.FLOW_PROMO:
        await buy.on_promo_text(update, context)
    elif flow == states.FLOW_TICKET_DESC:
        await tickets.on_desc_text(update, context)
    elif flow == states.FLOW_TICKET_REPLY:
        await tickets.on_reply_text(update, context)
    elif flow == states.FLOW_RECEIPT:
        await buy.on_receipt_text(update, context)
    elif flow == states.FLOW_SUB_RENAME:
        await subs.on_name_text(update, context)
    elif flow == states.FLOW_TRANSFER:
        await subs.on_transfer_text(update, context)
    elif flow == states.FLOW_INVITE:
        await buy.on_invite_text(update, context)
    elif flow == states.FLOW_AI:
        await ai.on_chat_text(update, context)
    else:
        text, markup = await ui.render_main_menu(uid)
        await update.message.reply_text(
            t("Use the buttons below to navigate.\n\n{menu}", menu=text),
            reply_markup=markup,
            parse_mode="HTML",
        )


async def route_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    flow = states.get_flow(update.effective_user.id)
    if flow == states.FLOW_RECEIPT:
        await buy.on_receipt_media(update, context)
    elif flow == states.FLOW_TICKET_DESC:
        await tickets.on_desc_media(update, context)
    else:
        await update.message.reply_text(t("No upload expected right now. Use /start for the menu."))


def register(application: Application) -> None:
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, route_text)
    )
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.ALL, route_media)
    )
