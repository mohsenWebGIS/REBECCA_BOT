"""Subscription list, detail, QR/URL and refresh."""
from __future__ import annotations

from io import BytesIO
from typing import Optional

import qrcode
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import format_number, normalize_lang, parse_number, t, use_lang
from core.rebecca_api import RebeccaAPIError
from core.services.sync import sync_for_telegram_id
from user_bot import keyboards as kb, ratelimit, states, ui
from user_bot.handlers.util import answer, client, safe_edit

MAX_SUB_NAME = 40


async def _owned_sub(update: Update) -> Optional[dict]:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return None
    sub_id = int(query.data.rsplit(":", 1)[-1])
    sub = await q.get_subscription(sub_id)
    if sub is None or int(sub["telegram_id"]) != update.effective_user.id:
        await answer(query, t("Subscription not found."))
        return None
    return sub


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    rebecca = client(context)
    try:
        await sync_for_telegram_id(update.effective_user.id, rebecca)
    except Exception:
        pass
    text, markup = await ui.render_subs_list(update.effective_user.id, rebecca)
    await safe_edit(query, text, markup)


async def show_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sub = await _owned_sub(update)
    if sub is None:
        return
    await answer(update.callback_query)
    text, markup = await ui.render_sub_detail(sub)
    await safe_edit(update.callback_query, text, markup)


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sub = await _owned_sub(update)
    if sub is None:
        return
    query = update.callback_query
    await answer(query, t("Refreshing…"))
    uid = int(sub["telegram_id"])
    rebecca = client(context)
    refreshed = await ui.refresh_subscriptions(uid, rebecca)
    current = next((s for s in refreshed if int(s["id"]) == int(sub["id"])), None)
    if current is None:
        text, markup = await ui.render_subs_list(uid, rebecca)
    else:
        text, markup = await ui.render_sub_detail(current)
    await safe_edit(query, text, markup)


async def rename_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sub = await _owned_sub(update)
    if sub is None:
        return
    query = update.callback_query
    await answer(query)
    states.set_state(
        update.effective_user.id, states.FLOW_SUB_RENAME, sub_id=int(sub["id"])
    )
    await query.message.reply_text(
        t(
            "✏️ Send a new name for this subscription (max {max} characters), or /cancel.",
            max=format_number(MAX_SUB_NAME),
        ),
        reply_markup=kb.cancel_only(),
    )


async def on_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    state = states.get_state(uid)
    if state.get("flow") != states.FLOW_SUB_RENAME:
        return
    name = " ".join((update.message.text or "").split())
    if not name:
        await update.message.reply_text(
            t("Please send a non-empty subscription name."),
            reply_markup=kb.cancel_only(),
        )
        return
    if len(name) > MAX_SUB_NAME:
        await update.message.reply_text(
            t(
                "Subscription name is too long. Maximum {max} characters.",
                max=format_number(MAX_SUB_NAME),
            ),
            reply_markup=kb.cancel_only(),
        )
        return
    sub = await q.get_subscription(int(state["sub_id"]))
    if sub is None or int(sub["telegram_id"]) != uid:
        states.clear_state(uid)
        await update.message.reply_text(t("Subscription not found."))
        return
    await q.update_subscription(int(sub["id"]), display_name=name)
    states.clear_state(uid)
    sub = await q.get_subscription(int(sub["id"]))
    text, markup = await ui.render_sub_detail(sub)
    await update.message.reply_text(
        t("✅ Subscription name updated.") + "\n\n" + text,
        reply_markup=markup,
        parse_mode="HTML",
    )


