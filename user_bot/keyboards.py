"""All InlineKeyboardMarkup builders for the user bot."""
from __future__ import annotations

from typing import Any, Iterable

from telegram import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from core.i18n import t

HOME_BUTTON = "🏠 Home / خانه"


def _kb(rows: Iterable[Iterable[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(row) for row in rows])


def home_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(HOME_BUTTON)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu(unread: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("📦 My Subscriptions"), callback_data="subs:list")],
        [InlineKeyboardButton(t("🛒 Buy"), callback_data="buy:start")],
        [InlineKeyboardButton(t("🆘 Report Issue"), callback_data="ticket:new")],
        [InlineKeyboardButton(t("🤖 AI Assistant"), callback_data="ai:start")],
        [InlineKeyboardButton(t("🎁 Invite Friends"), callback_data="referrals")],
        [InlineKeyboardButton(t("🔔 Notifications ({unread})", unread=str(unread)), callback_data="notif:list")],
        [InlineKeyboardButton(t("❓ Help"), callback_data="help")],
        [InlineKeyboardButton(t("🌐 Language / زبان"), callback_data="lang:menu")],
    ])


def language() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("🇬🇧 English"), callback_data="lang:set:en")],
        [InlineKeyboardButton(t("🇮🇷 فارسی"), callback_data="lang:set:fa")],
        [InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")],
    ])


def back_home() -> InlineKeyboardMarkup:
    return _kb([[InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")]])


def back_and_home(back_data: str, back_label: str = "⬅️ Back") -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t(back_label), callback_data=back_data)],
        [InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")],
    ])


