"""Rendering helpers: build (text, keyboard) pairs for the user bot."""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.db import queries as q
from core.i18n import format_days, format_gb, format_number, format_percent, format_toman, t
from core.pricing import plan_prices
from core.rebecca_api import GB, RebeccaClient
from core.services import discounts as discount_svc
from core.services.payment_card import card_state, grouped_card
from user_bot import keyboards as kb

logger = logging.getLogger(__name__)

CATEGORIES: list[tuple[str, str]] = [
    ("ping", "📶 No ping / high latency"),
    ("unreachable", "🌐 Server unreachable"),
    ("slow", "🐢 Slow speed"),
    ("app", "📱 App won't connect"),
    ("payment", "💳 Payment problem"),
    ("other", "✏️ Other"),
]
CATEGORY_LABELS = dict(CATEGORIES)

TICKET_DOTS = {"open": "🟡", "in_progress": "🔵", "resolved": "🟢", "closed": "⚫"}


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def days_left(expires_at: Optional[str]) -> Optional[int]:
    dt = parse_dt(expires_at)
    if dt is None:
        return None
    return (dt - datetime.now(timezone.utc)).days


def sub_title(sub: dict[str, Any]) -> str:
    return sub.get("display_name") or sub.get("plan_name") or sub["rebecca_username"]


def sub_dot(sub: dict[str, Any]) -> str:
    status = (sub.get("status") or "").lower()
    used = float(sub.get("traffic_used_gb") or 0)
    total = float(sub.get("traffic_total_gb") or 0)
    left = days_left(sub.get("expires_at"))
    if status in {"expired", "disabled"}:
        return "🔴" if status == "expired" else "⚫"
    if left is not None and left <= 0:
        return "🔴"
    if status == "limited" or (total > 0 and used >= total):
        return "⚫"
    if left is not None and left <= 7:
        return "🟡"
    return "🟢"