async def renew_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sub = await _owned_sub(update)
    if sub is None:
        return
    query = update.callback_query
    if await q.get_pending_transfer_for_sub(int(sub["id"])) is not None:
        await answer(query, t("A transfer is already pending for this subscription."))
        return
    if await q.get_pending_renewal_for_sub(int(sub["id"])) is not None:
        await answer(query, t("A renewal order is already pending for this subscription."))
        return
    plan_gb = float(sub.get("plan_gb") or sub.get("traffic_total_gb") or 0)
    plan_days = int(sub.get("plan_days") or 30)
    if plan_gb <= 0:
        await answer(query, t("This subscription cannot be renewed."))
        return
    plan = {
        "name": sub.get("plan_name") or t("Renewal"),
        "gb": plan_gb,
        "days": plan_days,
    }
    await answer(query)
    states.set_state(
        update.effective_user.id,
        "",
        renewal_sub_id=int(sub["id"]),
        renewal_plan=plan,
    )
    text, markup = await ui.render_payment(
        plan, None, 0.0, update.effective_user.id, None, int(sub["id"])
    )
    await safe_edit(query, text, markup)


async def transfer_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sub = await _owned_sub(update)
    if sub is None:
        return
    query = update.callback_query
    pending = await q.get_pending_transfer_for_sub(int(sub["id"]))
    if pending is not None:
        await answer(query, t("A transfer is already pending for this subscription."))
        return
    await answer(query)
    states.set_state(
        update.effective_user.id, states.FLOW_TRANSFER, sub_id=int(sub["id"])
    )
    await query.message.reply_text(
        t("🎁 Send the recipient's Telegram ID, or /cancel."),
        reply_markup=kb.cancel_only(),
    )


async def on_transfer_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    state = states.get_state(uid)
    if state.get("flow") != states.FLOW_TRANSFER:
        return
    if not ratelimit.allow(uid, "transfer", 5, 86400) or not ratelimit.allow(
        uid, "transfer_cooldown", 1, 30
    ):
        await update.message.reply_text(
            t("Too many requests. Please wait and try again later.")
        )
        return
    sub = await q.get_subscription(int(state["sub_id"]))
    if sub is None or int(sub["telegram_id"]) != uid:
        states.clear_state(uid)
        await update.message.reply_text(t("Subscription not found."))
        return
    value = parse_number((update.message.text or "").strip())
    if value is None or value <= 0 or not float(value).is_integer():
        await update.message.reply_text(t("Send a valid Telegram ID (numbers only)."))
        return
    target = int(value)
    if target == uid:
        await update.message.reply_text(t("You cannot transfer to yourself."))
        return
    recipient = await q.get_user(target)
    if recipient is None:
        await update.message.reply_text(t("Recipient must have started this bot first."))
        return
    pending = await q.get_pending_transfer_for_sub(int(sub["id"]))
    if pending is not None:
        states.clear_state(uid)
        await update.message.reply_text(
            t("A transfer is already pending for this subscription.")
        )
        return
    transfer_id = await q.create_transfer(int(sub["id"]), uid, target)
    if not transfer_id:
        states.clear_state(uid)
        await update.message.reply_text(
            t("A transfer is already pending for this subscription.")
        )
        return

    sender = update.effective_user
    sender_label = f"@{sender.username}" if sender.username else format_number(uid)
    lang = normalize_lang(recipient.get("preferred_lang") or "en")
    with use_lang(lang):
        body = (
            t("🎁 Subscription transfer") + "\n\n"
            + t(
                "User {sender} wants to transfer {name} to you.",
                sender=sender_label,
                name=ui.sub_title(sub),
            ) + "\n\n"
            + t("Only accept if you trust the sender.")
        )
    try:
        await context.bot.send_message(
            chat_id=target,
            text=body,
            reply_markup=kb.transfer_decision(transfer_id),
        )
    except TelegramError:
        await q.set_transfer_status(transfer_id, "cancelled")
        states.clear_state(uid)
        await update.message.reply_text(
            t("⚠️ Could not message the recipient. They must have started the bot and not blocked it.")
        )
        return
    states.clear_state(uid)
    await update.message.reply_text(t("✅ Transfer request sent to the recipient."))


async def _pending_transfer(update: Update):
    query = update.callback_query
    if query is None or update.effective_user is None:
        return None
    transfer_id = int(query.data.rsplit(":", 1)[-1])
    transfer = await q.get_transfer(transfer_id)
    if transfer is None or int(transfer["to_id"]) != update.effective_user.id:
        await answer(query, t("Transfer not found."))
        return None
    if transfer["status"] != "pending":
        await answer(query, t("This transfer is no longer valid."))
        return None
    return transfer


