"""InlineKeyboardMarkup builders for the manager bot."""
from __future__ import annotations

from typing import Any, Iterable

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from core.i18n import format_number, format_toman, t

HOME_BUTTON = "🏠 Home / خانه"


def _kb(rows: Iterable[Iterable[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(row) for row in rows])


def home_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(HOME_BUTTON)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_menu(pending: int, tickets: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("📥 Pending Orders ({count})", count=format_number(pending)), callback_data="orders:pending")],
        [InlineKeyboardButton(t("🎫 Open Tickets ({count})", count=format_number(tickets)), callback_data="tickets:queue")],
        [
            InlineKeyboardButton(t("👥 Users"), callback_data="users:page:0"),
            InlineKeyboardButton(t("📊 Statistics"), callback_data="stats"),
        ],
        [
            InlineKeyboardButton(t("🎁 Discounts"), callback_data="discounts:list"),
            InlineKeyboardButton(t("📢 Broadcast"), callback_data="broadcast:start"),
        ],
        [
            InlineKeyboardButton(t("🚨 Alerts"), callback_data="alerts"),
            InlineKeyboardButton(t("⚙️ Settings"), callback_data="settings"),
        ],
        [InlineKeyboardButton(t("💳 Payment Card"), callback_data="card:menu")],
        [InlineKeyboardButton(t("🌐 Language / زبان"), callback_data="lang:menu")],
    ])


def language() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("🇬🇧 English"), callback_data="lang:set:en")],
        [InlineKeyboardButton(t("🇮🇷 فارسی"), callback_data="lang:set:fa")],
        [InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")],
    ])


def back_admin(extra: Iterable[Iterable[InlineKeyboardButton]] = ()) -> InlineKeyboardMarkup:
    rows = list(extra)
    rows.append([InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")])
    return _kb(rows)


def pending_orders(orders: Iterable[dict[str, Any]], dots: dict[int, str]) -> InlineKeyboardMarkup:
    rows = []
    for order in orders:
        dot = dots.get(int(order["id"]), "🟢")
        rows.append([
            InlineKeyboardButton(
                f"{dot} #{order['public_id']} · {format_number(order['telegram_id'])} · "
                f"{format_toman(order.get('final_price') or 0)}",
                callback_data=f"order:view:{order['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")])
    return _kb(rows)


def order_detail(order_id: int, user_id: int, has_history: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(t("✅ Approve"), callback_data=f"order:approve:{order_id}"),
            InlineKeyboardButton(t("❌ Reject"), callback_data=f"order:reject:{order_id}"),
        ],
        [
            InlineKeyboardButton(t("📸 Ask Resend"), callback_data=f"order:resend:{order_id}"),
            InlineKeyboardButton(t("✏️ Custom Msg"), callback_data=f"order:custom:{order_id}"),
        ],
        [
            InlineKeyboardButton(t("👤 View User"), callback_data=f"user:view:{user_id}:user"),
            InlineKeyboardButton(t("📝 Internal Note"), callback_data=f"order:note:{order_id}"),
        ],
        [InlineKeyboardButton(t("⏱ Under Review"), callback_data=f"order:review:{order_id}")],
    ]
    if has_history:
        rows.append([InlineKeyboardButton(t("🖼 Previous Receipts"), callback_data=f"order:receipts:{order_id}")])
    rows.append([
        InlineKeyboardButton(t("⬅️ Orders"), callback_data="orders:pending"),
        InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home"),
    ])
    return _kb(rows)


def approve_confirm(order_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("✅ Confirm"), callback_data=f"order:approve_confirm:{order_id}")],
        [InlineKeyboardButton(t("✏️ Edit Price"), callback_data=f"order:edit_price:{order_id}")],
        [InlineKeyboardButton(t("⬅️ Back"), callback_data=f"order:view:{order_id}")],
    ])


def reject_reasons(order_id: int) -> InlineKeyboardMarkup:
    reasons = [
        ("unclear", "🧾 Receipt unclear"),
        ("mismatch", "💵 Amount mismatch"),
        ("not_received", "🕐 Payment not received"),
        ("duplicate", "👥 Duplicate"),
        ("fraud", "🚫 Suspected fraud"),
    ]
    rows = [
        [InlineKeyboardButton(t(label), callback_data=f"order:reject_reason:{order_id}:{key}")]
        for key, label in reasons
    ]
    rows.append([InlineKeyboardButton(t("✏️ Custom reason…"), callback_data=f"order:reject_custom:{order_id}")])
    rows.append([InlineKeyboardButton(t("⬅️ Back"), callback_data=f"order:view:{order_id}")])
    return _kb(rows)


