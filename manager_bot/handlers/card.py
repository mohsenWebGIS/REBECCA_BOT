"""Payment card settings, access requests, and user grants."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import t
from core.services.payment_card import (
    CARD_HOLDER_KEY,
    CARD_MODE_KEY,
    CARD_NUMBER_KEY,
    MODES,
    card_digits,
    notify_user_card_approved,
    notify_user_card_rejected,
    valid_card_number,
)
from manager_bot import keyboards as kb, states, ui
from manager_bot.util import answer, manager_only, safe_edit


@manager_only
async def open_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_card_menu()
    await safe_edit(query, text, markup)


@manager_only
async def edit_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    states.set_state(update.effective_user.id, "card_number")
    await query.message.reply_text(
        t("💳 Send the new 16-digit card number, or /cancel."),
        reply_markup=kb.cancel(),
    )


@manager_only
async def edit_holder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    states.set_state(update.effective_user.id, "card_holder")
    await query.message.reply_text(
        t("👤 Send the card holder name, or /cancel."),
        reply_markup=kb.cancel(),
    )


@manager_only
async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    mode = query.data.rsplit(":", 1)[-1]
    if mode not in MODES:
        await answer(query, t("Invalid card mode."))
        return
    await q.set_meta(CARD_MODE_KEY, mode)
    await q.add_audit(
        update.effective_user.id,
        "card_mode",
        "payment_card",
        mode,
        payload_after={"mode": mode},
    )
    await answer(query, t("Card mode updated."))
    text, markup = await ui.render_card_menu()
    await safe_edit(query, text, markup)


@manager_only
async def requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_card_requests()
    await safe_edit(query, text, markup)


@manager_only
async def request_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    await answer(query)
    text, markup = await ui.render_card_request(telegram_id)
    await safe_edit(query, text, markup)


@manager_only
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    admin_id = update.effective_user.id
    await q.set_card_access(telegram_id, "approved", admin_id)
    await q.add_audit(admin_id, "card_approve", "user", str(telegram_id))
    await notify_user_card_approved(telegram_id)
    await answer(query, t("Card access approved."))
    text, markup = await ui.render_card_requests()
    await safe_edit(query, text, markup)


@manager_only
async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    admin_id = update.effective_user.id
    await q.set_card_access(telegram_id, "rejected", admin_id)
    await q.add_audit(admin_id, "card_reject", "user", str(telegram_id))
    await notify_user_card_rejected(telegram_id)
    await answer(query, t("Card request rejected."))
    text, markup = await ui.render_card_requests()
    await safe_edit(query, text, markup)


async def handle_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, text: str
) -> bool:
    action = state.get("action")
    if action not in {"card_number", "card_holder"}:
        return False
    admin_id = update.effective_user.id
    if action == "card_number":
        if not valid_card_number(text):
            await update.message.reply_text(t("Send a valid 16-digit card number."))
            return True
        number = card_digits(text)
        await q.set_meta(CARD_NUMBER_KEY, number)
        await q.add_audit(
            admin_id,
            "card_number",
            "payment_card",
            number[-4:],
            payload_after={"last4": number[-4:]},
        )
        states.clear_state(admin_id)
        body, markup = await ui.render_card_menu()
        await update.message.reply_text(
            t("✅ Card number updated.") + "\n\n" + body,
            reply_markup=markup,
            parse_mode="HTML",
        )
        return True
    holder = " ".join(text.split())
    if not holder or len(holder) > 80:
        await update.message.reply_text(t("Send a valid card holder name."))
        return True
    await q.set_meta(CARD_HOLDER_KEY, holder)
    await q.add_audit(
        admin_id,
        "card_holder",
        "payment_card",
        None,
        payload_after={"holder": holder},
    )
    states.clear_state(admin_id)
    body, markup = await ui.render_card_menu()
    await update.message.reply_text(
        t("✅ Card holder updated.") + "\n\n" + body,
        reply_markup=markup,
        parse_mode="HTML",
    )
    return True


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(open_menu, pattern=r"^card:menu$"))
    application.add_handler(CallbackQueryHandler(edit_number, pattern=r"^card:edit:number$"))
    application.add_handler(CallbackQueryHandler(edit_holder, pattern=r"^card:edit:holder$"))
    application.add_handler(CallbackQueryHandler(set_mode, pattern=r"^card:mode:(all|request|none)$"))
    application.add_handler(CallbackQueryHandler(requests, pattern=r"^card:requests$"))
    application.add_handler(CallbackQueryHandler(request_view, pattern=r"^card:request:\d+$"))
    application.add_handler(CallbackQueryHandler(approve, pattern=r"^card:approve:\d+$"))
    application.add_handler(CallbackQueryHandler(reject, pattern=r"^card:reject:\d+$"))
