"""Broadcast composer: segment → compose → preview → rate-limited send."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import format_number, parse_number, t
from core.notifications import notify
from manager_bot import keyboards as kb, states, ui
from manager_bot.util import answer, manager_only, safe_edit

SEND_PER_SECOND = 20


async def _recipients(segment: str, state: dict) -> list[int]:
    if segment == "all":
        return await q.list_user_ids()
    if segment == "active":
        return await q.user_ids_active(7)
    if segment == "expiring":
        return await q.user_ids_expiring(7)
    if segment == "traffic":
        return await q.user_ids_high_traffic(90)
    if segment == "custom":
        return state.get("custom_ids", [])
    return []


@manager_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    states.clear_state(update.effective_user.id)
    await safe_edit(
        query,
        "<b>" + t("📢 Broadcast") + "</b>\n\n" + t("Choose a segment:"),
        kb.broadcast_segments(),
    )


@manager_only
async def choose_segment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    segment = query.data.rsplit(":", 1)[-1]
    admin_id = update.effective_user.id
    if segment == "custom":
        states.set_state(admin_id, "broadcast_custom", segment="custom")
        await answer(query)
        await query.message.reply_text(
            t("Send a comma-separated list of telegram ids, or /cancel."),
            reply_markup=kb.cancel(),
        )
        return
    state: dict[str, Any] = {"segment": segment}
    recipients = await _recipients(segment, state)
    states.set_state(admin_id, "broadcast_text", segment=segment, recipients=recipients, force=False)
    await answer(query, t("{count} recipient(s).", count=format_number(len(recipients))))
    await query.message.reply_text(
        t(
            "Segment <b>{segment}</b> · {count} recipients.\n\nSend the broadcast text, or /cancel.",
            segment=ui.esc(t(segment)),
            count=format_number(len(recipients)),
        ),
        reply_markup=kb.cancel(),
        parse_mode="HTML",
    )


@manager_only
async def toggle_force(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    state = states.get_state(update.effective_user.id)
    if state.get("action") != "broadcast_preview":
        await answer(query, t("Compose a broadcast first."))
        return
    force = not state.get("force", False)
    states.set_state(
        update.effective_user.id, "broadcast_preview",
        segment=state["segment"], recipients=state["recipients"],
        text_body=state["text_body"], force=force,
    )
    await answer(query, t("Force critical ON.") if force else t("Force critical OFF."))
    text, markup = ui.render_broadcast_preview(
        state["segment"], state["text_body"], len(state["recipients"]), force
    )
    await safe_edit(query, text, markup)


@manager_only
async def send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    state = states.get_state(update.effective_user.id)
    if state.get("action") != "broadcast_preview":
        await answer(query, t("Compose a broadcast first."))
        return
    await answer(query, t("Sending…"))
    recipients: list[int] = state["recipients"]
    text_body: str = state["text_body"]
    force: bool = state.get("force", False)
    dedupe = "broadcast:" + uuid.uuid4().hex
    sent = skipped = failed = 0

    for telegram_id in recipients:
        if not force:
            user = await q.get_user(telegram_id)
            if user and user.get("mute_broadcasts"):
                skipped += 1
                continue
        inserted = await notify(
            telegram_id, "broadcast", t("📢 Announcement"), text_body, dedupe_key=dedupe
        )
        if not inserted:
            skipped += 1
            continue
        try:
            await context.bot.send_message(chat_id=telegram_id, text=text_body)
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except Exception:
            failed += 1
        else:
            sent += 1
            await _mark_delivered(telegram_id, dedupe)
        await asyncio.sleep(1.0 / SEND_PER_SECOND)

    await q.add_audit(
        update.effective_user.id, "broadcast", "segment", state["segment"],
        payload_after={"sent": sent, "skipped": skipped, "failed": failed, "force": force},
    )
    states.clear_state(update.effective_user.id)
    await query.message.reply_text(
        t(
            "📢 Broadcast complete.\nSent: {sent} · Skipped: {skipped} · Failed: {failed}",
            sent=format_number(sent),
            skipped=format_number(skipped),
            failed=format_number(failed),
        )
    )


async def _mark_delivered(telegram_id: int, dedupe_key: str) -> None:
    notification = await q.get_notification_by_key(telegram_id, "broadcast", dedupe_key)
    if notification is not None:
        await q.mark_notification_delivered(int(notification["id"]))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, text: str) -> bool:
    action = state.get("action")
    admin_id = update.effective_user.id
    if action == "broadcast_custom":
        ids: list[int] = []
        for part in text.replace(" ", "").split(","):
            if part:
                parsed = parse_number(part)
                if parsed is None or parsed != int(parsed):
                    await update.message.reply_text(t("Invalid id: {id}", id=part))
                    return True
                ids.append(int(parsed))
        states.set_state(
            admin_id, "broadcast_text", segment="custom", recipients=ids, force=False
        )
        await update.message.reply_text(
            t(
                "{count} recipient(s). Send the broadcast text.",
                count=format_number(len(ids)),
            )
        )
        return True
    if action == "broadcast_text":
        if not text.strip():
            await update.message.reply_text(t("Message is empty."))
            return True
        states.set_state(
            admin_id, "broadcast_preview",
            segment=state["segment"], recipients=state["recipients"],
            text_body=text.strip(), force=state.get("force", False),
        )
        body, markup = ui.render_broadcast_preview(
            state["segment"], text.strip(), len(state["recipients"]), False
        )
        await update.message.reply_text(body, reply_markup=markup, parse_mode="HTML")
        return True
    return False


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(start, pattern=r"^broadcast:start$"))
    application.add_handler(CallbackQueryHandler(choose_segment, pattern=r"^broadcast:seg:\w+$"))
    application.add_handler(CallbackQueryHandler(toggle_force, pattern=r"^broadcast:force$"))
    application.add_handler(CallbackQueryHandler(send, pattern=r"^broadcast:send$"))