def resend_confirm(order_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("✅ Send"), callback_data=f"order:resend_send:{order_id}")],
        [InlineKeyboardButton(t("✏️ Edit"), callback_data=f"order:resend_edit:{order_id}")],
        [InlineKeyboardButton(t("⬅️ Back"), callback_data=f"order:view:{order_id}")],
    ])


def retry_order(order_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("🔄 Retry"), callback_data=f"order:approve_confirm:{order_id}")],
        [InlineKeyboardButton(t("⬅️ Back"), callback_data=f"order:view:{order_id}")],
    ])


def previous_receipts(order_id: int, count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t("Receipt {index}", index=format_number(i + 1)), callback_data=f"order:receipt:{order_id}:{i}")]
        for i in range(count)
    ]
    rows.append([InlineKeyboardButton(t("⬅️ Back"), callback_data=f"order:view:{order_id}")])
    return _kb(rows)


def tickets_queue(tickets: Iterable[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for ticket in tickets:
        rows.append([
            InlineKeyboardButton(
                f"🟡 #{ticket['public_id']} · {t(ticket['category'])} · {format_number(ticket['telegram_id'])}",
                callback_data=f"ticket:view:{ticket['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")])
    return _kb(rows)


def ticket_detail(ticket_id: int, user_id: int, status: str) -> InlineKeyboardMarkup:
    terminal = status in {"closed", "resolved"}
    rows = []
    if not terminal:
        rows.append([
            InlineKeyboardButton(t("🟡 In Progress"), callback_data=f"ticket:status:{ticket_id}:in_progress"),
            InlineKeyboardButton(t("✅ Resolve"), callback_data=f"ticket:status:{ticket_id}:resolved"),
        ])
        rows.append([
            InlineKeyboardButton(t("❌ Close"), callback_data=f"ticket:status:{ticket_id}:closed"),
            InlineKeyboardButton(t("💬 Reply"), callback_data=f"ticket:reply:{ticket_id}"),
        ])
        rows.append([
            InlineKeyboardButton(t("✏️ Custom Msg"), callback_data=f"ticket:custom:{ticket_id}"),
            InlineKeyboardButton(t("👤 View User"), callback_data=f"user:view:{user_id}:user"),
        ])
    rows.append([
        InlineKeyboardButton(t("⬅️ Tickets"), callback_data="tickets:queue"),
        InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home"),
    ])
    return _kb(rows)


def users_page(users: Iterable[dict[str, Any]], page: int, has_next: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"{format_number(user['telegram_id'])} · @{user.get('username') or '—'}"
            + (" 🚫" if user.get("banned") else ""),
            callback_data=f"user:view:{user['telegram_id']}:user",
        )]
        for user in users
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(t("⬅️ Prev"), callback_data=f"users:page:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(t("Next ➡️"), callback_data=f"users:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(t("📭 Without subscription"), callback_data="users:nosub:page:0")])
    rows.append([InlineKeyboardButton(t("🔗 Panel without Telegram ID"), callback_data="panel:unlinked:page:0")])
    rows.append([InlineKeyboardButton(t("🔎 Search"), callback_data="user:search")])
    rows.append([InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")])
    return _kb(rows)


def unsubscribed_users_page(
    users: Iterable[dict[str, Any]], page: int, has_next: bool
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"📭 {format_number(user['telegram_id'])} · @{user.get('username') or '—'}",
            callback_data=f"user:view:{user['telegram_id']}:user",
        )]
        for user in users
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(t("⬅️ Prev"), callback_data=f"users:nosub:page:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(t("Next ➡️"), callback_data=f"users:nosub:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton(t("⬅️ Users"), callback_data="users:page:0"),
        InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home"),
    ])
    return _kb(rows)


