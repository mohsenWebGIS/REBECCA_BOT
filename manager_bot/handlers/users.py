"""User browser and subscription management actions."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import format_gb, format_number, format_toman, parse_number, t, use_lang
from core.notifications import notify
from core.rebecca_api import GB, RebeccaAPIError
from core.services.panel_users import invalidate_unlinked_cache
from core.services.payment_card import notify_user_card_approved
from core.services.sync import link_panel_user
from manager_bot import keyboards as kb, states, ui
from manager_bot.util import answer, client, manager_only, safe_edit, user_lang

PANEL_USERNAME_RE = re.compile(r"^[A-Za-z0-9_@.-]{1,48}$")


def _iso(epoch: Any) -> Optional[str]:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


async def _sub_or_reply(update: Update, sub_id: int) -> Optional[dict]:
    sub = await q.get_subscription(sub_id)
    if sub is None and update.callback_query is not None:
        await answer(update.callback_query, t("Subscription not found."))
    return sub


async def _audit(update: Update, action: str, sub: dict, before: Any, after: Any) -> None:
    await q.add_audit(
        update.effective_user.id, action, "subscription", str(sub["id"]),
        payload_before=before, payload_after=after,
    )


@manager_only
async def page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    number = int(query.data.rsplit(":", 1)[-1])
    text, markup = await ui.render_users_page(number)
    await safe_edit(query, text, markup)


@manager_only
async def unsubscribed_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    number = int(query.data.rsplit(":", 1)[-1])
    text, markup = await ui.render_unsubscribed_users_page(number)
    await safe_edit(query, text, markup)


@manager_only
async def unlinked_panel_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    number = int(query.data.rsplit(":", 1)[-1])
    try:
        text, markup = await ui.render_unlinked_panel_users_page(
            client(context), number
        )
    except RebeccaAPIError as exc:
        await query.message.reply_text(
            t("⚠️ Rebecca error: {status} {detail}", status=exc.status, detail=exc.text[:150])
        )
        return
    await safe_edit(query, text, markup)


@manager_only
async def unlinked_panel_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query, t("Scanning panel…"))
    try:
        text, markup = await ui.render_unlinked_panel_users_page(
            client(context), 0, force=True
        )
    except RebeccaAPIError as exc:
        await query.message.reply_text(
            t("⚠️ Rebecca error: {status} {detail}", status=exc.status, detail=exc.text[:150])
        )
        return
    await safe_edit(query, text, markup)


@manager_only
async def panel_link_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    username = query.data.split(":", 2)[2]
    if not PANEL_USERNAME_RE.fullmatch(username):
        await answer(query, t("Invalid panel username."))
        return
    await answer(query)
    states.set_state(
        update.effective_user.id, "panel_link_telegram", username=username
    )
    await query.message.reply_text(
        t(
            "🔗 Send the Telegram ID to attach to {username}, or /cancel.",
            username=f"<code>{ui.esc(username)}</code>",
        ),
        reply_markup=kb.cancel(),
        parse_mode="HTML",
    )


@manager_only
async def search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    states.set_state(update.effective_user.id, "user_search")
    await query.message.reply_text(
        t("🔎 Send a telegram id or username to search, or /cancel."),
        reply_markup=kb.cancel(),
    )


@manager_only
async def view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.split(":")[2])
    await answer(query)
    text, markup = await ui.render_user_detail(telegram_id)
    await safe_edit(query, text, markup)


@manager_only
async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    await answer(query)
    rows = await q.list_orders_for_user(telegram_id, limit=50)
    buttons = [
        [InlineKeyboardButton(
            f"{t(o['status'])} · #{o['public_id']} · {format_toman(o.get('final_price') or 0)}",
            callback_data=f"order:view:{o['id']}",
        )]
        for o in rows
    ]
    buttons.append([InlineKeyboardButton(t("⬅️ User"), callback_data=f"user:view:{telegram_id}:user")])
    text = t("🧾 Orders for {uid}", uid=format_number(telegram_id)) + ("\n\n" + t("No orders.") if not rows else "")
    await safe_edit(query, text, InlineKeyboardMarkup(buttons))


@manager_only
async def tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    await answer(query)
    rows = await q.list_tickets_for_user(telegram_id, limit=50)
    buttons = [
        [InlineKeyboardButton(
            f"{t(row['status'])} · #{row['public_id']} · {t(row['category'])}",
            callback_data=f"ticket:view:{row['id']}",
        )]
        for row in rows
    ]
    buttons.append([InlineKeyboardButton(t("⬅️ User"), callback_data=f"user:view:{telegram_id}:user")])
    text = t("🎫 Tickets for {uid}", uid=format_number(telegram_id)) + ("\n\n" + t("No tickets.") if not rows else "")
    await safe_edit(query, text, InlineKeyboardMarkup(buttons))


@manager_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    user = await q.get_user(telegram_id)
    if user is None:
        await answer(query, t("User not found."))
        return
    new_state = not bool(user.get("banned"))
    await q.set_user_banned(telegram_id, new_state)
    await q.add_audit(
        update.effective_user.id, "ban" if new_state else "unban", "user", str(telegram_id)
    )
    await answer(query, t("Banned.") if new_state else t("Unbanned."))
    text, markup = await ui.render_user_detail(telegram_id)
    await safe_edit(query, text, markup)


@manager_only
async def card_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    admin_id = update.effective_user.id
    await answer(query)
    access = await q.get_card_access(telegram_id)
    if access is not None and access.get("status") == "approved":
        await q.delete_card_access(telegram_id)
        await q.add_audit(admin_id, "card_revoke", "user", str(telegram_id))
        await answer(query, t("Card access revoked."))
    else:
        await q.set_card_access(telegram_id, "approved", admin_id)
        await q.add_audit(admin_id, "card_grant", "user", str(telegram_id))
        await notify_user_card_approved(telegram_id)
        await answer(query, t("Card access granted."))
    text, markup = await ui.render_user_detail(telegram_id)
    await safe_edit(query, text, markup)


@manager_only
async def dm_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    telegram_id = int(query.data.rsplit(":", 1)[-1])
    await answer(query)
    states.set_state(update.effective_user.id, "user_dm", user_id=telegram_id)
    await query.message.reply_text(
        t("✉️ Send the message to deliver to the user, or /cancel."), reply_markup=kb.cancel()
    )


@manager_only
async def show_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    sub_id = int(query.data.rsplit(":", 1)[-1])
    sub = await _sub_or_reply(update, sub_id)
    if sub is None:
        return
    await answer(query)
    text, markup = ui.render_user_sub(sub)
    await safe_edit(query, text, markup)


@manager_only
async def traffic_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    sub_id = int(parts[2])
    sub = await _sub_or_reply(update, sub_id)
    if sub is None:
        return
    await answer(query)
    await safe_edit(query, "<b>" + t("➕ Add traffic") + "</b>", kb.traffic_amounts(sub_id))


async def _extend(update: Update, context: ContextTypes.DEFAULT_TYPE, sub: dict, days: int) -> None:
    api = client(context)
    try:
        data = await api.get_user(sub["rebecca_username"])
        if not data:
            raise RebeccaAPIError(404, "user not found on panel")
        current = int(data.get("expire") or time.time())
        new_expire = max(current, int(time.time())) + int(days * 86400)
        await api.update_user(sub["rebecca_username"], expire=new_expire)
    except RebeccaAPIError as exc:
        await update.effective_message.reply_text(
            t("⚠️ Rebecca error: {status} {detail}", status=exc.status, detail=exc.text[:150])
        )
        return
    await q.update_subscription(int(sub["id"]), expires_at=_iso(new_expire))
    await _audit(update, "extend_sub", sub, {"expire": current}, {"expire": new_expire})
    await update.effective_message.reply_text(
        t("✅ Extended by {days} days.", days=format_number(days))
    )
    refreshed = await q.get_subscription(int(sub["id"]))
    text, markup = ui.render_user_sub(refreshed)
    await update.effective_message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def _add_traffic(update: Update, context: ContextTypes.DEFAULT_TYPE, sub: dict, gb: float) -> None:
    api = client(context)
    try:
        data = await api.get_user(sub["rebecca_username"])
        if not data:
            raise RebeccaAPIError(404, "user not found on panel")
        current = int(data.get("data_limit") or 0)
        new_limit = current + int(gb * GB)
        await api.update_user(sub["rebecca_username"], data_limit=new_limit)
    except RebeccaAPIError as exc:
        await update.effective_message.reply_text(
            t("⚠️ Rebecca error: {status} {detail}", status=exc.status, detail=exc.text[:150])
        )
        return
    await q.update_subscription(int(sub["id"]), traffic_total_gb=new_limit / GB)
    await _audit(update, "add_traffic", sub, {"data_limit": current}, {"data_limit": new_limit})
    await update.effective_message.reply_text(t("✅ Added {gb}.", gb=format_gb(gb)))
    refreshed = await q.get_subscription(int(sub["id"]))
    text, markup = ui.render_user_sub(refreshed)
    await update.effective_message.reply_text(text, reply_markup=markup, parse_mode="HTML")


@manager_only
async def sub_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    sub_id = int(parts[2])
    action = parts[3]
    sub = await _sub_or_reply(update, sub_id)
    if sub is None:
        return
    api = client(context)

    if action == "extend7":
        await answer(query)
        await _extend(update, context, sub, 7)
    elif action == "extend30":
        await answer(query)
        await _extend(update, context, sub, 30)
    elif action == "extend_custom":
        await answer(query)
        states.set_state(update.effective_user.id, "sub_custom", sub_id=sub_id, kind="extend")
        await query.message.reply_text(t("✏️ Send the number of days to extend."), reply_markup=kb.cancel())
    elif action == "traffic":
        await answer(query)
        await safe_edit(query, "<b>" + t("➕ Add traffic") + "</b>", kb.traffic_amounts(sub_id))
    elif action in {"add5", "add10", "add50"}:
        await answer(query)
        await _add_traffic(update, context, sub, {"add5": 5, "add10": 10, "add50": 50}[action])
    elif action == "traffic_custom":
        await answer(query)
        states.set_state(update.effective_user.id, "sub_custom", sub_id=sub_id, kind="add")
        await query.message.reply_text(t("✏️ Send the number of GB to add."), reply_markup=kb.cancel())
    elif action == "reset":
        await answer(query, t("Resetting…"))
        try:
            await api.reset_user_usage(sub["rebecca_username"])
        except RebeccaAPIError as exc:
            await query.message.reply_text(
                t("⚠️ Rebecca error: {status} {detail}", status=exc.status, detail=exc.text[:150])
            )
            return
        await q.update_subscription(sub_id, traffic_used_gb=0)
        await _audit(update, "reset_traffic", sub, {"used": sub.get("traffic_used_gb")}, {"used": 0})
        await query.message.reply_text(t("♻️ Traffic reset."))
    elif action in {"disable", "enable"}:
        await answer(query)
        status = "disabled" if action == "disable" else "active"
        try:
            await api.update_user(sub["rebecca_username"], status=status)
        except RebeccaAPIError as exc:
            await query.message.reply_text(
                t("⚠️ Rebecca error: {status} {detail}", status=exc.status, detail=exc.text[:150])
            )
            return
        await q.update_subscription(sub_id, status=status)
        await _audit(update, action + "_sub", sub, {"status": sub.get("status")}, {"status": status})
        await query.message.reply_text(t("✅ Subscription {status}.", status=t(status)))
    elif action == "delete":
        await answer(query, t("Confirm deletion."))
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(t("🗑 Confirm delete"), callback_data=f"usub:delete_confirm:{sub_id}")],
            [InlineKeyboardButton(t("⬅️ Back"), callback_data=f"usub:{sub_id}")],
        ])
        await query.message.reply_text(
            t(
                "Delete subscription {username} from the panel?",
                username=f"<code>{ui.esc(sub['rebecca_username'])}</code>",
            ),
            reply_markup=markup, parse_mode="HTML",
        )
    refreshed = await q.get_subscription(sub_id)
    if refreshed and action not in {"delete", "extend7", "extend30", "extend_custom", "add5", "add10", "add50", "traffic_custom", "traffic"}:
        text, markup = ui.render_user_sub(refreshed)
        await query.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


@manager_only
async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    sub_id = int(query.data.rsplit(":", 1)[-1])
    sub = await _sub_or_reply(update, sub_id)
    if sub is None:
        return
    try:
        await client(context).delete_user(sub["rebecca_username"])
    except RebeccaAPIError as exc:
        await answer(query, t("Rebecca error {status}", status=exc.status))
        return
    await _audit(update, "delete_sub", sub, {"username": sub["rebecca_username"]}, None)
    await q.delete_subscription(sub_id)
    await answer(query, t("Deleted."))
    await query.message.reply_text(t("🗑 Subscription deleted from panel and DB."))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, text: str) -> bool:
    action = state.get("action")
    admin_id = update.effective_user.id
    if action == "panel_link_telegram":
        username = str(state.get("username") or "")
        states.clear_state(admin_id)
        if not PANEL_USERNAME_RE.fullmatch(username):
            await update.message.reply_text(t("Invalid panel username."))
            return True
        value = parse_number(text.strip())
        if value is None or value <= 0 or not float(value).is_integer():
            await update.message.reply_text(t("Send a valid Telegram ID (numbers only)."))
            return True
        target = int(value)
        api = client(context)
        existing = ""
        try:
            data = await api.get_user(username)
            if data is None:
                await update.message.reply_text(
                    t("Panel user {username} not found.", username=ui.esc(username))
                )
                return True
            existing = str(data.get("telegram_id") or "").strip()
            if existing and existing != str(target):
                await update.message.reply_text(
                    t(
                        "Panel user {username} is already linked to Telegram ID {id}.",
                        username=ui.esc(username),
                        id=format_number(existing),
                    ),
                    parse_mode="HTML",
                )
                return True
            updated = await api.update_user(username, telegram_id=str(target))
        except RebeccaAPIError as exc:
            await update.message.reply_text(
                t("⚠️ Rebecca error: {status} {detail}", status=exc.status, detail=exc.text[:150])
            )
            return True

        await link_panel_user(target, updated)
        await q.add_audit(
            admin_id,
            "link_panel_telegram",
            "subscription",
            username,
            payload_before={"telegram_id": existing or None},
            payload_after={"telegram_id": str(target)},
        )
        invalidate_unlinked_cache()

        known_user = await q.get_user(target)
        with use_lang(await user_lang(target)):
            await notify(
                target,
                "panel_link",
                t("📦 Your subscription is ready"),
                t("Open the bot and send /start so it appears in My Subscriptions."),
                dedupe_key=f"panel_link:{username}:{target}",
            )
        message = t(
            "✅ Telegram ID {id} linked to panel user {username}.",
            id=format_number(target),
            username=ui.esc(username),
        )
        message += "\n\n" + (
            t("Notification queued for delivery.")
            if known_user is not None
            else t("Notification queued; it will be delivered after the user starts the bot.")
        )
        await update.message.reply_text(message, parse_mode="HTML")
        try:
            list_text, list_markup = await ui.render_unlinked_panel_users_page(
                api, 0, force=True
            )
            await update.message.reply_text(list_text, reply_markup=list_markup)
        except RebeccaAPIError:
            pass
        return True
    if action == "user_search":
        results = await q.search_users(text.strip(), limit=20)
        states.clear_state(admin_id)
        if not results:
            await update.message.reply_text(t("No users matched."))
            return True
        buttons = [[InlineKeyboardButton(
            f"{format_number(u['telegram_id'])} · @{u.get('username') or '—'}",
            callback_data=f"user:view:{u['telegram_id']}:user",
        )] for u in results]
        await update.message.reply_text(
            t("🔎 {count} result(s):", count=format_number(len(results))),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return True
    if action == "user_dm":
        target = int(state["user_id"])
        with use_lang(await user_lang(target)):
            await notify(target, "custom_msg", t("Message from support"), text.strip())
        await q.add_audit(admin_id, "send_dm", "user", str(target), payload_after={"text": text})
        states.clear_state(admin_id)
        await update.message.reply_text(t("✉️ Message queued for delivery."))
        return True
    if action == "sub_custom":
        sub = await q.get_subscription(int(state["sub_id"]))
        states.clear_state(admin_id)
        if sub is None:
            await update.message.reply_text(t("Subscription not found."))
            return True
        amount = parse_number(text)
        if amount is None:
            await update.message.reply_text(t("Send a number."))
            return True
        if state.get("kind") == "extend":
            await _extend(update, context, sub, int(amount))
        else:
            await _add_traffic(update, context, sub, amount)
        return True
    return False


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(page, pattern=r"^users:page:\d+$"))
    application.add_handler(CallbackQueryHandler(unsubscribed_page, pattern=r"^users:nosub:page:\d+$"))
    application.add_handler(CallbackQueryHandler(unlinked_panel_page, pattern=r"^panel:unlinked:page:\d+$"))
    application.add_handler(CallbackQueryHandler(unlinked_panel_refresh, pattern=r"^panel:unlinked:refresh$"))
    application.add_handler(CallbackQueryHandler(panel_link_prompt, pattern=r"^panel:link:.+$"))
    application.add_handler(CallbackQueryHandler(search_prompt, pattern=r"^user:search$"))
    application.add_handler(CallbackQueryHandler(view, pattern=r"^user:view:-?\d+:\w+$"))
    application.add_handler(CallbackQueryHandler(orders, pattern=r"^user:orders:\d+$"))
    application.add_handler(CallbackQueryHandler(tickets, pattern=r"^user:tickets:\d+$"))
    application.add_handler(CallbackQueryHandler(ban, pattern=r"^user:ban:\d+$"))
    application.add_handler(CallbackQueryHandler(card_access, pattern=r"^user:card:\d+$"))
    application.add_handler(CallbackQueryHandler(dm_prompt, pattern=r"^user:dm:\d+$"))
    application.add_handler(CallbackQueryHandler(show_sub, pattern=r"^usub:\d+$"))
    application.add_handler(CallbackQueryHandler(traffic_menu, pattern=r"^usub:act:\d+:traffic$"))
    application.add_handler(CallbackQueryHandler(sub_action, pattern=r"^usub:act:\d+:\w+$"))
    application.add_handler(CallbackQueryHandler(delete_confirm, pattern=r"^usub:delete_confirm:\d+$"))
