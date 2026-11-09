"""Orders queue and the six order actions."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import format_number, parse_number, t, use_lang
from core.notifications import notify
from core.rebecca_api import RebeccaAPIError
from core.services import orders as order_sm
from core.services.provisioner import provision_sub_for_order, renew_sub_for_order
from core.services.referrals import credit_referral_for_order
from manager_bot import keyboards as kb, states, ui
from manager_bot.util import (
    answer, client, manager_only, safe_edit, send_attachment, user_lang,
)

logger = logging.getLogger(__name__)

REJECT_REASONS = {
    "unclear": "Receipt unclear",
    "mismatch": "Amount mismatch",
    "not_received": "Payment not received",
    "duplicate": "Duplicate",
    "fraud": "Suspected fraud",
}


async def _get_order(data: str, index: int = 1) -> Optional[dict]:
    order_id = int(data.split(":")[index])
    return await q.get_order(order_id)


async def _send_detail(update: Update, order: dict) -> None:
    text, markup = await ui.render_order_detail(order)
    chat_id = update.effective_chat.id
    await update.effective_message.reply_text(text, reply_markup=markup, parse_mode="HTML")
    await send_attachment(update.get_bot(), chat_id, order.get("receipt_path"), "Receipt")


@manager_only
async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_pending_orders()
    await safe_edit(query, text, markup)


@manager_only
async def view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    await _send_detail(update, order)


@manager_only
async def approve_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    text, markup = ui.render_approve_confirm(order, float(order.get("final_price") or 0))
    await safe_edit(query, text, markup)


@manager_only
async def edit_price_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    states.set_state(update.effective_user.id, "edit_price", order_id=int(order["id"]))
    await query.message.reply_text(
        t("✏️ Send the new final price in Toman (e.g. 288000), or /cancel."),
        reply_markup=kb.cancel(),
    )


async def _approve(update: Update, context: ContextTypes.DEFAULT_TYPE, order: dict) -> None:
    admin_id = update.effective_user.id
    renewal = order.get("kind") == "renewal"
    try:
        if renewal:
            sub = await renew_sub_for_order(order, client=client(context))
        else:
            sub = await provision_sub_for_order(order, client=client(context))
    except RebeccaAPIError as exc:
        await update.effective_message.reply_text(
            t(
                "⚠️ Provisioning failed: {status} {detail}\nOrder status unchanged. You can retry.",
                status=exc.status,
                detail=ui.esc(exc.text[:200]),
            ),
            reply_markup=kb.retry_order(int(order["id"])),
            parse_mode="HTML",
        )
        return

    await q.update_order(
        int(order["id"]),
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        reviewer_id=admin_id,
    )
    await q.add_audit(
        admin_id, "approve_order", "order", str(order["id"]),
        payload_before={"status": order["status"]},
        payload_after={"status": "approved", "sub_id": sub["id"]},
    )
    try:
        await credit_referral_for_order(int(order["id"]), client(context))
    except Exception:
        logger.exception("referral credit failed for order %s", order["id"])
    with use_lang(await user_lang(int(order["telegram_id"]))):
        if renewal:
            body = t(
                "Your subscription was renewed. Plan: {plan}.\nExpires: {expires}",
                plan=sub.get("plan_name"),
                expires=sub.get("expires_at") or t("n/a"),
            )
        else:
            body = t(
                "Your subscription is ready. Plan: {plan}.\n{url}",
                plan=sub.get("plan_name"),
                url=sub.get("subscription_url") or "",
            )
        await notify(
            int(order["telegram_id"]),
            "order_renewed" if renewal else "order_approved",
            t("Order #{public_id} approved", public_id=order["public_id"]),
            body,
            order_id=int(order["id"]),
            sub_id=int(sub["id"]),
            dedupe_key=f"approved:{order['id']}",
        )
    await update.effective_message.reply_text(
        t(
            "✅ Order #{public_id} approved · sub #{sub_id} renewed."
            if renewal
            else "✅ Order #{public_id} approved · sub #{sub_id} provisioned.",
            public_id=ui.esc(order["public_id"]),
            sub_id=format_number(sub["id"]),
        ),
        parse_mode="HTML",
    )
    states.clear_state(admin_id)


@manager_only
async def approve_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query, t("Provisioning…"))
    await _approve(update, context, order)


@manager_only
async def reject_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    text, markup = ui.render_reject_reasons(order)
    await safe_edit(query, text, markup)


async def _reject(update: Update, context: ContextTypes.DEFAULT_TYPE, order: dict, reason: str) -> None:
    admin_id = update.effective_user.id
    await q.update_order(
        int(order["id"]),
        status=order_sm.REJECTED,
        reject_reason=reason,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        reviewer_id=admin_id,
    )
    await q.cancel_referral_for_order(int(order["id"]))
    await q.add_audit(
        admin_id, "reject_order", "order", str(order["id"]),
        payload_before={"status": order["status"]},
        payload_after={"status": "rejected", "reason": reason},
    )
    with use_lang(await user_lang(int(order["telegram_id"]))):
        await notify(
            int(order["telegram_id"]),
            "order_rejected",
            t("Order #{public_id} rejected", public_id=order["public_id"]),
            t("Reason: {reason}", reason=t(reason)),
            order_id=int(order["id"]),
            dedupe_key=f"rejected:{order['id']}",
        )
    await update.effective_message.reply_text(
        t(
            "❌ Order #{public_id} rejected: {reason}",
            public_id=ui.esc(order["public_id"]),
            reason=ui.esc(t(reason)),
        ),
        parse_mode="HTML",
    )
    states.clear_state(admin_id)


@manager_only
async def reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    order = await q.get_order(int(parts[2]))
    reason = REJECT_REASONS.get(parts[3], parts[3])
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    await _reject(update, context, order, reason)


@manager_only
async def reject_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    states.set_state(update.effective_user.id, "reject_reason", order_id=int(order["id"]))
    await query.message.reply_text(
        t("✏️ Send the rejection reason, or /cancel."), reply_markup=kb.cancel()
    )


@manager_only
async def resend_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    text, markup = ui.render_resend(order)
    await safe_edit(query, text, markup)


async def _resend(update: Update, context: ContextTypes.DEFAULT_TYPE, order: dict, message: str) -> None:
    admin_id = update.effective_user.id
    await q.update_order(int(order["id"]), status=order_sm.NEEDS_RESEND)
    await q.add_audit(
        admin_id, "ask_resend", "order", str(order["id"]),
        payload_before={"status": order["status"]},
        payload_after={"status": "needs_resend", "message": message},
    )
    with use_lang(await user_lang(int(order["telegram_id"]))):
        await notify(
            int(order["telegram_id"]),
            "order_resend",
            t("New receipt needed for #{public_id}", public_id=order["public_id"]),
            message,
            order_id=int(order["id"]),
            dedupe_key=f"resend:{order['id']}:{datetime.now(timezone.utc).timestamp():.0f}",
        )
    await update.effective_message.reply_text(
        t("📸 Resend requested for #{public_id}.", public_id=ui.esc(order["public_id"])),
        parse_mode="HTML",
    )
    states.clear_state(admin_id)


@manager_only
async def resend_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    await _resend(update, context, order, ui.RESEND_DEFAULT)


@manager_only
async def resend_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    states.set_state(update.effective_user.id, "resend_msg", order_id=int(order["id"]))
    await query.message.reply_text(
        t("✏️ Send the resend message text, or /cancel."), reply_markup=kb.cancel()
    )


@manager_only
async def custom_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    states.set_state(update.effective_user.id, "custom_msg", order_id=int(order["id"]))
    await query.message.reply_text(
        t("✏️ Send the message to the user, or /cancel."), reply_markup=kb.cancel()
    )


@manager_only
async def internal_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    states.set_state(update.effective_user.id, "internal_note", order_id=int(order["id"]))
    await query.message.reply_text(
        t("📝 Send the internal note, or /cancel."), reply_markup=kb.cancel()
    )


@manager_only
async def under_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await q.update_order(int(order["id"]), status=order_sm.UNDER_REVIEW)
    await q.add_audit(
        update.effective_user.id, "under_review", "order", str(order["id"]),
        payload_before={"status": order["status"]},
        payload_after={"status": "under_review"},
    )
    await answer(query, t("Marked under review."))
    order = await q.get_order(int(order["id"]))
    text, markup = await ui.render_order_detail(order)
    await safe_edit(query, text, markup)


@manager_only
async def previous_receipts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    order = await _get_order(query.data, 2)
    if order is None:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    text, markup = await ui.render_previous_receipts(order)
    await safe_edit(query, text, markup)


@manager_only
async def show_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    order = await q.get_order(int(parts[2]))
    index = int(parts[3])
    if order is None:
        await answer(query, t("Order not found."))
        return
    try:
        history = json.loads(order.get("receipt_history") or "[]")
    except (ValueError, TypeError):
        history = []
    if index >= len(history):
        await answer(query, t("Receipt not found."))
        return
    await answer(query)
    await send_attachment(update.get_bot(), update.effective_chat.id, history[index], f"Receipt {index + 1}")


ORDER_TEXT_ACTIONS = {"edit_price", "reject_reason", "resend_msg", "custom_msg", "internal_note"}


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, text: str) -> bool:
    action = state.get("action")
    if action not in ORDER_TEXT_ACTIONS:
        return False
    admin_id = update.effective_user.id
    order = await q.get_order(int(state.get("order_id", 0)))
    if order is None:
        states.clear_state(admin_id)
        await update.message.reply_text(t("Order not found."))
        return True

    if action == "edit_price":
        parsed = parse_number(text)
        if parsed is None:
            await update.message.reply_text(t("Send a number, e.g. 288000."))
            return True
        price = float(parsed)
        await q.update_order(int(order["id"]), final_price=round(price, 2))
        order = await q.get_order(int(order["id"]))
        await q.add_audit(
            admin_id, "edit_price", "order", str(order["id"]),
            payload_after={"final_price": price},
        )
        states.clear_state(admin_id)
        body, markup = ui.render_approve_confirm(order, float(order["final_price"] or 0))
        await update.message.reply_text(body, reply_markup=markup, parse_mode="HTML")
        return True
    if action == "reject_reason":
        states.clear_state(admin_id)
        await _reject(update, context, order, text.strip())
        return True
    if action == "resend_msg":
        states.clear_state(admin_id)
        await _resend(update, context, order, text.strip())
        return True
    if action == "custom_msg":
        with use_lang(await user_lang(int(order["telegram_id"]))):
            await notify(
                int(order["telegram_id"]),
                "custom_msg",
                t("Message from support"),
                text.strip(),
                order_id=int(order["id"]),
            )
        await q.add_audit(admin_id, "custom_msg", "order", str(order["id"]), payload_after={"text": text})
        await update.message.reply_text(t("✉️ Message queued for the user."))
        states.clear_state(admin_id)
        return True
    if action == "internal_note":
        await q.add_order_note(int(order["id"]), admin_id, text.strip())
        await q.add_audit(admin_id, "internal_note", "order", str(order["id"]), payload_after={"note": text})
        await update.message.reply_text(t("📝 Note saved."))
        states.clear_state(admin_id)
        return True
    return False


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(pending, pattern=r"^orders:pending$"))
    application.add_handler(CallbackQueryHandler(view, pattern=r"^order:view:\d+$"))
    application.add_handler(CallbackQueryHandler(approve_prompt, pattern=r"^order:approve:\d+$"))
    application.add_handler(CallbackQueryHandler(approve_confirm, pattern=r"^order:approve_confirm:\d+$"))
    application.add_handler(CallbackQueryHandler(edit_price_prompt, pattern=r"^order:edit_price:\d+$"))
    application.add_handler(CallbackQueryHandler(reject_prompt, pattern=r"^order:reject:\d+$"))
    application.add_handler(CallbackQueryHandler(reject_reason, pattern=r"^order:reject_reason:\d+:\w+$"))
    application.add_handler(CallbackQueryHandler(reject_custom, pattern=r"^order:reject_custom:\d+$"))
    application.add_handler(CallbackQueryHandler(resend_prompt, pattern=r"^order:resend:\d+$"))
    application.add_handler(CallbackQueryHandler(resend_send, pattern=r"^order:resend_send:\d+$"))
    application.add_handler(CallbackQueryHandler(resend_edit, pattern=r"^order:resend_edit:\d+$"))
    application.add_handler(CallbackQueryHandler(custom_msg, pattern=r"^order:custom:\d+$"))
    application.add_handler(CallbackQueryHandler(internal_note, pattern=r"^order:note:\d+$"))
    application.add_handler(CallbackQueryHandler(under_review, pattern=r"^order:review:\d+$"))
    application.add_handler(CallbackQueryHandler(previous_receipts, pattern=r"^order:receipts:\d+$"))
    application.add_handler(CallbackQueryHandler(show_receipt, pattern=r"^order:receipt:\d+:\d+$"))