def unlinked_panel_page(
    users: Iterable[dict[str, Any]], page: int, has_next: bool
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            f"🔓 {user['username']} · {user.get('service_name') or '—'} · {t(user.get('status') or 'unknown')}",
            callback_data=f"panel:link:{user['username']}",
        )]
        for user in users
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(t("⬅️ Prev"), callback_data=f"panel:unlinked:page:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(t("Next ➡️"), callback_data=f"panel:unlinked:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(t("↻ Refresh"), callback_data="panel:unlinked:refresh")])
    rows.append([
        InlineKeyboardButton(t("⬅️ Users"), callback_data="users:page:0"),
        InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home"),
    ])
    return _kb(rows)


def user_detail(
    user_id: int, subs: Iterable[dict[str, Any]], card_status: str = "none"
) -> InlineKeyboardMarkup:
    rows = []
    for sub in subs:
        rows.append([
            InlineKeyboardButton(
                f"📦 {sub.get('plan_name') or sub['rebecca_username']} · {t(sub.get('status') or 'unknown')}",
                callback_data=f"usub:{sub['id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton(t("🧾 Orders"), callback_data=f"user:orders:{user_id}"),
        InlineKeyboardButton(t("🎫 Tickets"), callback_data=f"user:tickets:{user_id}"),
    ])
    rows.append([
        InlineKeyboardButton(t("🚫 Ban/Unban"), callback_data=f"user:ban:{user_id}"),
        InlineKeyboardButton(t("✉️ Send DM"), callback_data=f"user:dm:{user_id}"),
    ])
    card_label = (
        "✅ Revoke card access" if card_status == "approved" else "💳 Grant card access"
    )
    rows.append([
        InlineKeyboardButton(t(card_label), callback_data=f"user:card:{user_id}")
    ])
    rows.append([
        InlineKeyboardButton(t("⬅️ Users"), callback_data="users:page:0"),
        InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home"),
    ])
    return _kb(rows)


def card_menu(config: dict[str, Any], pending: int) -> InlineKeyboardMarkup:
    mode = config.get("mode") or "request"

    def label(mode_name: str, text: str) -> str:
        return ("✅ " if mode == mode_name else "") + t(text)

    return _kb([
        [InlineKeyboardButton(t("✏️ Edit card number"), callback_data="card:edit:number")],
        [InlineKeyboardButton(t("👤 Edit card holder"), callback_data="card:edit:holder")],
        [InlineKeyboardButton(label("all", "🌍 All users"), callback_data="card:mode:all")],
        [InlineKeyboardButton(label("request", "🔐 On request"), callback_data="card:mode:request")],
        [InlineKeyboardButton(label("none", "🚫 No automatic access"), callback_data="card:mode:none")],
        [InlineKeyboardButton(
            t("📥 Pending requests ({count})", count=format_number(pending)),
            callback_data="card:requests",
        )],
        [InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")],
    ])


def card_requests_list(requests: Iterable[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for item in requests:
        rows.append([
            InlineKeyboardButton(
                f"👤 {format_number(item['telegram_id'])} · @{item.get('username') or '—'}",
                callback_data=f"card:request:{item['telegram_id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton(t("⬅️ Payment Card"), callback_data="card:menu"),
        InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home"),
    ])
    return _kb(rows)


def card_request_detail(telegram_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [
            InlineKeyboardButton(t("✅ Approve"), callback_data=f"card:approve:{telegram_id}"),
            InlineKeyboardButton(t("❌ Reject"), callback_data=f"card:reject:{telegram_id}"),
        ],
        [
            InlineKeyboardButton(t("⬅️ Requests"), callback_data="card:requests"),
            InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home"),
        ],
    ])


def user_sub_actions(sub_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("➕ Extend +7d"), callback_data=f"usub:act:{sub_id}:extend7"),
         InlineKeyboardButton(t("➕ Extend +30d"), callback_data=f"usub:act:{sub_id}:extend30")],
        [InlineKeyboardButton(t("✏️ Extend Custom"), callback_data=f"usub:act:{sub_id}:extend_custom"),
         InlineKeyboardButton(t("➕ Traffic +5/10/50"), callback_data=f"usub:act:{sub_id}:traffic")],
        [InlineKeyboardButton(t("✏️ Traffic Custom"), callback_data=f"usub:act:{sub_id}:traffic_custom"),
         InlineKeyboardButton(t("♻️ Reset Traffic"), callback_data=f"usub:act:{sub_id}:reset")],
        [InlineKeyboardButton(t("⏸ Disable"), callback_data=f"usub:act:{sub_id}:disable"),
         InlineKeyboardButton(t("▶️ Enable"), callback_data=f"usub:act:{sub_id}:enable")],
        [InlineKeyboardButton(t("🗑 Delete"), callback_data=f"usub:act:{sub_id}:delete")],
        [InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")],
    ])


def traffic_amounts(sub_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("+5 GB", callback_data=f"usub:act:{sub_id}:add5"),
         InlineKeyboardButton("+10 GB", callback_data=f"usub:act:{sub_id}:add10"),
         InlineKeyboardButton("+50 GB", callback_data=f"usub:act:{sub_id}:add50")],
        [InlineKeyboardButton(t("⬅️ Back"), callback_data=f"usub:{sub_id}")],
    ])


