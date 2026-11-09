"""APScheduler jobs for the manager bot."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from core.config import settings
from core.db import queries as q
from core.i18n import format_number, normalize_lang, t, use_lang
from core.notifications import notify
from core.services.referrals import credit_referral_for_order
from manager_bot import ui
from manager_bot.util import age_minutes

logger = logging.getLogger(__name__)

PENDING_STATUSES = ("pending", "needs_resend", "under_review")
OPEN_TICKET_STATUSES = ("open", "in_progress")


def _delivery_ids() -> list[int]:
    ids = list(settings.manager_id_list)
    if settings.manager_group_id:
        ids.append(int(settings.manager_group_id))
    return ids


async def _lang_for(chat_id: int) -> str:
    if settings.manager_group_id and chat_id == int(settings.manager_group_id):
        lang = await q.get_manager_lang(chat_id)
        return normalize_lang(lang) if lang else "fa"
    lang = await q.get_manager_lang(chat_id)
    return normalize_lang(lang) if lang else "en"


async def deliver_pending(application: Application) -> None:
    pending = await q.list_pending_notifications(_delivery_ids())
    for notif in pending:
        text = notif["title"]
        if notif.get("body"):
            text += "\n\n" + notif["body"]
        chat_id = int(notif["telegram_id"])
        try:
            markup = None
            if (
                notif.get("type") in {"new_order", "order_new_receipt"}
                and notif.get("order_id")
            ):
                with use_lang(await _lang_for(chat_id)):
                    markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            t("🔎 Review order"),
                            callback_data=f"order:view:{int(notif['order_id'])}",
                        )
                    ]])
            await application.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=markup
            )
            await q.mark_notification_delivered(int(notif["id"]))
        except Exception:
            logger.exception("manager delivery failed for %s", notif.get("id"))


async def retry_referrals(application: Application) -> None:
    client = application.bot_data.get("rebecca")
    if client is None:
        return
    for referral in await q.list_pending_referrals_for_approved_orders():
        try:
            result = await credit_referral_for_order(
                int(referral["order_id"]), client
            )
            if result == "credited":
                logger.info(
                    "referral credited for order %s", referral["order_id"]
                )
        except Exception:
            logger.exception(
                "referral retry failed for order %s", referral["order_id"]
            )


async def _broadcast_to_admins(application: Application, build: Callable[[], str]) -> None:
    targets = _delivery_ids()
    if not targets:
        logger.warning("no manager ids configured for digest")
        return
    for chat_id in targets:
        try:
            with use_lang(await _lang_for(chat_id)):
                text = build()
            await application.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        except Exception:
            logger.exception("digest send failed to %s", chat_id)


async def sla_check(application: Application) -> None:
    bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    group = int(settings.manager_group_id) if settings.manager_group_id else None
    if group is None:
        return

    with use_lang(await _lang_for(group)):
        pending = await q.list_orders_by_status(PENDING_STATUSES)
        old_orders = [o for o in pending if age_minutes(o.get("created_at")) > 120]
        if old_orders:
            await notify(
                group, "sla_breach",
                t(
                    "⏰ {count} order(s) pending >2h",
                    count=format_number(len(old_orders)),
                ),
                t("Open pending orders and review them."),
                dedupe_key=f"sla:orders:{bucket}",
            )

        tickets = await q.list_tickets_by_status(OPEN_TICKET_STATUSES)
        old_tickets = [x for x in tickets if age_minutes(x.get("created_at")) > 1440]
        if old_tickets:
            await notify(
                group, "sla_breach",
                t(
                    "⏰ {count} ticket(s) open >24h",
                    count=format_number(len(old_tickets)),
                ),
                t("Tickets are waiting for an admin reply."),
                dedupe_key=f"sla:tickets:{bucket}",
            )


async def daily_digest(application: Application) -> None:
    today = await q.revenue_since("start of day")
    week = await q.revenue_since("-7 days")
    statuses = await q.orders_status_counts_since("-1 day")
    total_users = await q.count_users()
    new_users = await q.count_users_since("-1 day")

    def build() -> str:
        status_text = ", ".join(
            f"{t(k)}={format_number(v)}" for k, v in sorted(statuses.items())
        ) or t("none")
        return (
            "📅 <b>" + t("Daily digest") + "</b>\n"
            + t(
                "💰 Revenue today: {today} · 7d: {week}",
                today=ui.fmt_money(today),
                week=ui.fmt_money(week),
            )
            + "\n"
            + t("🧾 Orders today: {statuses}", statuses=status_text)
            + "\n"
            + t(
                "👥 Users: {total} total · {new} new today",
                total=format_number(total_users),
                new=format_number(new_users),
            )
        )

    await _broadcast_to_admins(application, build)


async def weekly_digest(application: Application) -> None:
    week = await q.revenue_since("-7 days")
    statuses = await q.orders_status_counts_since("-7 days")
    promos = await q.top_promos(5, "-7 days")
    subs = await q.list_all_subscriptions()
    plan_counts: dict[str, int] = {}
    for sub in subs:
        name = sub.get("plan_name") or t("unknown")
        plan_counts[name] = plan_counts.get(name, 0) + 1
    top_plans = sorted(plan_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
    expired = sum(1 for s in subs if (s.get("status") or "").lower() == "expired")

    def build() -> str:
        status_text = ", ".join(
            f"{t(k)}={format_number(v)}" for k, v in sorted(statuses.items())
        ) or t("none")
        plan_text = ", ".join(f"{t(n)}({format_number(c)})" for n, c in top_plans) or t("none")
        promo_text = ", ".join(
            f"{p['code']}({format_number(p['uses'])})" for p in promos
        ) or t("none")
        return (
            "📈 <b>" + t("Weekly digest") + "</b>\n"
            + t("💰 Revenue 7d: {week}", week=ui.fmt_money(week))
            + "\n"
            + t("🧾 Orders 7d: {statuses}", statuses=status_text)
            + "\n"
            + t("📦 Top plans: {plans}", plans=plan_text)
            + "\n"
            + t("🎁 Top promos: {promos}", promos=promo_text)
            + "\n"
            + t(
                "📉 Churn: {expired} expired subs · {rejected} rejected orders",
                expired=format_number(expired),
                rejected=format_number(statuses.get("rejected", 0)),
            )
        )

    await _broadcast_to_admins(application, build)


def start_scheduler(application: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.tz))
    scheduler.add_job(
        deliver_pending, "interval", seconds=10, args=[application],
        id="deliver_pending", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        retry_referrals, "interval", minutes=10, args=[application],
        id="retry_referrals", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        sla_check, "interval", minutes=15, args=[application],
        id="sla_check", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        daily_digest, CronTrigger(hour=9, minute=0), args=[application],
        id="daily_digest", replace_existing=True,
    )
    scheduler.add_job(
        weekly_digest, CronTrigger(day_of_week="mon", hour=9, minute=0), args=[application],
        id="weekly_digest", replace_existing=True,
    )
    scheduler.start()
    return scheduler
