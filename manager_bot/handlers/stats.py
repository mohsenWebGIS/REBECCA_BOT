"""Live statistics screen and CSV export."""
from __future__ import annotations

import csv
import io

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import t
from manager_bot import ui
from manager_bot.util import answer, client, manager_only, safe_edit


@manager_only
async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_stats(client(context))
    await safe_edit(query, text, markup)


def _csv(rows: list[dict], columns: list[str]) -> bytes:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


@manager_only
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query, t("Building CSV…"))
    chat_id = update.effective_chat.id

    orders = await q.list_all_orders()
    users = await q.list_users(offset=0, limit=100000)
    subs = await q.list_all_subscriptions()

    files = [
        ("orders.csv", _csv(orders, [
            "id", "public_id", "telegram_id", "plan_id", "list_price", "discount_code",
            "volume_discount_toman", "discount_toman", "final_price", "status",
            "created_at", "reviewed_at",
        ])),
        ("users.csv", _csv(users, [
            "telegram_id", "username", "display_name", "joined_at", "banned",
            "mute_broadcasts", "preferred_lang", "lang_selected", "last_seen_at",
        ])),
        ("subscriptions.csv", _csv(subs, [
            "id", "telegram_id", "rebecca_username", "plan_name", "status",
            "traffic_used_gb", "traffic_total_gb", "expires_at", "created_at",
        ])),
    ]
    for name, payload in files:
        await context.bot.send_document(
            chat_id=chat_id, document=io.BytesIO(payload), filename=name
        )


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(show, pattern=r"^stats$"))
    application.add_handler(CallbackQueryHandler(export, pattern=r"^stats:export$"))
