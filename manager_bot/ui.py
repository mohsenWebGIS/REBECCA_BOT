"""Rendering helpers for the manager bot."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Optional

from core.db import queries as q
from core.i18n import format_days, format_gb, format_number, format_toman, t
from core.rebecca_api import RebeccaClient
from core.services.panel_users import scan_unlinked_panel_users
from core.services.payment_card import get_card_config, grouped_card
from manager_bot import keyboards as kb
from manager_bot.util import age_dot, age_minutes, parse_dt, rel_time

PENDING_STATUSES = ("pending", "needs_resend", "under_review")
OPEN_TICKET_STATUSES = ("open", "in_progress")

CATEGORY_LABELS = {
    "ping": "📶 No ping / high latency",
    "unreachable": "🌐 Server unreachable",
    "slow": "🐢 Slow speed",
    "app": "📱 App won't connect",
    "payment": "💳 Payment problem",
    "other": "✏️ Other",
}


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def fmt_money(value: Any) -> str:
    return format_toman(value if value is not None else 0)


def _plan_snapshot(order: dict[str, Any]) -> dict[str, Any]:
    raw = order.get("plan_snapshot")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return raw or {}


async def render_admin_menu() -> tuple[str, Any]:
    pending = await q.list_orders_by_status(PENDING_STATUSES)
    tickets = await q.list_tickets_by_status(OPEN_TICKET_STATUSES)
    today = await q.revenue_since("start of day")
    week = await q.revenue_since("-7 days")
    text = (
        "🛠 <b>" + t("🛠 Admin Menu").replace("🛠 ", "") + "</b>\n\n"
        + t("🔔 Pending orders: {count}", count=f"<b>{format_number(len(pending))}</b>") + "\n"
        + t("🎫 Open tickets: {count}", count=f"<b>{format_number(len(tickets))}</b>") + "\n"
        + t("💰 Revenue today: {amount}", amount=f"<b>{fmt_money(today)}</b>") + "\n"
        + t("💰 Revenue 7d: {amount}", amount=f"<b>{fmt_money(week)}</b>")
    )
    return text, kb.admin_menu(len(pending), len(tickets))


async def render_pending_orders() -> tuple[str, Any]:
    orders = await q.list_orders_by_status(PENDING_STATUSES)
    dots = {int(o["id"]): age_dot(age_minutes(o.get("created_at"))) for o in orders}
    if not orders:
        text = t("📥 Pending orders") + "\n\n" + t("Nothing waiting. 🎉")
    else:
        lines = ["📥 <b>" + t("📥 Pending orders").replace("📥 ", "") + "</b>"]
        for order in orders:
            lines.append(
                t(
                    "{dot} #{id} · {uid} · {amount} · {when}",
                    dot=dots[int(order["id"])],
                    id=esc(order["public_id"]),
                    uid=format_number(order["telegram_id"]),
                    amount=fmt_money(order.get("final_price")),
                    when=rel_time(order.get("created_at")),
                )
            )
        text = "\n".join(lines)
    return text, kb.pending_orders(orders, dots)


async def order_user_context(order: dict[str, Any]) -> str:
    user = await q.get_user(int(order["telegram_id"]))
    subs = await q.list_subscriptions_for_user(int(order["telegram_id"]))
    active_subs = sum(1 for s in subs if (s.get("status") or "").lower() == "active")
    paid = await q.user_total_paid(int(order["telegram_id"]))
    rejections = await q.user_rejection_count(int(order["telegram_id"]))
    open_tickets = await q.count_open_tickets_for_user(int(order["telegram_id"]))
    joined = user.get("joined_at") if user else None
    dt = parse_dt(joined)
    days = (datetime.now(timezone.utc) - dt).days if dt else 0
    return (
        t("— user context —") + "\n"
        + t(
            "Active subs: {subs} · Total paid: {paid} · Rejections: {rejections}",
            subs=format_number(active_subs),
            paid=fmt_money(paid),
            rejections=format_number(rejections),
        ) + "\n"
        + t(
            "Member since: {date} ({days} days) · Open tickets: {tickets}",
            date=esc((joined or t("unknown"))[:10]),
            days=format_number(days),
            tickets=format_number(open_tickets),
        )
    )


async def render_order_detail(order: dict[str, Any]) -> tuple[str, Any]:
    snapshot = _plan_snapshot(order)
    user = await q.get_user(int(order["telegram_id"]))
    username = f"@{user['username']}" if user and user.get("username") else "—"
    lines = [
        "🧾 <b>" + t("🧾 Order #{public_id}", public_id=esc(order["public_id"])).replace("🧾 ", "") + "</b>",
        t("User: {uid} ({username})", uid=f"<code>{format_number(order['telegram_id'])}</code>", username=esc(username)),
        t(
            "Plan: {plan} · {gb} · {days}",
            plan=esc(snapshot.get("name", "?")),
            gb=format_gb(snapshot.get("gb", 0)),
            days=format_days(snapshot.get("days", 0)),
        ),
        t("List price: {price}", price=fmt_money(order.get("list_price"))),
    ]
    if order.get("kind") == "renewal":
        lines.insert(
            3,
            t(
                "Renewal for subscription #{sub_id}",
                sub_id=format_number(order.get("subscription_id") or 0),
            ),
        )
    if float(order.get("volume_discount_toman") or 0):
        lines.append(
            t(
                "Volume discount: -{amount}",
                amount=fmt_money(order.get("volume_discount_toman")),
            )
        )
    lines.append(
        t(
            "Discount: {code} (-{amount})",
            code=esc(order.get("discount_code") or t("none")),
            amount=fmt_money(order.get("discount_toman")),
        )
    )
    lines.extend([
        t("Final price: {amount}", amount=f"<b>{fmt_money(order.get('final_price'))}</b>"),
        t("Submitted: {when}", when=rel_time(order.get("created_at"))),
        t("Status: {status}", status=f"<b>{esc(t(order['status']))}</b>"),
    ])
    if order.get("reject_reason"):
        lines.append(t("Reject reason: {reason}", reason=esc(order["reject_reason"])))
    lines.extend(["", await order_user_context(order)])

    history: list = []
    try:
        history = json.loads(order.get("receipt_history") or "[]")
    except (ValueError, TypeError):
        history = []
    notes = await q.list_order_notes(int(order["id"]))
    if notes:
        lines.append("\n" + t("📝 Notes: {notes}", notes="; ".join(esc(n["note"]) for n in notes)))
    text = "\n".join(lines)
    return text, kb.order_detail(int(order["id"]), int(order["telegram_id"]), bool(history))


def render_approve_confirm(order: dict[str, Any], price: float) -> tuple[str, Any]:
    text = (
        "✅ <b>" + t("✅ Approve order").replace("✅ ", "") + "</b>\n\n"
        + t("Order #{public_id}", public_id=esc(order["public_id"])) + "\n"
        + t(
            "Renew Rebecca sub · notify user · mark paid {amount}"
            if order.get("kind") == "renewal"
            else "Provision Rebecca sub · notify user · mark paid {amount}",
            amount=fmt_money(price),
        )
    )
    return text, kb.approve_confirm(int(order["id"]))


def render_reject_reasons(order: dict[str, Any]) -> tuple[str, Any]:
    return (
        t("❌ Reject order #{public_id}", public_id=esc(order["public_id"]))
        + "\n\n"
        + t("Choose a reason:"),
        kb.reject_reasons(int(order["id"])),
    )


RESEND_DEFAULT = "We couldn't verify your payment. Please re-upload a clear screenshot of the transaction."


def render_resend(order: dict[str, Any]) -> tuple[str, Any]:
    text = (
        "📸 <b>" + t("📸 Ask resend — order #{public_id}", public_id=esc(order["public_id"])).replace("📸 ", "") + "</b>\n\n"
        + t("Message to user:\n{message}", message=f"<i>{esc(RESEND_DEFAULT)}</i>")
    )
    return text, kb.resend_confirm(int(order["id"]))


async def render_previous_receipts(order: dict[str, Any]) -> tuple[str, Any]:
    try:
        history = json.loads(order.get("receipt_history") or "[]")
    except (ValueError, TypeError):
        history = []
    return (
        "🖼 <b>" + t("🖼 Previous Receipts").replace("🖼 ", "") + "</b> · "
        + t("Order #{public_id}", public_id=esc(order["public_id"])),
        kb.previous_receipts(int(order["id"]), len(history)),
    )


async def render_tickets_queue() -> tuple[str, Any]:
    tickets = await q.list_tickets_by_status(OPEN_TICKET_STATUSES)
    if not tickets:
        return t("🎫 Open tickets") + "\n\n" + t("None. 🎉"), kb.tickets_queue([])
    lines = ["🎫 <b>" + t("🎫 Open tickets").replace("🎫 ", "") + "</b>"]
    for ticket in tickets:
        lines.append(
            t(
                "{dot} #{id} · {category} · {uid} · {when}",
                dot="🟡",
                id=esc(ticket["public_id"]),
                category=esc(t(CATEGORY_LABELS.get(ticket["category"], ticket["category"]))),
                uid=format_number(ticket["telegram_id"]),
                when=rel_time(ticket.get("created_at")),
            )
        )
    return "\n".join(lines), kb.tickets_queue(tickets)


async def render_ticket_detail(ticket: dict[str, Any]) -> tuple[str, Any]:
    messages = await q.list_ticket_messages(int(ticket["id"]))
    lines = [
        "🎫 <b>" + t("🎫 Ticket #{public_id}", public_id=esc(ticket["public_id"])).replace("🎫 ", "") + "</b>",
        t("User: {uid}", uid=f"<code>{format_number(ticket['telegram_id'])}</code>"),
        t(
            "Category: {category} · Status: {status}",
            category=esc(t(CATEGORY_LABELS.get(ticket["category"], ticket["category"]))),
            status=f"<b>{esc(t(ticket['status']))}</b>",
        ),
        t(
            "Created: {created} · Updated: {updated}",
            created=rel_time(ticket.get("created_at")),
            updated=rel_time(ticket.get("updated_at")),
        ),
        "",
        f"<i>{esc(ticket.get('description') or t('No description'))}</i>",
    ]
    if messages:
        lines.append("\n" + t("— thread —"))
        for msg in messages:
            role = msg.get("sender_role")
            who = t("👤 User") if role == "user" else (t("🛠 Admin") if role == "admin" else t("⚙️ System"))
            if msg.get("file_path"):
                lines.append(f"{who}: {t('[attachment]')}")
            if msg.get("body"):
                lines.append(f"{who}: {esc(msg['body'])}")
    text = "\n".join(lines)
    return text, kb.ticket_detail(int(ticket["id"]), int(ticket["telegram_id"]), str(ticket["status"]))


async def render_users_page(page: int) -> tuple[str, Any]:
    users = await q.list_users(offset=page * 10, limit=11)
    has_next = len(users) > 10
    users = users[:10]
    text = t("👥 Users — page {page}", page=format_number(page + 1))
    return text, kb.users_page(users, page, has_next)


async def render_unsubscribed_users_page(page: int) -> tuple[str, Any]:
    users = await q.list_users_without_subscriptions(offset=page * 10, limit=11)
    has_next = len(users) > 10
    users = users[:10]
    total = await q.count_users_without_subscriptions()
    text = t(
        "📭 Users without subscription — page {page} · total {total}",
        page=format_number(page + 1),
        total=format_number(total),
    )
    if not users:
        text += "\n\n" + t("🎉 Everyone has a subscription.")
    return text, kb.unsubscribed_users_page(users, page, has_next)


async def render_unlinked_panel_users_page(
    client: RebeccaClient, page: int = 0, *, force: bool = False
) -> tuple[str, Any]:
    items = await scan_unlinked_panel_users(client, force=force)
    total = len(items)
    max_page = max(0, (total - 1) // 10) if total else 0
    page = max(0, min(page, max_page))
    start = page * 10
    subset = items[start:start + 10]
    text = t(
        "🔗 Panel users without Telegram ID — page {page} · total {total}",
        page=format_number(page + 1),
        total=format_number(total),
    )
    if not items:
        text += "\n\n" + t("✅ All panel users have a Telegram ID.")
    return text, kb.unlinked_panel_page(subset, page, start + 10 < total)


async def render_user_detail(telegram_id: int) -> tuple[str, Any]:
    user = await q.get_user(telegram_id)
    if user is None:
        return t("User {uid} not found.", uid=format_number(telegram_id)), kb.back_admin()
    subs = await q.list_subscriptions_for_user(telegram_id)
    paid = await q.user_total_paid(telegram_id)
    access = await q.get_card_access(telegram_id)
    card_status = (access or {}).get("status") or "none"
    text = (
        "👤 <b>" + t("User {uid}", uid=format_number(telegram_id)).replace("👤 ", "") + "</b>\n"
        + t("Username: @{username}", username=esc(user.get("username") or "—")) + "\n"
        + t("Name: {name}", name=esc(user.get("display_name") or "—")) + "\n"
        + t(
            "Joined: {date} · Last seen: {last_seen}",
            date=esc((user.get("joined_at") or "")[:10]),
            last_seen=rel_time(user.get("last_seen_at")),
        ) + "\n"
        + t(
            "Total paid: {paid} · Banned: {banned} · Muted: {muted}",
            paid=fmt_money(paid),
            banned=t("yes") if user.get("banned") else t("no"),
            muted=t("yes") if user.get("mute_broadcasts") else t("no"),
        ) + "\n"
        + t("Subscriptions: {count}", count=format_number(len(subs))) + "\n"
        + t("Card access: {status}", status=t(card_status))
    )
    return text, kb.user_detail(telegram_id, subs, card_status)


def render_user_sub(sub: dict[str, Any]) -> tuple[str, Any]:
    text = (
        "📦 <b>" + esc(sub.get("plan_name") or sub["rebecca_username"]) + "</b>\n"
        + t("Username: {username}", username=f"<code>{esc(sub['rebecca_username'])}</code>") + "\n"
        + t("Status: {status}", status=esc(t(sub.get("status") or "unknown"))) + "\n"
        + t(
            "Traffic: {used} / {total}",
            used=format_gb(sub.get("traffic_used_gb") or 0),
            total=format_gb(sub.get("traffic_total_gb") or 0),
        ) + "\n"
        + t("Expires: {expires}", expires=esc(sub.get("expires_at") or t("n/a")))
    )
    return text, kb.user_sub_actions(int(sub["id"]))


async def render_discounts() -> tuple[str, Any]:
    discounts = await q.list_discounts()
    usage = {d["code"]: await q.count_redemptions(d["code"]) for d in discounts}
    if not discounts:
        text = t("🎁 Discounts") + "\n\n" + t("No codes yet.")
    else:
        lines = ["🎁 <b>" + t("🎁 Discounts").replace("🎁 ", "") + "</b>"]
        for d in discounts:
            lines.append(
                t(
                    "{dot} {code} · {type} {value} · {uses} uses · applies {applies}",
                    dot="🟢" if d.get("active") else "⚫",
                    code=f"<code>{esc(d['code'])}</code>",
                    type=esc(t("percent") if d["type"] == "percent" else t("flat")),
                    value=format_number(d["value"]),
                    uses=format_number(usage.get(d["code"], 0)),
                    applies=esc(t(d["applies_to"])),
                )
            )
        text = "\n".join(lines)
    return text, kb.discounts_list(discounts, usage)


async def render_discount_view(code: str) -> tuple[str, Any]:
    d = await q.get_discount(code)
    if d is None:
        return t("Discount not found."), kb.back_admin()
    usage = await q.count_redemptions(code)
    text = (
        "🎁 <b>" + esc(d["code"]) + "</b>\n"
        + t("Type: {type} · Value: {value}", type=esc(t("percent") if d["type"] == "percent" else t("flat")), value=format_number(d["value"])) + "\n"
        + t("Applies to: {applies}", applies=esc(t(d["applies_to"]))) + "\n"
        + t(
            "Max uses: {max_uses} · Per user: {per_user}",
            max_uses=esc(d.get("max_uses") or "∞"),
            per_user=format_number(d.get("per_user_max")),
        ) + "\n"
        + t(
            "Expires: {expires} · Active: {active}",
            expires=esc(d.get("expires_at") or t("never")),
            active=t("yes") if d.get("active") else t("no"),
        ) + "\n"
        + t("Redemptions: {count}", count=format_number(usage))
    )
    return text, kb.discount_view(code)


def render_broadcast_preview(segment: str, text_body: str, recipients: int, force: bool) -> tuple[str, Any]:
    body = (
        "📢 <b>" + t("📢 Broadcast preview").replace("📢 ", "") + "</b>\n\n"
        + t(
            "Segment: {segment} · Recipients: {count}",
            segment=f"<b>{esc(segment)}</b>",
            count=f"<b>{format_number(recipients)}</b>",
        ) + "\n"
        + t("Force critical: {force}", force=t("yes") if force else t("no")) + "\n\n"
        + t("Message:\n{message}", message=esc(text_body))
    )
    return body, kb.broadcast_preview(force)


async def render_stats(client: Optional[RebeccaClient] = None) -> tuple[str, Any]:
    today = await q.revenue_since("start of day")
    week = await q.revenue_since("-7 days")
    month = await q.revenue_since("-30 days")
    statuses = await q.orders_status_counts_since("-7 days")
    avg_review = await q.avg_review_seconds("-7 days")
    total_users = await q.count_users()
    active_users = await q.count_active_users_since("-7 days")
    new_users = await q.count_users_since("-7 days")
    subs = await q.list_all_subscriptions()
    now = datetime.now(timezone.utc)

    def days_until(value: Optional[str]) -> Optional[int]:
        dt = parse_dt(value)
        return (dt - now).days if dt else None

    active_subs = sum(1 for s in subs if (s.get("status") or "").lower() == "active")
    expiring3 = expiring7 = traffic90 = traffic100 = 0
    for s in subs:
        left = days_until(s.get("expires_at"))
        if left is not None and 0 <= left <= 3:
            expiring3 += 1
        if left is not None and 0 <= left <= 7:
            expiring7 += 1
        total = float(s.get("traffic_total_gb") or 0)
        if total > 0:
            pct = float(s.get("traffic_used_gb") or 0) / total * 100
            if pct >= 100:
                traffic100 += 1
            elif pct >= 90:
                traffic90 += 1

    promos = await q.top_promos(5, "-30 days")
    rate = client.success_rate(300) if client else None
    rate_text = format_number(round(rate * 100)) + "%" if rate is not None else t("n/a")
    pending = await q.list_orders_by_status(PENDING_STATUSES)
    sla_pending = sum(1 for o in pending if age_minutes(o.get("created_at")) > 120)
    open_tickets = await q.list_tickets_by_status(OPEN_TICKET_STATUSES)
    sla_tickets = sum(1 for t_ in open_tickets if age_minutes(t_.get("created_at")) > 1440)
    orders_text = ", ".join(
        f"{t(k)}={format_number(v)}" for k, v in sorted(statuses.items())
    ) or t("none")
    avg_text = (
        f"{format_number(round(avg_review / 60))} " + t("min") if avg_review else t("n/a")
    )

    lines = [
        "📊 <b>" + t("📊 Statistics").replace("📊 ", "") + "</b>",
        t(
            "💰 Revenue today/7d/30d: {today} / {week} / {month}",
            today=fmt_money(today), week=fmt_money(week), month=fmt_money(month),
        ),
        t("🧾 Orders 7d: {orders}", orders=orders_text),
        t("⏱ Avg review time (7d): {value}", value=avg_text),
        t(
            "👥 Users total/active/new-7d: {total} / {active} / {new}",
            total=format_number(total_users), active=format_number(active_users), new=format_number(new_users),
        ),
        t(
            "📦 Subs active/exp3d/exp7d/90%/100%: {active} / {e3} / {e7} / {t90} / {t100}",
            active=format_number(active_subs), e3=format_number(expiring3),
            e7=format_number(expiring7), t90=format_number(traffic90),
            t100=format_number(traffic100),
        ),
        t(
            "🎁 Top promos: {promos}",
            promos=", ".join(f"{p['code']}({format_number(p['uses'])})" for p in promos) or t("none"),
        ),
        t("🔌 Rebecca API success (5m): {rate}", rate=rate_text),
        t(
            "🚨 Funnel: {orders} orders >2h, {tickets} tickets >24h",
            orders=format_number(sla_pending), tickets=format_number(sla_tickets),
        ),
    ]
    return "\n".join(lines), kb.stats_menu()


async def render_alerts(toggles: dict[str, bool]) -> tuple[str, Any]:
    audit = await q.list_audit(limit=10)
    lines = ["🚨 <b>" + t("🚨 Alerts & Logs").replace("🚨 ", "") + "</b>"]
    if audit:
        for row in audit:
            lines.append(
                t(
                    "• {when} · {action} {target} by {admin}",
                    when=rel_time(row.get("created_at")),
                    action=esc(row["action"]),
                    target=esc(f"{row.get('target_type') or ''} {row.get('target_id') or ''}".strip()),
                    admin=format_number(row["admin_id"]),
                )
            )
    else:
        lines.append(t("No audit events yet."))
    return "\n".join(lines), kb.alerts_menu(toggles)


async def render_full_logs(offset: int = 0) -> tuple[str, Any]:
    rows = await q.list_audit(limit=20, offset=offset)
    lines = [t("📜 Audit logs — offset {offset}", offset=format_number(offset))]
    for row in rows:
        lines.append(
            t(
                "{when} · {admin} · {action} · {target}",
                when=esc(row.get("created_at")),
                admin=format_number(row["admin_id"]),
                action=esc(row["action"]),
                target=esc(f"{row.get('target_type') or ''}:{row.get('target_id') or ''}"),
            )
        )
    return "\n".join(lines), kb.back_admin()


async def render_settings() -> tuple[str, Any]:
    plans = await q.list_plans()
    lines = ["⚙️ <b>" + t("⚙️ Settings (read-only)").replace("⚙️ ", "") + "</b>", "", t("Plans:")]
    for plan in plans:
        lines.append(
            t(
                "• {name} · {gb} · {days} · {price} · {status}",
                name=esc(plan["name"]),
                gb=format_gb(plan["gb"]),
                days=format_days(plan["days"]),
                price=fmt_money(plan.get("price_toman")),
                status=t("active") if plan["active"] else t("disabled"),
            )
        )
    return "\n".join(lines), kb.back_admin()


async def render_card_menu() -> tuple[str, Any]:
    config = await get_card_config()
    pending = await q.count_card_requests()
    mode_labels = {
        "all": t("🌍 All users"),
        "request": t("🔐 On request"),
        "none": t("🚫 No automatic access"),
    }
    number = grouped_card(config["number"]) if config["number"] else t("not set")
    lines = [
        "💳 <b>" + t("💳 Payment Card").replace("💳 ", "") + "</b>",
        t("Card number: {number}", number=f"<code>{number}</code>"),
        t("Card holder: {holder}", holder=esc(config["holder"] or t("not set"))),
        t("Mode: {mode}", mode=mode_labels[config["mode"]]),
        t("Pending requests: {count}", count=format_number(pending)),
        "",
        t("🌍 All users: everyone sees the card."),
        t("🔐 On request: returning users see the card; new users request approval."),
        t("🚫 No automatic access: only users you explicitly grant."),
    ]
    return "\n".join(lines), kb.card_menu(config, pending)


async def render_card_requests() -> tuple[str, Any]:
    requests = await q.list_card_requests()
    lines = ["💳 <b>" + t("Card requests").replace("💳 ", "") + "</b>"]
    if not requests:
        lines.append(t("No pending card requests."))
    for item in requests:
        lines.append(
            t(
                "👤 {uid} · @{username} · {when}",
                uid=format_number(item["telegram_id"]),
                username=esc(item.get("username") or "—"),
                when=rel_time(item.get("requested_at")),
            )
        )
    return "\n".join(lines), kb.card_requests_list(requests)


async def render_card_request(telegram_id: int) -> tuple[str, Any]:
    access = await q.get_card_access(telegram_id)
    user = await q.get_user(telegram_id)
    status = (access or {}).get("status") or "none"
    lines = [
        "💳 <b>" + t("Card request").replace("💳 ", "") + "</b>",
        t("User: {uid}", uid=format_number(telegram_id)),
        t("Username: @{username}", username=esc((user or {}).get("username") or "—")),
        t("Status: {status}", status=t(status)),
        t("Requested: {when}", when=rel_time((access or {}).get("requested_at"))),
    ]
    return "\n".join(lines), kb.card_request_detail(telegram_id)