def subs_list(subs: Iterable[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for sub in subs:
        dot = sub.get("_dot", "•")
        label = (
            f"{dot} {sub.get('display_name') or sub.get('plan_name') or sub['rebecca_username']}"
        )
        rows.append([InlineKeyboardButton(label, callback_data=f"sub:view:{sub['id']}")])
    rows.append([InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")])
    return _kb(rows)


def sub_detail(sub_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [
            InlineKeyboardButton(t("📱 QR"), callback_data=f"sub:qr:{sub_id}"),
            InlineKeyboardButton(t("🔗 URL"), callback_data=f"sub:url:{sub_id}"),
        ],
        [
            InlineKeyboardButton(t("🔄 Refresh"), callback_data=f"sub:refresh:{sub_id}"),
            InlineKeyboardButton(t("✏️ Rename"), callback_data=f"sub:rename:{sub_id}"),
        ],
        [
            InlineKeyboardButton(t("🔄 Renew"), callback_data=f"sub:renew:{sub_id}"),
            InlineKeyboardButton(t("🎁 Transfer"), callback_data=f"sub:transfer:{sub_id}"),
        ],
        [
            InlineKeyboardButton(t("⬅️ Back"), callback_data="subs:list"),
            InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home"),
        ],
    ])


def plans(plan_rows: Iterable[tuple[int, str]]) -> InlineKeyboardMarkup:
    """plan_rows: iterable of (plan_id, label)."""
    rows = [[InlineKeyboardButton(label, callback_data=f"buy:plan:{plan_id}")] for plan_id, label in plan_rows]
    rows.append([InlineKeyboardButton(t("🎁 Enter Promo"), callback_data="buy:promo")])
    rows.append([InlineKeyboardButton(t("🎟 Invitation Code"), callback_data="buy:invite")])
    rows.append([InlineKeyboardButton(t("⬅️ Back"), callback_data="menu:home")])
    return _kb(rows)


def referral_menu(code: str, link: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t("📋 Copy code"), copy_text=CopyTextButton(code))]
    ]
    if link:
        rows.append([
            InlineKeyboardButton(
                t("🔗 Copy invite link"), copy_text=CopyTextButton(link)
            )
        ])
    rows.append([InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")])
    return _kb(rows)


def payment(
    card_number: str = "",
    *,
    can_request: bool = False,
    pending: bool = False,
    renewal_sub_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    if card_number:
        rows.append([
            InlineKeyboardButton(
                t("📋 Copy card number"),
                copy_text=CopyTextButton(card_number),
            )
        ])
    elif pending:
        rows.append([
            InlineKeyboardButton(t("🔄 Check card request"), callback_data="pay:card_refresh")
        ])
    elif can_request:
        rows.append([
            InlineKeyboardButton(t("📩 Request card number"), callback_data="pay:card_request")
        ])
    rows.append([
        InlineKeyboardButton(t("📸 I Paid – Send Receipt"), callback_data="pay:receipt")
    ])
    if renewal_sub_id is not None:
        rows.append([
            InlineKeyboardButton(
                t("⬅️ Back to subscription"),
                callback_data=f"sub:view:{renewal_sub_id}",
            )
        ])
    else:
        rows.extend([
            [InlineKeyboardButton(t("✏️ Change Promo"), callback_data="buy:promo")],
            [InlineKeyboardButton(t("⬅️ Back"), callback_data="buy:start")],
        ])
    rows.append([InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")])
    return _kb(rows)


def cancel_only() -> InlineKeyboardMarkup:
    return _kb([[InlineKeyboardButton(t("✖️ Cancel"), callback_data="cancel")]])


def ticket_categories(categories: Iterable[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t(label), callback_data=f"ticket:cat:{key}")] for key, label in categories]
    rows.append([InlineKeyboardButton(t("⬅️ Back"), callback_data="menu:home")])
    return _kb(rows)


def tickets_list(tickets: Iterable[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for ticket in tickets:
        dot = ticket.get("_dot", "•")
        rows.append([
            InlineKeyboardButton(
                f"{dot} #{ticket['public_id']} · {t(ticket['category'])}",
                callback_data=f"ticket:view:{ticket['id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton(t("➕ New Ticket"), callback_data="ticket:new"),
        InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home"),
    ])
    return _kb(rows)


def ticket_detail(ticket_id: int, status: str) -> InlineKeyboardMarkup:
    terminal = status in {"closed", "resolved"}
    rows = []
    if not terminal:
        rows.append([
            InlineKeyboardButton(t("💬 Reply"), callback_data=f"ticket:reply:{ticket_id}"),
            InlineKeyboardButton(t("❌ Close Ticket"), callback_data=f"ticket:close:{ticket_id}"),
        ])
    rows.append([
        InlineKeyboardButton(t("⬅️ My Tickets"), callback_data="tickets:list"),
        InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home"),
    ])
    return _kb(rows)


def notifications_list(notifs: Iterable[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for notif in notifs:
        icon = "📩" if not notif.get("is_read") else "✅"
        rows.append([
            InlineKeyboardButton(
                f"{icon} {notif['title'][:40]}",
                callback_data=f"notif:view:{notif['id']}",
            )
        ])
    rows.append([
        InlineKeyboardButton(t("✅ Mark All Read"), callback_data="notif:readall"),
        InlineKeyboardButton(t("🔕 Mute Broadcasts"), callback_data="notif:mute"),
    ])
    rows.append([InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")])
    return _kb(rows)


def notification_detail(notification_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("⬅️ Inbox"), callback_data="notif:list")],
        [InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home")],
    ])


def ai_footer() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("🆘 Create Ticket"), callback_data="ticket:new")],
        [
            InlineKeyboardButton(t("🧹 Clear Chat"), callback_data="ai:clear"),
            InlineKeyboardButton(t("🏠 Main Menu"), callback_data="menu:home"),
        ],
    ])


def transfer_decision(transfer_id: int) -> InlineKeyboardMarkup:
    return _kb([
        [
            InlineKeyboardButton(t("✅ Accept"), callback_data=f"transfer:accept:{transfer_id}"),
            InlineKeyboardButton(t("❌ Decline"), callback_data=f"transfer:decline:{transfer_id}"),
        ],
    ])


def resend_receipt(public_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton(t("📸 Re-upload Receipt"), callback_data=f"resend:{public_id}")],
    ])
