"""Ticket creation, listing, thread view, reply and close."""
from __future__ import annotations

from typing import Optional

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from core.db import queries as q
from core.i18n import t
from core.services import tickets as ticket_svc
from user_bot import keyboards as kb, ratelimit, states, ui
from user_bot.handlers.util import answer, safe_edit, save_uploaded_file


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await answer(query)
    states.clear_state(update.effective_user.id)
    await safe_edit(
        query,
        t("🆘 Report an issue\n\nChoose a category:"),
        kb.ticket_categories(ui.CATEGORIES),
    )


async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    category = query.data.rsplit(":", 1)[-1]
    await answer(query)
    states.set_state(update.effective_user.id, states.FLOW_TICKET_DESC, category=category)
    await query.message.reply_text(
        t("Describe the issue, or /skip. You may attach a screenshot."),
        reply_markup=kb.cancel_only(),
    )


async def _finalize_ticket(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    category: str,
    description: Optional[str],
    screenshot_path: Optional[str],
    public_id: str,
) -> None:
    uid = update.effective_user.id
    if not ratelimit.allow(uid, "ticket", 5, 3600) or not ratelimit.allow(
        uid, "ticket_cooldown", 1, 60
    ):
        await update.message.reply_text(
            t("Too many requests. Please wait and try again later.")
        )
        return
    ticket_id = await q.create_ticket(
        public_id=public_id,
        telegram_id=uid,
        category=category,
        description=description,
        screenshot_path=screenshot_path,
        status="open",
    )
    if description or screenshot_path:
        await q.add_ticket_message(
            ticket_id,
            "user",
            sender_id=uid,
            body=description,
            file_path=screenshot_path,
        )
    await update.message.reply_text(ui.ticket_created_ack(public_id), parse_mode="HTML")
    states.clear_state(uid)


async def on_desc_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    state = states.get_state(update.effective_user.id)
    if state.get("flow") != states.FLOW_TICKET_DESC:
        return
    description = (update.message.text or "").strip() or None
    public_id = await ticket_svc.generate_public_id()
    await _finalize_ticket(update, context, state["category"], description, None, public_id)


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    state = states.get_state(update.effective_user.id)
    if state.get("flow") != states.FLOW_TICKET_DESC:
        await update.message.reply_text(t("Nothing to skip. Use /start to open the menu."))
        return
    public_id = await ticket_svc.generate_public_id()
    await _finalize_ticket(update, context, state["category"], None, None, public_id)


async def on_desc_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    state = states.get_state(update.effective_user.id)
    if state.get("flow") != states.FLOW_TICKET_DESC:
        return
    public_id = await ticket_svc.generate_public_id()
    path, error = await save_uploaded_file(context, update.message, "ticket", public_id, 1)
    if error or path is None:
        await update.message.reply_text(t(error or "Please send a screenshot (image)."))
        return
    description = (update.message.caption or "").strip() or None
    await _finalize_ticket(update, context, state["category"], description, path, public_id)


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await answer(query)
    text, markup = await ui.render_tickets_list(update.effective_user.id)
    await safe_edit(query, text, markup)


async def _owned_ticket(update: Update) -> Optional[dict]:
    query = update.callback_query
    ticket_id = int(query.data.rsplit(":", 1)[-1])
    ticket = await q.get_ticket(ticket_id)
    if ticket is None or int(ticket["telegram_id"]) != update.effective_user.id:
        await answer(query, t("Ticket not found."))
        return None
    return ticket


async def show_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ticket = await _owned_ticket(update)
    if ticket is None:
        return
    await answer(update.callback_query)
    text, markup = await ui.render_ticket_detail(ticket)
    await safe_edit(update.callback_query, text, markup)


async def reply_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ticket = await _owned_ticket(update)
    if ticket is None:
        return
    await answer(update.callback_query)
    states.set_state(
        update.effective_user.id, states.FLOW_TICKET_REPLY, ticket_id=int(ticket["id"])
    )
    await update.callback_query.message.reply_text(
        t("💬 Send your reply, or /cancel."),
        reply_markup=kb.cancel_only(),
    )


async def on_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    state = states.get_state(uid)
    if state.get("flow") != states.FLOW_TICKET_REPLY:
        return
    ticket = await q.get_ticket(int(state["ticket_id"]))
    if ticket is None or int(ticket["telegram_id"]) != uid:
        await update.message.reply_text(t("Ticket not found."))
        states.clear_state(uid)
        return
    await q.add_ticket_message(int(ticket["id"]), "user", sender_id=uid, body=update.message.text)
    await q.set_ticket_status(int(ticket["id"]), "in_progress")
    states.clear_state(uid)
    ticket = await q.get_ticket(int(ticket["id"]))
    text, markup = await ui.render_ticket_detail(ticket)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ticket = await _owned_ticket(update)
    if ticket is None:
        return
    await q.set_ticket_status(int(ticket["id"]), "closed")
    await q.add_ticket_message(int(ticket["id"]), "system", body=t("Ticket closed by user."))
    await answer(update.callback_query, t("Ticket closed."))
    ticket = await q.get_ticket(int(ticket["id"]))
    text, markup = await ui.render_ticket_detail(ticket)
    await safe_edit(update.callback_query, text, markup)


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(show_categories, pattern=r"^ticket:new$"))
    application.add_handler(CallbackQueryHandler(choose_category, pattern=r"^ticket:cat:.+$"))
    application.add_handler(CallbackQueryHandler(show_list, pattern=r"^tickets:list$"))
    application.add_handler(CallbackQueryHandler(show_detail, pattern=r"^ticket:view:\d+$"))
    application.add_handler(CallbackQueryHandler(reply_prompt, pattern=r"^ticket:reply:\d+$"))
    application.add_handler(CallbackQueryHandler(close_ticket, pattern=r"^ticket:close:\d+$"))
    application.add_handler(CommandHandler("skip", skip_description))