async def transfer_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    transfer = await _pending_transfer(update)
    if transfer is None:
        return
    await answer(query)
    sub = await q.get_subscription(int(transfer["sub_id"]))
    if sub is None or int(sub["telegram_id"]) != int(transfer["from_id"]):
        await q.set_transfer_status(int(transfer["id"]), "cancelled")
        await safe_edit(query, t("This transfer is no longer valid."), kb.back_home())
        return
    try:
        await client(context).update_user(
            sub["rebecca_username"], telegram_id=str(transfer["to_id"])
        )
    except RebeccaAPIError as exc:
        await query.message.reply_text(
            t(
                "⚠️ Rebecca error: {status} {detail}",
                status=exc.status,
                detail=exc.text[:150],
            )
        )
        return
    await q.update_subscription(
        int(sub["id"]),
        telegram_id=int(transfer["to_id"]),
        display_name=None,
    )
    await q.set_transfer_status(int(transfer["id"]), "accepted")
    await safe_edit(
        query,
        t("✅ Transfer accepted. The subscription is now in My Subscriptions."),
        kb.back_home(),
    )
    sender = await q.get_user(int(transfer["from_id"]))
    sender_lang = normalize_lang(sender.get("preferred_lang") if sender else "en")
    with use_lang(sender_lang):
        text = t(
            "✅ Subscription {name} was transferred to the recipient.",
            name=ui.sub_title(sub),
        )
    try:
        await context.bot.send_message(chat_id=int(transfer["from_id"]), text=text)
    except TelegramError:
        pass


async def transfer_decline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    transfer = await _pending_transfer(update)
    if transfer is None:
        return
    await q.set_transfer_status(int(transfer["id"]), "declined")
    await answer(query, t("Transfer declined."))
    await safe_edit(query, t("❌ Transfer declined."), kb.back_home())
    sub = await q.get_subscription(int(transfer["sub_id"]))
    name = ui.sub_title(sub) if sub is not None else t("subscription")
    sender = await q.get_user(int(transfer["from_id"]))
    sender_lang = normalize_lang(sender.get("preferred_lang") if sender else "en")
    with use_lang(sender_lang):
        text = t(
            "❌ The recipient declined the transfer of {name}.", name=name
        )
    try:
        await context.bot.send_message(chat_id=int(transfer["from_id"]), text=text)
    except TelegramError:
        pass


async def send_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sub = await _owned_sub(update)
    if sub is None:
        return
    query = update.callback_query
    url = sub.get("subscription_url")
    if not url:
        await answer(query, t("No subscription URL available yet."))
        return
    await answer(query)
    image = qrcode.make(url)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=buffer,
        caption=t(
            "📱 QR for {name}",
            name=ui.esc(ui.sub_title(sub)),
        ),
        parse_mode="HTML",
    )


async def send_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sub = await _owned_sub(update)
    if sub is None:
        return
    query = update.callback_query
    url = sub.get("subscription_url")
    if not url:
        await answer(query, t("No subscription URL available yet."))
        return
    await answer(query)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=t("🔗 Open subscription URL") + f'\n\n<a href="{ui.esc(url)}"><code>{ui.esc(url)}</code></a>',
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(show_list, pattern=r"^subs:list$"))
    application.add_handler(CallbackQueryHandler(show_detail, pattern=r"^sub:view:\d+$"))
    application.add_handler(CallbackQueryHandler(refresh, pattern=r"^sub:refresh:\d+$"))
    application.add_handler(
        CallbackQueryHandler(rename_prompt, pattern=r"^sub:rename:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(renew_prompt, pattern=r"^sub:renew:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(transfer_prompt, pattern=r"^sub:transfer:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(transfer_accept, pattern=r"^transfer:accept:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(transfer_decline, pattern=r"^transfer:decline:\d+$")
    )
    application.add_handler(CallbackQueryHandler(send_qr, pattern=r"^sub:qr:\d+$"))
    application.add_handler(CallbackQueryHandler(send_url, pattern=r"^sub:url:\d+$"))
