"""Ticket queue and lifecycle actions."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import t, use_lang
from core.notifications import notify
from manager_bot import keyboards as kb, states, ui
from manager_bot.util import answer, manager_only, safe_edit, send_attachment, user_lang

STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In Progress",
    "resolved": "Resolved",
    "closed": "Closed",
}


async def _send_detail(update: Update, ticket: dict) -> None:
    text, markup = await ui.render_ticket_detail(ticket)
    chat_id = update.effective_chat.id
    await update.effective_message.reply_text(text, reply_markup=markup, parse_mode="HTML")
    await send_attachment(
        update.get_bot(), chat_id, ticket.get("screenshot_path"), t("Screenshot")
    )


@manager_only
async def queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_tickets_queue()
    await safe_edit(query, text, markup)


@manager_only
async def view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ticket_id = int(query.data.rsplit(":", 1)[-1])
    ticket = await q.get_ticket(ticket_id)
    if ticket is None:
        await answer(query, t("Ticket not found."))
        return
    await answer(query)
    await _send_detail(update, ticket)


@manager_only
async def set_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    ticket_id = int(parts[2])
    status = parts[3]
    ticket = await q.get_ticket(ticket_id)
    if ticket is None:
        await answer(query, t("Ticket not found."))
        return
    await q.set_ticket_status(ticket_id, status, assigned_to=update.effective_user.id)
    label = STATUS_LABELS.get(status, status)
    lang = await user_lang(int(ticket["telegram_id"]))
    with use_lang(lang):
        await q.add_ticket_message(
            ticket_id, "system", body=t("Status changed to {status}.", status=t(label))
        )
        await notify(
            int(ticket["telegram_id"]),
            "ticket_update",
            t("Ticket #{public_id} {status}", public_id=ticket["public_id"], status=t(label)),
            t("Your ticket status is now {status}.", status=t(label)),
            ticket_id=ticket_id,
            dedupe_key=f"ticket:{ticket_id}:{status}",
        )
    await answer(query, t("Ticket {status}.", status=t(label)))
    ticket = await q.get_ticket(ticket_id)
    text, markup = await ui.render_ticket_detail(ticket)
    await safe_edit(query, text, markup)


@manager_only
async def reply_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ticket_id = int(query.data.rsplit(":", 1)[-1])
    ticket = await q.get_ticket(ticket_id)
    if ticket is None:
        await answer(query, t("Ticket not found."))
        return
    await answer(query)
    states.set_state(update.effective_user.id, "ticket_reply", ticket_id=ticket_id)
    await query.message.reply_text(
        t("💬 Send the reply to the user, or /cancel."), reply_markup=kb.cancel()
    )


@manager_only
async def custom_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ticket_id = int(query.data.rsplit(":", 1)[-1])
    ticket = await q.get_ticket(ticket_id)
    if ticket is None:
        await answer(query, t("Ticket not found."))
        return
    await answer(query)
    states.set_state(update.effective_user.id, "ticket_custom", ticket_id=ticket_id)
    await query.message.reply_text(
        t("✏️ Send a custom message to the user, or /cancel."), reply_markup=kb.cancel()
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, text: str) -> bool:
    action = state.get("action")
    if action not in {"ticket_reply", "ticket_custom"}:
        return False
    admin_id = update.effective_user.id
    ticket = await q.get_ticket(int(state.get("ticket_id", 0)))
    if ticket is None:
        states.clear_state(admin_id)
        await update.message.reply_text(t("Ticket not found."))
        return True

    await q.add_ticket_message(int(ticket["id"]), "admin", sender_id=admin_id, body=text.strip())
    if action == "ticket_reply":
        await q.set_ticket_status(int(ticket["id"]), "in_progress", assigned_to=admin_id)
    await q.add_audit(
        admin_id, action, "ticket", str(ticket["id"]), payload_after={"text": text}
    )
    with use_lang(await user_lang(int(ticket["telegram_id"]))):
        if action == "ticket_reply":
            title = t("Reply on ticket #{public_id}", public_id=ticket["public_id"])
        else:
            title = t("Message about ticket #{public_id}", public_id=ticket["public_id"])
        await notify(
            int(ticket["telegram_id"]),
            "ticket_reply" if action == "ticket_reply" else "custom_msg",
            title,
            text.strip(),
            ticket_id=int(ticket["id"]),
        )
    states.clear_state(admin_id)
    await update.message.reply_text(
        t("✅ Sent via ticket #{public_id}.", public_id=ui.esc(ticket["public_id"])),
        parse_mode="HTML",
    )
    return True


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(queue, pattern=r"^tickets:queue$"))
    application.add_handler(CallbackQueryHandler(view, pattern=r"^ticket:view:\d+$"))
    application.add_handler(CallbackQueryHandler(set_status, pattern=r"^ticket:status:\d+:(open|in_progress|resolved|closed)$"))
    application.add_handler(CallbackQueryHandler(reply_prompt, pattern=r"^ticket:reply:\d+$"))
    application.add_handler(CallbackQueryHandler(custom_prompt, pattern=r"^ticket:custom:\d+$"))
