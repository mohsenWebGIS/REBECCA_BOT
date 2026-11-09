"""APScheduler jobs for the user bot."""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from core.config import settings
from core.db import queries as q
from core.i18n import format_number, format_percent, normalize_lang, t, use_lang
from core.notifications import notify
from user_bot import ui

logger = logging.getLogger(__name__)


async def check_expiry(application: Application) -> None:
    client = application.bot_data.get("rebecca")
    if client is None:
        return
    subs = await q.list_active_subscriptions()
    if not subs:
        return
    for sub in subs:
        try:
            sub = await ui._refresh_one(sub, client)
        except Exception:
            logger.exception("refresh failed for sub %s", sub.get("id"))
        await _enqueue_alerts(application, sub)


async def _enqueue_alerts(application: Application, sub: dict) -> None:
    left = ui.days_left(sub.get("expires_at"))
    used = float(sub.get("traffic_used_gb") or 0)
    total = float(sub.get("traffic_total_gb") or 0)
    pct = (used / total * 100.0) if total > 0 else 0.0
    status = (sub.get("status") or "").lower()
    label = sub.get("display_name") or sub.get("plan_name") or sub["rebecca_username"]
    user = await q.get_user(int(sub["telegram_id"]))
    lang = normalize_lang(user.get("preferred_lang") if user else "en")

    with use_lang(lang):
        if status == "expired" or (left is not None and left <= 0):
            await notify(
                int(sub["telegram_id"]), "sub_expired",
                t("Subscription expired: {label}", label=label),
                t("Your subscription has expired. Open My Subscriptions to renew."),
                bot=application.bot, sub_id=int(sub["id"]),
                dedupe_key="expired:" + str(sub["id"]),
            )
            return

        if left is not None:
            bucket = None
            if left <= 1:
                bucket = "1d"
            elif left <= 3:
                bucket = "3d"
            elif left <= 7:
                bucket = "7d"
            if bucket:
                await notify(
                    int(sub["telegram_id"]), "sub_expiring",
                    t(
                        "Subscription expiring in {days} day(s): {label}",
                        days=format_number(left),
                        label=label,
                    ),
                    t("Renew soon to avoid losing access."),
                    bot=application.bot, sub_id=int(sub["id"]),
                    dedupe_key="expiring:" + bucket + ":" + str(sub["id"]),
                )

        if status == "limited" or pct >= 100:
            await notify(
                int(sub["telegram_id"]), "traffic_100",
                t("Traffic exhausted: {label}", label=label),
                t("You have used 100% of your traffic."),
                bot=application.bot, sub_id=int(sub["id"]),
                dedupe_key="traffic100:" + str(sub["id"]),
            )
        elif pct >= 90:
            await notify(
                int(sub["telegram_id"]), "traffic_90",
                t("Traffic at {percent}: {label}", percent=format_percent(int(pct)), label=label),
                t("You have used over 90% of your traffic."),
                bot=application.bot, sub_id=int(sub["id"]),
                dedupe_key="traffic90:" + str(sub["id"]),
            )


async def deliver_pending(application: Application) -> None:
    user_ids = await q.list_user_ids(exclude=settings.manager_id_list)
    pending = await q.list_pending_notifications(user_ids)
    for notif in pending:
        text = notif["title"]
        if notif.get("body"):
            text += "\n\n" + notif["body"]
        try:
            await application.bot.send_message(chat_id=int(notif["telegram_id"]), text=text)
            await q.mark_notification_delivered(int(notif["id"]))
        except Exception:
            logger.exception("failed to deliver notification %s", notif.get("id"))


def start_scheduler(application: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.tz))
    scheduler.add_job(
        check_expiry, "interval", minutes=10, args=[application],
        id="check_expiry", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        deliver_pending, "interval", minutes=2, args=[application],
        id="deliver_pending", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.start()
    return scheduler