async def _refresh_one(
    sub: dict[str, Any], client: RebeccaClient
) -> Optional[dict[str, Any]]:
    try:
        async with asyncio.timeout(5):
            data = await client.get_user(sub["rebecca_username"])
    except Exception:
        return sub
    if not data:
        logger.info(
            "removing local subscription %s (%s): panel user no longer exists",
            sub.get("id"),
            sub.get("rebecca_username"),
        )
        await q.delete_subscription(int(sub["id"]))
        return None
    used_gb = float(data.get("used_traffic") or 0) / GB
    total_gb = float(data.get("data_limit") or 0) / GB or float(sub.get("traffic_total_gb") or 0)
    expire = data.get("expire")
    expires_at = sub.get("expires_at")
    if expire:
        try:
            expires_at = datetime.fromtimestamp(int(expire), tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            pass
    status = str(data.get("status") or sub.get("status") or "active")
    url = data.get("subscription_url") or data.get("key_subscription_url") or sub.get("subscription_url")
    if url and str(url).startswith("/"):
        from core.config import settings
        url = settings.rebecca_base + str(url)
    await q.update_subscription(
        int(sub["id"]),
        traffic_used_gb=used_gb,
        traffic_total_gb=total_gb,
        expires_at=expires_at,
        status=status,
        subscription_url=url,
    )
    merged = dict(sub)
    merged.update({
        "traffic_used_gb": used_gb,
        "traffic_total_gb": total_gb,
        "expires_at": expires_at,
        "status": status,
        "subscription_url": url,
    })
    return merged


async def refresh_subscriptions(telegram_id: int, client: RebeccaClient) -> list[dict[str, Any]]:
    subs = await q.list_subscriptions_for_user(telegram_id)
    if not subs:
        return []
    refreshed = await asyncio.gather(*[_refresh_one(s, client) for s in subs])
    return [sub for sub in refreshed if sub is not None]


async def render_main_menu(telegram_id: int) -> tuple[str, Any]:
    subs = await q.list_subscriptions_for_user(telegram_id)
    active = sum(1 for s in subs if (s.get("status") or "").lower() == "active")
    unread = await q.count_unread(telegram_id)
    header = t(
        "👤 {uid} · 📦 {active}/{total} · 🔔 {unread}",
        uid=format_number(telegram_id),
        active=format_number(active),
        total=format_number(len(subs)),
        unread=format_number(unread),
    )
    text = header + "\n\n" + t("Welcome back! Choose an option below.")
    return text, kb.main_menu(unread)


async def render_subs_list(telegram_id: int, client: RebeccaClient) -> tuple[str, Any]:
    subs = await refresh_subscriptions(telegram_id, client)
    if not subs:
        text = t("📦 You have no subscriptions yet.\n\nTap 🛒 Buy to get started.")
        return text, kb.back_and_home("menu:home")
    for sub in subs:
        sub["_dot"] = sub_dot(sub)
    lines = ["📦 <b>" + t("📦 My Subscriptions").replace("📦 ", "") + "</b>"]
    for sub in subs:
        left = days_left(sub.get("expires_at"))
        used = float(sub.get("traffic_used_gb") or 0)
        total = float(sub.get("traffic_total_gb") or 0)
        remaining = max(0.0, total - used)
        days = format_days(left) if left is not None else t("no expiry")
        lines.append(
            t(
                "{dot} <b>{name}</b>\n   {remaining} left · {days}",
                dot=sub["_dot"],
                name=esc(sub_title(sub)),
                remaining=format_gb(remaining),
                days=days,
            )
        )
    return "\n".join(lines), kb.subs_list(subs)


async def render_sub_detail(sub: dict[str, Any]) -> tuple[str, Any]:
    used = float(sub.get("traffic_used_gb") or 0)
    total = float(sub.get("traffic_total_gb") or 0)
    remaining = max(0.0, total - used)
    left = days_left(sub.get("expires_at"))
    days_text = format_days(left) if left is not None else t("no expiry")
    text = (
        f"{sub_dot(sub)} <b>{esc(sub_title(sub))}</b>\n\n"
        + (
            t("Plan: {plan}", plan=esc(sub.get("plan_name") or t("n/a"))) + "\n"
            if sub.get("display_name")
            else ""
        )
        + t("Status: {status}", status=f"<b>{esc(t(sub.get('status') or 'unknown'))}</b>")
        + "\n"
        + t(
            "Traffic: {used} / {total} used ({remaining} left)",
            used=format_gb(used),
            total=format_gb(total),
            remaining=format_gb(remaining),
        )
        + "\n"
        + t(
            "Expires: {expires} ({days})",
            expires=esc(sub.get("expires_at") or t("n/a")),
            days=days_text,
        )
        + "\n"
        + t("Username: {username}", username=f"<code>{esc(sub['rebecca_username'])}</code>")
    )
    return text, kb.sub_detail(int(sub["id"]))


def _plan_label(plan: dict[str, Any]) -> str:
    return t(
        "{name} · {gb} · {days}",
        name=plan["name"],
        gb=format_gb(plan["gb"]),
        days=format_days(int(plan["days"])),
    )


async def render_plans(
    telegram_id: int,
    discount_code: Optional[str],
    invite_code: Optional[str] = None,
) -> tuple[str, Any]:
    plans = await q.list_active_plans()
    discount = await q.get_discount(discount_code) if discount_code else None
    lines = ["🛒 <b>" + t("🛒 Choose a plan").replace("🛒 ", "") + "</b>"]
    rows: list[tuple[int, str]] = []
    for plan in plans:
        base, _volume, after = plan_prices(plan)
        off = discount_svc.amount_for_plan(discount, plan) if discount else None
        final = after - (off or 0.0)
        if off or after != base:
            lines.append(
                t(
                    "• {label} — {base} → {final}",
                    label=esc(_plan_label(plan)),
                    base=f"<s>{format_toman(base)}</s>",
                    final=f"<b>{format_toman(final)}</b>",
                )
            )
        else:
            lines.append(
                t(
                    "• {label} — {final}",
                    label=esc(_plan_label(plan)),
                    final=f"<b>{format_toman(final)}</b>",
                )
            )
        rows.append((int(plan["id"]), f"{_plan_label(plan)} — {format_toman(final)}"))
    if discount:
        lines.append(
            "\n" + t("Promo {code} applied.", code=f"<b>{esc(discount['code'])}</b>")
        )
    if invite_code:
        lines.append(
            "\n" + t("Invitation code applied: {code}", code=f"<b>{esc(invite_code)}</b>")
        )
    if not plans:
        lines.append(t("No plans are available right now."))
    return "\n".join(lines), kb.plans(rows)


async def render_payment(
    plan: dict[str, Any],
    discount: Optional[dict[str, Any]],
    off: float,
    telegram_id: int,
    invite_code: Optional[str] = None,
    renewal_sub_id: Optional[int] = None,
) -> tuple[str, Any]:
    base, volume, after = plan_prices(plan)
    final = max(0.0, after - off)
    saved = volume + (off or 0.0)
    card = await card_state(telegram_id)
    lines = []
    if renewal_sub_id is not None:
        lines.extend([
            t(
                "🔄 Renewal for subscription #{sub_id}",
                sub_id=format_number(renewal_sub_id),
            ),
            "",
        ])
    if card["show"]:
        lines.append("💳 <b>" + t("💳 Pay by card").replace("💳 ", "") + "</b>")
        lines.append(
            t(
                "Card number: {number}",
                number=f"<code>{grouped_card(card['number'])}</code>",
            )
        )
        if card["holder"]:
            lines.append(t("Card holder: {holder}", holder=esc(card["holder"])))
        lines.append("")
    elif card["pending"]:
        lines.extend([t("💳 Card number request is pending manager approval."), ""])
    elif card["allow_request"]:
        lines.extend([t("💳 Request the card number to continue with payment."), ""])
    lines.extend([
        "🧾 <b>" + t("🧾 Payment details").replace("🧾 ", "") + "</b>",
        t("Plan: {plan}", plan=esc(_plan_label(plan))),
        t("List price: {price}", price=format_toman(base)),
    ])
    if volume:
        from core.pricing import volume_discount_percent
        lines.append(
            t(
                "Volume discount ({percent}): -{amount}",
                percent=format_percent(volume_discount_percent(plan["gb"])),
                amount=format_toman(volume),
            )
        )
    if discount and off:
        lines.append(
            t(
                "Discount ({code}): -{amount}",
                code=esc(discount["code"]),
                amount=format_toman(off),
            )
        )
    lines.append(
        t("Total: {total}", total=f"<b>{format_toman(final)}</b>")
        + (t(" (you save {amount})", amount=format_toman(saved)) if saved else "")
    )
    if invite_code:
        lines.append(t("Invitation code: {code}", code=f"<code>{esc(invite_code)}</code>"))
    if card["show"]:
        lines.extend(["", t("After paying, send a screenshot of your payment transaction below.")])
    return "\n".join(lines), kb.payment(
        card["number"] if card["show"] else "",
        can_request=card["allow_request"],
        pending=card["pending"],
        renewal_sub_id=renewal_sub_id,
    )


async def render_tickets_list(telegram_id: int) -> tuple[str, Any]:
    tickets = await q.list_tickets_for_user(telegram_id)
    if not tickets:
        text = t("🎫 You have no tickets.")
        return text, kb.back_and_home("menu:home")
    for ticket in tickets:
        ticket["_dot"] = TICKET_DOTS.get(ticket.get("status") or "open", "•")
    lines = ["🎫 <b>" + t("🎫 My Tickets").replace("🎫 ", "") + "</b>"]
    for ticket in tickets:
        lines.append(
            t(
                "{dot} #{id} · {category} · {status}",
                dot=ticket["_dot"],
                id=esc(ticket["public_id"]),
                category=esc(t(CATEGORY_LABELS.get(ticket["category"], ticket["category"]))),
                status=esc(t(ticket["status"])),
            )
        )
    return "\n".join(lines), kb.tickets_list(tickets)


async def render_ticket_detail(ticket: dict[str, Any]) -> tuple[str, Any]:
    messages = await q.list_ticket_messages(int(ticket["id"]))
    lines = [
        "🎫 <b>" + t("🎫 Ticket #{public_id}", public_id=esc(ticket["public_id"])).replace("🎫 ", "") + "</b>",
        t("Category: {category}", category=esc(t(CATEGORY_LABELS.get(ticket["category"], ticket["category"])))),
        t("Status: {status}", status=f"<b>{esc(t(ticket['status']))}</b>"),
        "",
        f"<i>{esc(ticket.get('description') or t('No description'))}</i>",
    ]
    if messages:
        lines.append("\n" + t("— thread —"))
        for msg in messages:
            role = msg.get("sender_role")
            who = t("👤 You") if role == "user" else t("🛠 Support")
            if msg.get("file_path"):
                lines.append(f"{who}: {t('[attachment]')}")
            if msg.get("body"):
                lines.append(f"{who}: {esc(msg['body'])}")
    return "\n".join(lines), kb.ticket_detail(int(ticket["id"]), str(ticket["status"]))


async def render_notifications(telegram_id: int) -> tuple[str, Any]:
    notifs = await q.list_notifications_for_user(telegram_id, limit=30)
    if not notifs:
        return t("🔔 No notifications yet."), kb.back_and_home("menu:home")
    lines = ["🔔 <b>" + t("🔔 Notifications").replace("🔔 ", "") + "</b>"]
    for notif in notifs:
        icon = "📩" if not notif.get("is_read") else "✅"
        lines.append(f"{icon} {esc(notif['title'])}")
    return "\n".join(lines), kb.notifications_list(notifs)


def render_notification(notif: dict[str, Any]) -> tuple[str, Any]:
    text = f"<b>{esc(notif['title'])}</b>"
    if notif.get("body"):
        text += f"\n\n{esc(notif['body'])}"
    return text, kb.notification_detail(int(notif["id"]))


def render_help() -> tuple[str, Any]:
    text = (
        "<b>" + t("Help") + "</b>\n\n"
        + t("Commands:") + "\n"
        + t("/start — open the main menu") + "\n"
        + t("/cancel — abort the current flow") + "\n"
        + t("/help — show this message") + "\n"
        + t("/language — change language") + "\n\n"
        + t("Use the inline buttons to manage subscriptions, buy a plan, open a ticket, chat with the AI assistant, and read notifications.") + "\n\n"
        + t("To connect: open My Subscriptions → tap a subscription → QR or URL.")
    )
    return text, kb.back_home()


def render_ai_intro() -> tuple[str, Any]:
    text = (
        "🤖 <b>" + t("🤖 AI Assistant").replace("🤖 ", "") + "</b>\n\n"
        + t("Ask me anything about plans, connecting, or using the service. I can't approve payments or promise refunds — for account issues use 🆘 Report Issue.") + "\n\n"
        + t("Send a message to begin. /cancel or the Main Menu button exits.")
    )
    return text, kb.ai_footer()


def render_language() -> tuple[str, Any]:
    return t("Choose your language:"), kb.language()


def receipt_ack(public_id: str) -> str:
    return t("✅ Receipt received. Order #{public_id}, awaiting review.", public_id=esc(public_id))


def ticket_created_ack(public_id: str) -> str:
    return t("🎫 Ticket #{public_id} created.", public_id=esc(public_id))


__all__ = [
    "CATEGORIES", "CATEGORY_LABELS", "esc", "parse_dt", "days_left", "sub_dot",
    "refresh_subscriptions", "render_main_menu", "render_subs_list",
    "render_sub_detail", "render_plans", "render_payment", "render_tickets_list",
    "render_ticket_detail", "render_notifications", "render_notification",
    "render_help", "render_ai_intro", "render_language", "receipt_ack",
    "ticket_created_ack", "format_days",
]