def discounts_list(discounts: Iterable[dict[str, Any]], usage: dict[str, int]) -> InlineKeyboardMarkup:
    rows = []
    for d in discounts:
        state = "🟢" if d.get("active") else "⚫"
        rows.append([
            InlineKeyboardButton(
                f"{state} {d['code']} · {t(d['type'])} {format_number(d['value'])} · {format_number(usage.get(d['code'], 0))}",
                callback_data=f"discount:view:{d['code']}",
            )
        ])
    rows.append([InlineKeyboardButton(t("➕ New Discount"), callback_data="discount:new")])
    rows.append([InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")])
    return _kb(rows)


def discount_view(code: str) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("🔁 Toggle Active"), callback_data=f"discount:toggle:{code}")],
        [InlineKeyboardButton(t("🗑 Delete"), callback_data=f"discount:delete:{code}")],
        [InlineKeyboardButton(t("⬅️ Discounts"), callback_data="discounts:list")],
        [InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")],
    ])


def discount_type() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("Percent"), callback_data="discount:type:percent"),
         InlineKeyboardButton(t("Flat (Toman)"), callback_data="discount:type:flat")],
    ])


def discount_applies(plans: Iterable[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t("All plans"), callback_data="discount:applies:all")]]
    for plan in plans:
        rows.append([InlineKeyboardButton(
            f"{plan['name']} · {format_number(plan['gb'])}GB", callback_data=f"discount:applies:{plan['id']}"
        )])
    return _kb(rows)


def broadcast_segments() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("◉ All users"), callback_data="broadcast:seg:all")],
        [InlineKeyboardButton(t("○ Active users"), callback_data="broadcast:seg:active")],
        [InlineKeyboardButton(t("○ Expiring ≤7d"), callback_data="broadcast:seg:expiring")],
        [InlineKeyboardButton(t("○ Traffic ≥90%"), callback_data="broadcast:seg:traffic")],
        [InlineKeyboardButton(t("○ Custom list"), callback_data="broadcast:seg:custom")],
        [InlineKeyboardButton(t("⬅️ Back"), callback_data="home")],
    ])


def broadcast_preview(force: bool) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("☑ Force critical") if force else t("☐ Force critical"), callback_data="broadcast:force")],
        [InlineKeyboardButton(t("📤 Send Now"), callback_data="broadcast:send")],
        [InlineKeyboardButton(t("⬅️ Back"), callback_data="broadcast:start")],
    ])


def stats_menu() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("📤 Export CSV"), callback_data="stats:export")],
        [InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")],
    ])


def alerts_menu(toggles: dict[str, bool]) -> InlineKeyboardMarkup:
    labels = {
        "new_order": "New order alerts",
        "new_ticket": "New ticket alerts",
        "sla_breach": "SLA breach alerts",
        "api_errors": "API error alerts",
        "daily_digest": "Daily digest",
        "weekly_digest": "Weekly digest",
    }
    rows = [
        [InlineKeyboardButton(
            f"{'✅' if toggles.get(key, True) else '⬜'} {t(label)}",
            callback_data=f"alerts:toggle:{key}",
        )]
        for key, label in labels.items()
    ]
    rows.append([InlineKeyboardButton(t("📜 Full Logs"), callback_data="alerts:logs")])
    rows.append([InlineKeyboardButton(t("🏠 Admin Menu"), callback_data="home")])
    return _kb(rows)


def cancel() -> InlineKeyboardMarkup:
    return _kb([[InlineKeyboardButton(t("✖️ Cancel"), callback_data="cancel")]])
