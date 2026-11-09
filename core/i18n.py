"""Bilingual (English/Persian) text, number and currency helpers.

Templates are written as their English text and looked up in the Persian
catalog. Unknown templates fall back to English, so a missing translation never
raises. The active language is carried in a ContextVar set per Telegram update.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

SUPPORTED = ("en", "fa")
DEFAULT = "en"

_LANG: ContextVar[str] = ContextVar("moot_lang", default=DEFAULT)

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def normalize_lang(code: Optional[str]) -> str:
    if code and str(code).lower().startswith("fa"):
        return "fa"
    return "en"


def set_lang(lang: Optional[str]) -> None:
    _LANG.set(lang if lang in SUPPORTED else DEFAULT)


def get_lang() -> str:
    return _LANG.get()


@contextmanager
def use_lang(lang: Optional[str]) -> Iterator[None]:
    token = _LANG.set(lang if lang in SUPPORTED else DEFAULT)
    try:
        yield
    finally:
        _LANG.reset(token)


def language_name(lang: str) -> str:
    return "فارسی" if lang == "fa" else "English"


FA: dict[str, str] = {
    # ---- common ----
    "⬅️ Back": "⬅️ بازگشت",
    "🏠 Main Menu": "🏠 منوی اصلی",
    "✖️ Cancel": "✖️ لغو",
    "Cancelled.": "لغو شد.",
    "Unknown plan.": "پلن ناشناخته است.",
    "ok": "تایید",
    "no expiry": "بدون انقضا",
    "n/a": "نامشخص",
    "none": "هیچ",
    "unknown": "نامشخص",
    # ---- language ----
    "🌐 Language / زبان": "🌐 زبان / Language",
    "Choose your language:": "زبان خود را انتخاب کنید:",
    "🇬🇧 English": "🇬🇧 English",
    "🇮🇷 فارسی": "🇮🇷 فارسی",
    "Language set.": "زبان تغییر کرد.",
    # ---- main menu ----
    "👋 Loading…": "👋 در حال بارگذاری…",
    "Welcome back! Choose an option below.": "خوش آمدید! یکی از گزینه‌ها را انتخاب کنید.",
    "👤 {uid} · 📦 {active}/{total} · 🔔 {unread}": "👤 {uid} · 📦 {active}/{total} · 🔔 {unread}",
    "📦 My Subscriptions": "📦 اشتراک‌های من",
    "🛒 Buy": "🛒 خرید",
    "🆘 Report Issue": "🆘 گزارش مشکل",
    "🤖 AI Assistant": "🤖 دستیار هوشمند",
    "🔔 Notifications ({unread})": "🔔 اعلان‌ها ({unread})",
    "❓ Help": "❓ راهنما",
    "Use the buttons below to navigate.\n\n{menu}": "از دکمه‌های زیر استفاده کنید.\n\n{menu}",
    # ---- subscriptions ----
    "📦 My Subscriptions": "📦 اشتراک‌های من",
    "📦 You have no subscriptions yet.\n\nTap 🛒 Buy to get started.": "📦 هنوز اشتراکی ندارید.\n\nبرای شروع 🛒 خرید را بزنید.",
    "{dot} {name}": "{dot} {name}",
    "   {remaining} GB left · {days}": "   {remaining} گیگابایت باقی‌مانده · {days}",
    "📱 QR": "📱 QR",
    "🔗 URL": "🔗 لینک",
    "🔄 Refresh": "🔄 بروزرسانی",
    "Refreshing…": "در حال بروزرسانی…",
    "Status: {status}": "وضعیت: {status}",
    "Traffic: {used} / {total} GB used ({remaining} GB left)": "ترافیک: {used} / {total} گیگابایت مصرف‌شده ({remaining} گیگابایت باقی‌مانده)",
    "Expires: {expires} ({days})": "انقضا: {expires} ({days})",
    "Username: {username}": "نام کاربری: {username}",
    "Subscription not found.": "اشتراک پیدا نشد.",
    "✏️ Rename": "✏️ تغییر نام",
    "✏️ Send a new name for this subscription (max {max} characters), or /cancel.": "✏️ نام جدیدی برای این اشتراک بفرستید (حداکثر {max} کاراکتر)، یا /cancel.",
    "Please send a non-empty subscription name.": "لطفاً یک نام غیرخالی برای اشتراک بفرستید.",
    "Subscription name is too long. Maximum {max} characters.": "نام اشتراک طولانی است. حداکثر {max} کاراکتر.",
    "✅ Subscription name updated.": "✅ نام اشتراک به‌روزرسانی شد.",
    "No subscription URL available yet.": "لینک اشتراک هنوز موجود نیست.",
    "📱 QR for {name}": "📱 QR برای {name}",
    "🔗 Open subscription URL": "🔗 باز کردن لینک اشتراک",
    # ---- buy / payment ----
    "🛒 Choose a plan": "🛒 انتخاب پلن",
    "Promo {code} applied.": "کد تخفیف {code} اعمال شد.",
    "No plans are available right now.": "در حال حاضر پلنی موجود نیست.",
    "🎁 Enter Promo": "🎁 وارد کردن کد تخفیف",
    "🎁 Send your promo code as a message, or tap Cancel.": "کد تخفیف را ارسال کنید، یا لغو را بزنید.",
    "Send another code or tap Cancel.": "کد دیگری ارسال کنید یا لغو را بزنید.",
    "Invalid promo code.": "کد تخفیف نامعتبر است.",
    "This promo code is no longer active.": "این کد تخفیف دیگر فعال نیست.",
    "This promo code has expired.": "این کد تخفیف منقضی شده است.",
    "This promo code does not apply to the selected plan.": "این کد تخفیف برای پلن انتخاب‌شده معتبر نیست.",
    "This promo code has reached its usage limit.": "این کد تخفیف به سقف استفاده رسیده است.",
    "You have already used this promo code.": "شما قبلاً از این کد تخفیف استفاده کرده‌اید.",
    "💳 Pay by card": "💳 پرداخت با کارت",
    "Card number: {number}": "شماره کارت: {number}",
    "Card holder: {holder}": "نام دارنده کارت: {holder}",
    "📋 Copy card number": "📋 کپی شماره کارت",
    "🧾 Payment details": "🧾 جزئیات پرداخت",
    "Plan: {plan}": "پلن: {plan}",
    "List price: {price}": "قیمت پایه: {price}",
    "Volume discount ({percent}): -{amount}": "تخفیف حجمی ({percent}): -{amount}",
    "Discount ({code}): -{amount}": "تخفیف ({code}): -{amount}",
    "Total: {total}": "مبلغ نهایی: {total}",
    " (you save {amount})": " (صرفه‌جویی {amount})",
    "After paying, send a screenshot of your payment transaction below.": "پس از پرداخت، اسکرین‌شات تراکنش را در ادامه ارسال کنید.",
    "✏️ Change Promo": "✏️ تغییر کد تخفیف",
    "📸 I Paid – Send Receipt": "📸 پرداخت کردم – ارسال رسید",
    "📸 Send a screenshot of your payment transaction (max 20 MB), or /cancel.": "📸 اسکرین‌شات تراکنش پرداخت را ارسال کنید (حداکثر ۲۰ مگابایت)، یا /cancel.",
    "Please send the payment screenshot (image), or /cancel.": "لطفاً اسکرین‌شات پرداخت (تصویر) را ارسال کنید، یا /cancel.",
    "📸 Please upload a screenshot of your payment transaction.": "📸 لطفاً اسکرین‌شات تراکنش پرداخت را ارسال کنید.",
    "✅ Receipt received. Order #{public_id}, awaiting review.": "✅ رسید دریافت شد. سفارش #{public_id}، در انتظار بررسی.",
    "✅ New receipt received for order #{public_id}. Awaiting review.": "✅ رسید جدید برای سفارش #{public_id} دریافت شد. در انتظار بررسی.",
    "Please send a screenshot (image).": "لطفاً اسکرین‌شات (تصویر) ارسال کنید.",
    "Please send a screenshot (image) of the payment.": "لطفاً اسکرین‌شات (تصویر) پرداخت را ارسال کنید.",
    "File is too large. Maximum size is 20 MB.": "حجم فایل زیاد است. حداکثر ۲۰ مگابایت.",
    "That plan is no longer available.": "این پلن دیگر موجود نیست.",
    "Order not found.": "سفارش پیدا نشد.",
    "No upload expected right now. Use /start for the menu.": "در حال حاضر آپلودی لازم نیست. برای منو /start را بزنید.",
    "Please choose a plan first.": "لطفاً ابتدا یک پلن انتخاب کنید.",
    # ---- tickets ----
    "🆘 Report an issue\n\nChoose a category:": "🆘 گزارش مشکل\n\nیک دسته را انتخاب کنید:",
    "Describe the issue, or /skip. You may attach a screenshot.": "مشکل را توضیح دهید، یا /skip. می‌توانید اسکرین‌شات هم بفرستید.",
    "🎫 Ticket #{public_id} created.": "🎫 تیکت #{public_id} ایجاد شد.",
    "🎫 My Tickets": "🎫 تیکت‌های من",
    "🎫 You have no tickets.": "🎫 تیکتی ندارید.",
    "🎫 Ticket #{public_id}": "🎫 تیکت #{public_id}",
    "Category: {category}": "دسته: {category}",
    "No description": "بدون توضیح",
    "— thread —": "— گفتگو —",
    "👤 You": "👤 شما",
    "🛠 Support": "🛠 پشتیبانی",
    "[attachment]": "[پیوست]",
    "💬 Reply": "💬 پاسخ",
    "❌ Close Ticket": "❌ بستن تیکت",
    "➕ New Ticket": "➕ تیکت جدید",
    "Send your reply, or /cancel.": "پاسخ خود را ارسال کنید، یا /cancel.",
    "Ticket closed.": "تیکت بسته شد.",
    "Ticket not found.": "تیکت پیدا نشد.",
    "Nothing to skip. Use /start to open the menu.": "چیزی برای رد کردن نیست. برای منو /start را بزنید.",
    # ticket categories
    "📶 No ping / high latency": "📶 پینگ ندارد / تاخیر بالا",
    "🌐 Server unreachable": "🌐 سرور در دسترس نیست",
    "🐢 Slow speed": "🐢 سرعت پایین",
    "📱 App won't connect": "📱 برنامه وصل نمی‌شود",
    "💳 Payment problem": "💳 مشکل پرداخت",
    "✏️ Other": "✏️ سایر",
    # ---- notifications ----
    "🔔 Notifications": "🔔 اعلان‌ها",
    "🔔 No notifications yet.": "🔔 هنوز اعلانی ندارید.",
    "✅ Mark All Read": "✅ خواندن همه",
    "🔕 Mute Broadcasts": "🔕 قطع اعلان‌های عمومی",
    "Broadcasts muted.": "اعلان‌های عمومی قطع شد.",
    "Broadcasts unmuted.": "اعلان‌های عمومی وصل شد.",
    "Marked all as read.": "همه خوانده شدند.",
    "Notification not found.": "اعلان پیدا نشد.",
    # ---- help ----
    "❓ Help": "❓ راهنما",
    "Help": "راهنما",
    "Commands:": "دستورها:",
    "/start — open the main menu": "/start — باز کردن منوی اصلی",
    "/cancel — abort the current flow": "/cancel — لغو مرحله فعلی",
    "/help — show this message": "/help — نمایش این پیام",
    "/language — change language": "/language — تغییر زبان",
    "Use the inline buttons to manage subscriptions, buy a plan, open a ticket, chat with the AI assistant, and read notifications.": "از دکمه‌ها برای مدیریت اشتراک‌ها، خرید پلن، ارسال تیکت، گفتگو با دستیار و خواندن اعلان‌ها استفاده کنید.",
    "To connect: open My Subscriptions → tap a subscription → QR or URL.": "برای اتصال: اشتراک‌های من → یک اشتراک → QR یا لینک.",
    # ---- AI ----
    "🤖 AI Assistant": "🤖 دستیار هوشمند",
    "🆘 Create Ticket": "🆘 ایجاد تیکت",
    "🧹 Clear Chat": "🧹 پاک کردن گفتگو",
    "⏳ You have reached the AI limit (20 messages/hour). Please try again later, or use 🆘 Report Issue.": "⏳ به سقف پیام دستیار (۲۰ پیام در ساعت) رسیده‌اید. بعداً تلاش کنید یا از 🆘 گزارش مشکل استفاده کنید.",
    "The AI assistant is temporarily unavailable. Please use 🆘 Report Issue and our team will help.": "دستیار هوشمند موقتاً در دسترس نیست. لطفاً از 🆘 گزارش مشکل استفاده کنید.",
    "Chat cleared.": "گفتگو پاک شد.",
    # ---- job notifications ----
    "Subscription expired: {label}": "اشتراک منقضی شد: {label}",
    "Your subscription has expired. Open My Subscriptions to renew.": "اشتراک شما منقضی شده است. برای تمدید اشتراک‌های من را باز کنید.",
    "Subscription expiring in {days} day(s): {label}": "اشتراک تا {days} روز دیگر منقضی می‌شود: {label}",
    "Renew soon to avoid losing access.": "برای جلوگیری از قطع دسترسی به‌زودی تمدید کنید.",
    "Traffic exhausted: {label}": "ترافیک تمام شد: {label}",
    "You have used 100% of your traffic.": "۱۰۰٪ ترافیک شما مصرف شده است.",
    "Traffic at {percent}: {label}": "ترافیک در {percent}: {label}",
    "You have used over 90% of your traffic.": "بیش از ۹۰٪ ترافیک شما مصرف شده است.",
    "📢 Announcement": "📢 اطلاعیه",
    # ---- cross-bot order notifications ----
    "Order #{public_id} approved": "سفارش #{public_id} تایید شد",
    "Your subscription is ready. Plan: {plan}.\n{url}": "اشتراک شما آماده است. پلن: {plan}.\n{url}",
    "Order #{public_id} rejected": "سفارش #{public_id} رد شد",
    "Reason: {reason}": "دلیل: {reason}",
    "New receipt needed for #{public_id}": "نیاز به رسید جدید برای #{public_id}",
    "Message from support": "پیام از پشتیبانی",
    "Reply on ticket #{public_id}": "پاسخ در تیکت #{public_id}",
    "Message about ticket #{public_id}": "پیام درباره تیکت #{public_id}",
    "Ticket #{public_id} {status}": "تیکت #{public_id} {status}",
    "Your ticket status is now {status}.": "وضعیت تیکت شما اکنون {status} است.",
    # ---- additional user templates ----
    "{name} · {gb} · {days}": "{name} · {gb} · {days}",
    "• {label} — {base} → {final}": "• {label} — {final} (قبلاً {base})",
    "• {label} — {final}": "• {label} — {final}",
    "{dot} <b>{name}</b>\n   {remaining} left · {days}": "{dot} <b>{name}</b>\n   {remaining} باقی‌مانده · {days}",
    "Traffic: {used} / {total} used ({remaining} left)": "ترافیک: {used} / {total} مصرف‌شده ({remaining} باقی‌مانده)",
    "{dot} #{id} · {category} · {status}": "{dot} #{id} · {category} · {status}",
    "❌ {reason}\n\nSend another code or tap Cancel.": "❌ {reason}\n\nکد دیگری ارسال کنید یا لغو را بزنید.",
    "Ask me anything about plans, connecting, or using the service. I can't approve payments or promise refunds — for account issues use 🆘 Report Issue.": "درباره پلن‌ها، اتصال یا استفاده از سرویس بپرسید. من نمی‌توانم پرداخت را تایید کنم یا وعده بازگشت وجه بدهم — برای مشکلات حساب از 🆘 گزارش مشکل استفاده کنید.",
    "Send a message to begin. /cancel or the Main Menu button exits.": "برای شروع یک پیام بفرستید. /cancel یا دکمه منوی اصلی خارج می‌شود.",
    "📸 Re-upload Receipt": "📸 ارسال دوباره رسید",
    "⬅️ Inbox": "⬅️ صندوق",
    "⬅️ My Tickets": "⬅️ تیکت‌های من",
    "Order #{public_id} received": "سفارش #{public_id} دریافت شد",
    "Plan {plan} · {amount}. We will review your receipt shortly.": "پلن {plan} · {amount}. رسید شما به‌زودی بررسی می‌شود.",
    "New receipt for #{public_id}": "رسید جدید برای #{public_id}",
    "A user re-uploaded a receipt. Review the order.": "کاربر رسیدی دوباره ارسال کرد. سفارش را بررسی کنید.",
    "Open subscription URL": "باز کردن لینک اشتراک",
}

# ---- manager UI ----
FA.update({
    "🛠 Admin Menu": "🛠 منوی مدیریت",
    "📥 Pending Orders ({count})": "📥 سفارش‌های در انتظار ({count})",
    "🎫 Open Tickets ({count})": "🎫 تیکت‌های باز ({count})",
    "👥 Users": "👥 کاربران",
    "📊 Statistics": "📊 آمار",
    "🎁 Discounts": "🎁 کدهای تخفیف",
    "📢 Broadcast": "📢 ارسال همگانی",
    "🚨 Alerts": "🚨 هشدارها",
    "⚙️ Settings": "⚙️ تنظیمات",
    "🔔 Pending orders: {count}": "🔔 سفارش‌های در انتظار: {count}",
    "🎫 Open tickets: {count}": "🎫 تیکت‌های باز: {count}",
    "💰 Revenue today: {amount}": "💰 درآمد امروز: {amount}",
    "💰 Revenue 7d: {amount}": "💰 درآمد ۷ روز: {amount}",
    "📥 Pending orders": "📥 سفارش‌های در انتظار",
    "Nothing waiting. 🎉": "چیزی در انتظار نیست. 🎉",
    "🧾 Order #{public_id}": "🧾 سفارش #{public_id}",
    "User: {uid} ({username})": "کاربر: {uid} ({username})",
    "Plan: {plan} · {gb}GB · {days}d": "پلن: {plan} · {gb} گیگابایت · {days} روز",
    "Discount: {code} (-{amount})": "تخفیف: {code} (-{amount})",
    "Final price: {amount}": "مبلغ نهایی: {amount}",
    "Submitted: {when}": "ثبت: {when}",
    "Status: {status}": "وضعیت: {status}",
    "Reject reason: {reason}": "دلیل رد: {reason}",
    "— user context —": "— وضعیت کاربر —",
    "Active subs: {subs} · Total paid: {paid} · Rejections: {rejections}": "اشتراک فعال: {subs} · پرداخت کل: {paid} · ردها: {rejections}",
    "Member since: {date} ({days} days) · Open tickets: {tickets}": "عضو از: {date} ({days} روز) · تیکت‌های باز: {tickets}",
    "📝 Notes: {notes}": "📝 یادداشت‌ها: {notes}",
    "✅ Approve": "✅ تایید",
    "❌ Reject": "❌ رد",
    "📸 Ask Resend": "📸 درخواست ارسال دوباره",
    "✏️ Custom Msg": "✏️ پیام دلخواه",
    "👤 View User": "👤 مشاهده کاربر",
    "📝 Internal Note": "📝 یادداشت داخلی",
    "⏱ Under Review": "⏱ در حال بررسی",
    "⬅️ Orders": "⬅️ سفارش‌ها",
    "✅ Confirm": "✅ تایید",
    "✏️ Edit Price": "✏️ ویرایش قیمت",
    "✅ Approve order": "✅ تایید سفارش",
    "Order #{public_id}": "سفارش #{public_id}",
    "Provision Rebecca sub · notify user · mark paid {amount}": "ایجاد اشتراک در پنل · اطلاع به کاربر · ثبت پرداخت {amount}",
    "❌ Reject order #{public_id}": "❌ رد سفارش #{public_id}",
    "Choose a reason:": "یک دلیل انتخاب کنید:",
    "🧾 Receipt unclear": "🧾 رسید نامشخص",
    "💵 Amount mismatch": "💵 مبلغ مطابقت ندارد",
    "🕐 Payment not received": "🕐 پرداخت دریافت نشده",
    "👥 Duplicate": "👥 تکراری",
    "🚫 Suspected fraud": "🚫 مشکوک به تقلب",
    "✏️ Custom reason…": "✏️ دلیل دلخواه…",
    "📸 Ask resend — order #{public_id}": "📸 درخواست ارسال دوباره — سفارش #{public_id}",
    "Message to user:\n{message}": "پیام به کاربر:\n{message}",
    "✅ Send": "✅ ارسال",
    "✏️ Edit": "✏️ ویرایش",
    "🖼 Previous receipts": "🖼 رسیدهای قبلی",
    "Receipt {index}": "رسید {index}",
    "🖼 Previous Receipts": "🖼 رسیدهای قبلی",
    "🔄 Retry": "🔄 تلاش دوباره",
    "🎫 Open tickets": "🎫 تیکت‌های باز",
    "None. 🎉": "هیچ. 🎉",
    "🎫 Ticket #{public_id}": "🎫 تیکت #{public_id}",
    "Created: {created} · Updated: {updated}": "ایجاد: {created} · بروزرسانی: {updated}",
    "🟡 In Progress": "🟡 در حال بررسی",
    "✅ Resolve": "✅ حل شد",
    "❌ Close": "❌ بستن",
    "💬 Reply": "💬 پاسخ",
    "⬅️ Tickets": "⬅️ تیکت‌ها",
    "👥 Users — page {page}": "👥 کاربران — صفحه {page}",
    "⬅️ Prev": "⬅️ قبلی",
    "Next ➡️": "بعدی ➡️",
    "🔎 Search": "🔎 جستجو",
    "⬅️ Users": "⬅️ کاربران",
    "👤 User {uid}": "👤 کاربر {uid}",
    "Username: @{username}": "نام کاربری: @{username}",
    "Name: {name}": "نام: {name}",
    "Joined: {date} · Last seen: {last_seen}": "عضویت: {date} · آخرین بازدید: {last_seen}",
    "Total paid: {paid} · Banned: {banned} · Muted: {muted}": "پرداخت کل: {paid} · مسدود: {banned} · بی‌صدا: {muted}",
    "Subscriptions: {count}": "اشتراک‌ها: {count}",
    "yes": "بله",
    "no": "خیر",
    "🧾 Orders": "🧾 سفارش‌ها",
    "🎫 Tickets": "🎫 تیکت‌ها",
    "🚫 Ban/Unban": "🚫 مسدود/رفع مسدودی",
    "✉️ Send DM": "✉️ ارسال پیام",
    "➕ Extend +7d": "➕ تمدید +۷ روز",
    "➕ Extend +30d": "➕ تمدید +۳۰ روز",
    "✏️ Extend Custom": "✏️ تمدید دلخواه",
    "➕ Traffic +5/10/50": "➕ ترافیک +۵/۱۰/۵۰",
    "✏️ Traffic Custom": "✏️ ترافیک دلخواه",
    "♻️ Reset Traffic": "♻️ ریست ترافیک",
    "⏸ Disable": "⏸ غیرفعال",
    "▶️ Enable": "▶️ فعال",
    "🗑 Delete": "🗑 حذف",
    "➕ Add traffic": "➕ افزودن ترافیک",
    "➕ New Discount": "➕ تخفیف جدید",
    "🔁 Toggle Active": "🔁 تغییر وضعیت",
    "🗑 Delete": "🗑 حذف",
    "Percent": "درصدی",
    "Flat (Toman)": "مبلغ ثابت (تومان)",
    "All plans": "همه پلن‌ها",
    "📢 Broadcast": "📢 ارسال همگانی",
    "◉ All users": "◉ همه کاربران",
    "○ Active users": "○ کاربران فعال",
    "○ Expiring ≤7d": "○ در حال انقضا ≤۷ روز",
    "○ Traffic ≥90%": "○ ترافیک ≥۹۰٪",
    "○ Custom list": "○ لیست دلخواه",
    "☐ Force critical": "☐ ارسال اجباری",
    "☑ Force critical": "☑ ارسال اجباری",
    "📤 Send Now": "📤 ارسال",
    "📤 Export CSV": "📤 خروجی CSV",
    "📜 Full Logs": "📜 گزارش کامل",
    "📊 Statistics": "📊 آمار",
    "🚨 Alerts & Logs": "🚨 هشدارها و گزارش‌ها",
    "No audit events yet.": "هنوز رویدادی ثبت نشده است.",
    "⚙️ Settings (read-only)": "⚙️ تنظیمات (فقط خواندنی)",
    "Plans:": "پلن‌ها:",
    "🛠 Admin Menu": "🛠 منوی مدیریت",
    "Not authorized.": "دسترسی ندارید.",
    "⛔ Not authorized.": "⛔ دسترسی ندارید.",
    "Use /admin to open the manager menu.": "برای منوی مدیریت /admin را بزنید.",
    "Unrecognized input. Use /cancel to abort.": "ورودی نامشخص است. برای لغو /cancel را بزنید.",
    "✏️ Send the new final price in Toman (e.g. 288000), or /cancel.": "✏️ مبلغ نهایی جدید را به تومان ارسال کنید (مثلاً ۲۸۸۰۰۰)، یا /cancel.",
    "✏️ Send the rejection reason, or /cancel.": "✏️ دلیل رد را ارسال کنید، یا /cancel.",
    "✏️ Send the resend message text, or /cancel.": "✏️ متن درخواست ارسال دوباره را بنویسید، یا /cancel.",
    "✏️ Send the message to the user, or /cancel.": "✏️ پیام برای کاربر را بنویسید، یا /cancel.",
    "📝 Send the internal note, or /cancel.": "📝 یادداشت داخلی را بنویسید، یا /cancel.",
    "✅ Order #{public_id} approved · sub #{sub_id} provisioned.": "✅ سفارش #{public_id} تایید شد · اشتراک #{sub_id} ایجاد شد.",
    "❌ Order #{public_id} rejected: {reason}": "❌ سفارش #{public_id} رد شد: {reason}",
    "📸 Resend requested for #{public_id}.": "📸 درخواست ارسال دوباره برای #{public_id} ثبت شد.",
    "✉️ Message queued for the user.": "✉️ پیام برای کاربر در صف قرار گرفت.",
    "📝 Note saved.": "📝 یادداشت ذخیره شد.",
    "Marked under review.": "به حالت در حال بررسی رفت.",
    "⚠️ Provisioning failed: {status} {detail}\nOrder status unchanged. You can retry.": "⚠️ ایجاد اشتراک ناموفق بود: {status} {detail}\nوضعیت سفارش تغییر نکرد. می‌توانید دوباره تلاش کنید.",
    "⚠️ Rebecca error: {status} {detail}": "⚠️ خطای پنل: {status} {detail}",
    "✅ Extended by {days} days.": "✅ {days} روز تمدید شد.",
    "✅ Added {gb} GB.": "✅ {gb} گیگابایت اضافه شد.",
    "♻️ Traffic reset.": "♻️ ترافیک ریست شد.",
    "✅ Subscription {status}.": "✅ اشتراک {status} شد.",
    "🗑 Subscription deleted from panel and DB.": "🗑 اشتراک از پنل و دیتابیس حذف شد.",
    "Delete subscription {username} from the panel?": "اشتراک {username} از پنل حذف شود؟",
    "🗑 Confirm delete": "🗑 تایید حذف",
    "Send a number.": "یک عدد ارسال کنید.",
    "Send an integer, e.g. 1.": "یک عدد صحیح ارسال کنید، مثلاً ۱.",
    "Send a number, e.g. 288000.": "یک عدد ارسال کنید، مثلاً ۲۸۸۰۰۰.",
    "User {uid} not found.": "کاربر {uid} پیدا نشد.",
    "User not found.": "کاربر پیدا نشد.",
    "No users matched.": "کاربری پیدا نشد.",
    "🔎 {count} result(s):": "🔎 {count} نتیجه:",
    "🔎 Send a telegram id or username to search, or /cancel.": "🔎 شناسه تلگرام یا نام کاربری را برای جستجو بفرستید، یا /cancel.",
    "✉️ Send the message to deliver to the user, or /cancel.": "✉️ پیامی که باید به کاربر برسد را بفرستید، یا /cancel.",
    "✉️ Message queued for delivery.": "✉️ پیام در صف ارسال قرار گرفت.",
    "📸 Send the resend message text, or /cancel.": "📸 متن درخواست ارسال دوباره را بنویسید، یا /cancel.",
    "➕ New discount": "➕ تخفیف جدید",
    "Send the code (letters/numbers), or /cancel.": "کد را ارسال کنید (حروف/اعداد)، یا /cancel.",
    "Type of discount:": "نوع تخفیف:",
    "Send the value in {unit}, or /cancel.": "مقدار را به {unit} ارسال کنید، یا /cancel.",
    "Which plans does this apply to?": "برای کدام پلن‌ها اعمال شود؟",
    "Send max uses (e.g. 100), or send 'skip' for unlimited.": "حداکثر استفاده را بفرستید (مثلاً ۱۰۰)، یا 'skip' برای نامحدود.",
    "Send per-user max redemptions (e.g. 1).": "حداکثر استفاده هر کاربر را بفرستید (مثلاً ۱).",
    "Send expiry date (YYYY-MM-DD) or 'skip' for no expiry.": "تاریخ انقضا (YYYY-MM-DD) یا 'skip' برای بدون انقضا.",
    "✅ Discount created.\n\n{details}": "✅ تخفیف ایجاد شد.\n\n{details}",
    "Use only letters, numbers, _ or -.": "فقط حروف، اعداد، _ یا - استفاده کنید.",
    "Send an integer or 'skip'.": "یک عدد صحیح یا 'skip' بفرستید.",
    "Use YYYY-MM-DD or 'skip'.": "از YYYY-MM-DD یا 'skip' استفاده کنید.",
    "📢 Broadcast\n\nChoose a segment:": "📢 ارسال همگانی\n\nیک بخش را انتخاب کنید:",
    "Send a comma-separated list of telegram ids, or /cancel.": "لیست شناسه‌های تلگرام را با کاما جدا کنید، یا /cancel.",
    "Segment {segment} · {count} recipients.\n\nSend the broadcast text, or /cancel.": "بخش {segment} · {count} گیرنده.\n\nمتن پیام را بفرستید، یا /cancel.",
    "{count} recipient(s). Send the broadcast text.": "{count} گیرنده. متن پیام را بفرستید.",
    "Invalid id: {value}": "شناسه نامعتبر: {value}",
    "Message is empty.": "پیام خالی است.",
    "📢 Broadcast preview": "📢 پیش‌نمایش ارسال همگانی",
    "Segment: {segment} · Recipients: {count}": "بخش: {segment} · گیرندگان: {count}",
    "Force critical: {force}": "ارسال اجباری: {force}",
    "Message:\n{message}": "پیام:\n{message}",
    "📢 Broadcast complete.\nSent: {sent} · Skipped: {skipped} · Failed: {failed}": "📢 ارسال همگانی انجام شد.\nارسال: {sent} · ردشده: {skipped} · ناموفق: {failed}",
    "📥 Pending orders ({count})": "📥 سفارش‌های در انتظار ({count})",
    "🆘 Report an issue\n\nChoose a category:": "🆘 گزارش مشکل\n\nیک دسته را انتخاب کنید:",
    "📊 Statistics": "📊 آمار",
    "💰 Revenue today/7d/30d: {today} / {week} / {month}": "💰 درآمد امروز/۷روز/۳۰روز: {today} / {week} / {month}",
    "🧾 Orders 7d: {orders}": "🧾 سفارش‌های ۷ روز: {orders}",
    "⏱ Avg review time (7d): {value}": "⏱ میانگین زمان بررسی (۷ روز): {value}",
    "👥 Users total/active/new-7d: {total} / {active} / {new}": "👥 کاربران کل/فعال/جدید ۷ روز: {total} / {active} / {new}",
    "📦 Subs active/exp3d/exp7d/90%/100%: {active} / {e3} / {e7} / {t90} / {t100}": "📦 اشتراک فعال/انقضا۳روز/انقضا۷روز/۹۰٪/۱۰۰٪: {active} / {e3} / {e7} / {t90} / {t100}",
    "🎁 Top promos: {promos}": "🎁 پرکاربردترین کدها: {promos}",
    "🔌 Rebecca API success (5m): {rate}": "🔌 موفقیت API پنل (۵ دقیقه): {rate}",
    "🚨 Funnel: {orders} orders >2h, {tickets} tickets >24h": "🚨 هشدار: {orders} سفارش بیش از ۲ ساعت، {tickets} تیکت بیش از ۲۴ ساعت",
    "min": "دقیقه",
    "📈 Weekly digest": "📈 خلاصه هفتگی",
    "📅 Daily digest": "📅 خلاصه روزانه",
    "💰 Revenue today: {today} · 7d: {week}": "💰 درآمد امروز: {today} · ۷ روز: {week}",
    "🧾 Orders today: {orders}": "🧾 سفارش‌های امروز: {orders}",
    "👥 Users: {total} total · {new} new today": "👥 کاربران: {total} کل · {new} جدید امروز",
    "💰 Revenue 7d: {amount}": "💰 درآمد ۷ روز: {amount}",
    "🧾 Orders 7d: {orders}": "🧾 سفارش‌های ۷ روز: {orders}",
    "📦 Top plans: {plans}": "📦 پرکاربردترین پلن‌ها: {plans}",
    "📉 Churn: {expired} expired subs · {rejected} rejected orders": "📉 ریزش: {expired} اشتراک منقضی · {rejected} سفارش ردشده",
    "⏰ {count} order(s) pending >2h": "⏰ {count} سفارش بیش از ۲ ساعت در انتظار",
    "Open pending orders and review them.": "سفارش‌های در انتظار را باز و بررسی کنید.",
    "⏰ {count} ticket(s) open >24h": "⏰ {count} تیکت بیش از ۲۴ ساعت باز",
    "Tickets are waiting for an admin reply.": "تیکت‌ها منتظر پاسخ مدیر هستند.",
})

# status labels
FA.update({
    "pending": "در انتظار",
    "needs_resend": "نیاز به ارسال دوباره",
    "under_review": "در حال بررسی",
    "approved": "تاییدشده",
    "rejected": "ردشده",
    "cancelled": "لغوشده",
    "open": "باز",
    "in_progress": "در حال بررسی",
    "resolved": "حل‌شده",
    "closed": "بسته",
    "active": "فعال",
    "disabled": "غیرفعال",
    "expired": "منقضی",
    "limited": "محدود",
    "none": "هیچ",
    "all": "همه",
})

# manager UI and handler strings
FA.update({
    "Applies to: {applies}": "اعمال بر: {applies}",
    "Banned.": "مسدود شد.",
    "Building CSV…": "در حال ساخت CSV…",
    "Category: {category} · Status: {status}": "دسته: {category} · وضعیت: {status}",
    "Choose a segment:": "یک بخش را انتخاب کنید:",
    "Compose a broadcast first.": "ابتدا یک پیام همگانی بنویسید.",
    "Confirm deletion.": "حذف را تأیید کنید.",
    "Daily digest": "خلاصه روزانه",
    "Deleted.": "حذف شد.",
    "Discount not found.": "کد تخفیف یافت نشد.",
    "Expires: {expires}": "انقضا: {expires}",
    "Expires: {expires} · Active: {active}": "انقضا: {expires} · فعال: {active}",
    "Force critical OFF.": "ارسال اجباری خاموش شد.",
    "Force critical ON.": "ارسال اجباری روشن شد.",
    "Invalid id: {id}": "شناسه نامعتبر: {id}",
    "Max uses: {max_uses} · Per user: {per_user}": "حداکثر استفاده: {max_uses} · هر کاربر: {per_user}",
    "No codes yet.": "هنوز کدی وجود ندارد.",
    "No orders.": "سفارشی وجود ندارد.",
    "No tickets.": "تیکتی وجود ندارد.",
    "Not found.": "یافت نشد.",
    "Plan: {plan} · {gb} · {days}": "پلن: {plan} · {gb} · {days}",
    "Provisioning…": "در حال ایجاد…",
    "Rebecca error {status}": "خطای Rebecca {status}",
    "Receipt not found.": "رسید یافت نشد.",
    "Redemptions: {count}": "استفاده‌ها: {count}",
    "Resetting…": "در حال بازنشانی…",
    "Segment <b>{segment}</b> · {count} recipients.\n\nSend the broadcast text, or /cancel.": "بخش <b>{segment}</b> · {count} گیرنده.\n\nمتن پیام همگانی را بفرستید یا /cancel را بزنید.",
    "Sending…": "در حال ارسال…",
    "Start from Discounts → New.": "از تخفیف‌ها → جدید شروع کنید.",
    "Status changed to {status}.": "وضعیت به {status} تغییر کرد.",
    "Ticket {status}.": "تیکت {status}.",
    "Ticket closed by user.": "تیکت توسط کاربر بسته شد.",
    "Toggled.": "تغییر کرد.",
    "Toman": "تومان",
    "Screenshot": "اسکرین‌شات",
    "New order alerts": "هشدار سفارش جدید",
    "New ticket alerts": "هشدار تیکت جدید",
    "SLA breach alerts": "هشدار نقض SLA",
    "API error alerts": "هشدار خطای API",
    "⚠️ {caption}: file not found ({path})": "⚠️ {caption}: فایل یافت نشد ({path})",
    "Traffic: {used} / {total}": "ترافیک: {used} / {total}",
    "Type: {type} · Value: {value}": "نوع: {type} · مقدار: {value}",
    "Unbanned.": "رفع مسدودی شد.",
    "User {uid}": "کاربر {uid}",
    "User: {uid}": "کاربر: {uid}",
    "Volume discount: -{amount}": "تخفیف حجمی: -{amount}",
    "Weekly digest": "خلاصه هفتگی",
    "flat": "مبلغ ثابت",
    "never": "هرگز",
    "off": "خاموش",
    "on": "روشن",
    "percent": "درصد",
    "{count} recipient(s).": "{count} گیرنده.",
    "{count} redemptions exist; disabled instead.": "{count} استفاده ثبت شده است؛ به‌جای حذف غیرفعال شد.",
    "{days}d ago": "{days} روز پیش",
    "{dot} #{id} · {category} · {uid} · {when}": "{dot} #{id} · {category} · {uid} · {when}",
    "{dot} #{id} · {uid} · {amount} · {when}": "{dot} #{id} · {uid} · {amount} · {when}",
    "{dot} {code} · {type} {value} · {uses} uses · applies {applies}": "{dot} {code} · {type} {value} · {uses} استفاده · اعمال بر {applies}",
    "{hours}h ago": "{hours} ساعت پیش",
    "{minutes}m ago": "{minutes} دقیقه پیش",
    "{name}: {state}": "{name}: {state}",
    "{when} · {admin} · {action} · {target}": "{when} · {admin} · {action} · {target}",
    "• {name} · {gb} · {days} · {price} · {status}": "• {name} · {gb} · {days} · {price} · {status}",
    "• {when} · {action} {target} by {admin}": "• {when} · {action} {target} توسط {admin}",
    "⚙️ System": "⚙️ سیستم",
    "✅ Added {gb}.": "✅ {gb} اضافه شد.",
    "✅ Discount created.": "✅ کد تخفیف ایجاد شد.",
    "✅ Sent via ticket #{public_id}.": "✅ از طریق تیکت #{public_id} ارسال شد.",
    "✏️ Send a custom message to the user, or /cancel.": "✏️ پیام دلخواه برای کاربر بفرستید یا /cancel را بزنید.",
    "✏️ Send the number of GB to add.": "✏️ مقدار گیگابایت برای افزودن را بفرستید.",
    "✏️ Send the number of days to extend.": "✏️ تعداد روزهای تمدید را بفرستید.",
    "⬅️ Discounts": "⬅️ تخفیف‌ها",
    "⬅️ User": "⬅️ کاربر",
    "🎫 Tickets for {uid}": "🎫 تیکت‌های {uid}",
    "🏠 Admin Menu": "🏠 منوی مدیر",
    "👤 User": "👤 کاربر",
    "💬 Send the reply to the user, or /cancel.": "💬 پاسخ را برای کاربر بفرستید یا /cancel را بزنید.",
    "💬 Send your reply, or /cancel.": "💬 پاسخ خود را بفرستید یا /cancel را بزنید.",
    "💰 Revenue 7d: {week}": "💰 درآمد ۷ روز: {week}",
    "📜 Audit logs — offset {offset}": "📜 گزارش‌های حسابرسی — offset {offset}",
    "🛠 Admin": "🛠 مدیر",
    "🧾 Orders 7d: {statuses}": "🧾 سفارش‌های ۷ روز: {statuses}",
    "🧾 Orders for {uid}": "🧾 سفارش‌های {uid}",
    "🧾 Orders today: {statuses}": "🧾 سفارش‌های امروز: {statuses}",
    "📭 Without subscription": "📭 بدون اشتراک",
    "🔗 Panel without Telegram ID": "🔗 پنل بدون آیدی تلگرام",
    "↻ Refresh": "↻ به‌روزرسانی",
    "📭 Users without subscription — page {page} · total {total}": "📭 کاربران بدون اشتراک — صفحه {page} · مجموع {total}",
    "🎉 Everyone has a subscription.": "🎉 همه اشتراک دارند.",
    "🔗 Panel users without Telegram ID — page {page} · total {total}": "🔗 کاربران پنل بدون آیدی تلگرام — صفحه {page} · مجموع {total}",
    "✅ All panel users have a Telegram ID.": "✅ همه کاربران پنل آیدی تلگرام دارند.",
    "Scanning panel…": "در حال بررسی پنل…",
    "Invalid panel username.": "نام کاربری پنل نامعتبر است.",
    "🔗 Send the Telegram ID to attach to {username}, or /cancel.": "🔗 آیدی تلگرام را برای اتصال به {username} بفرستید، یا /cancel.",
    "Send a valid Telegram ID (numbers only).": "یک آیدی تلگرام معتبر (فقط عدد) بفرستید.",
    "Panel user {username} not found.": "کاربر پنل {username} پیدا نشد.",
    "Panel user {username} is already linked to Telegram ID {id}.": "کاربر پنل {username} قبلاً به آیدی تلگرام {id} متصل شده است.",
    "📦 Your subscription is ready": "📦 اشتراک شما آماده است",
    "Open the bot and send /start so it appears in My Subscriptions.": "ربات را باز کنید و /start بفرستید تا اشتراک در «اشتراک‌های من» نمایش داده شود.",
    "✅ Telegram ID {id} linked to panel user {username}.": "✅ آیدی تلگرام {id} به کاربر پنل {username} متصل شد.",
    "Notification queued for delivery.": "اعلان برای ارسال در صف قرار گرفت.",
    "Notification queued; it will be delivered after the user starts the bot.": "اعلان در صف قرار گرفت؛ پس از شروع ربات توسط کاربر ارسال می‌شود.",
    "💳 Card number request": "درخواست شماره کارت",
    "User {uid} (@{username}) requested the payment card.": "کاربر {uid} (@{username}) شماره کارت پرداخت را درخواست کرد.",
    "💳 Card number available": "شماره کارت در دسترس است",
    "Open the payment page to see the card number.": "صفحه پرداخت را باز کنید تا شماره کارت را ببینید.",
    "💳 Card request rejected": "درخواست شماره کارت رد شد",
    "Contact support if you need help.": "در صورت نیاز به کمک با پشتیبانی تماس بگیرید.",
    "🔄 Check card request": "🔄 بررسی درخواست کارت",
    "📩 Request card number": "📩 درخواست شماره کارت",
    "💳 Card number request is pending manager approval.": "درخواست شماره کارت در انتظار تأیید مدیر است.",
    "💳 Request the card number to continue with payment.": "برای ادامه پرداخت، شماره کارت را درخواست کنید.",
    "📩 Card request sent to the manager.": "📩 درخواست کارت برای مدیر ارسال شد.",
    "Card payment is currently unavailable.": "پرداخت کارتی در حال حاضر در دسترس نیست.",
    "Card details are already available.": "اطلاعات کارت از قبل در دسترس است.",
    "Your card request is already pending.": "درخواست کارت شما در انتظار بررسی است.",
    "💳 Payment Card": "💳 کارت پرداخت",
    "✏️ Edit card number": "✏️ ویرایش شماره کارت",
    "👤 Edit card holder": "👤 ویرایش نام دارنده کارت",
    "⬅️ Payment Card": "⬅️ کارت پرداخت",
    "📥 Pending requests ({count})": "📥 درخواست‌های در انتظار ({count})",
    "⬅️ Requests": "⬅️ درخواست‌ها",
    "Card access: {status}": "دسترسی کارت: {status}",
    "🌍 All users": "🌍 همه کاربران",
    "🔐 On request": "🔐 با درخواست",
    "🚫 No automatic access": "🚫 بدون دسترسی خودکار",
    "not set": "تنظیم نشده",
    "Mode: {mode}": "حالت: {mode}",
    "Pending requests: {count}": "درخواست‌های در انتظار: {count}",
    "🌍 All users: everyone sees the card.": "🌍 همه کاربران: همه شماره کارت را می‌بینند.",
    "🔐 On request: returning users see the card; new users request approval.": "🔐 با درخواست: کاربران دارای سابقه کارت را می‌بینند؛ کاربران جدید باید تأیید بگیرند.",
    "🚫 No automatic access: only users you explicitly grant.": "🚫 بدون دسترسی خودکار: فقط کاربرانی که صریحاً اجازه دهید.",
    "Requested: {when}": "درخواست شده: {when}",
    "No pending card requests.": "درخواست کارت در انتظاری وجود ندارد.",
    "👤 {uid} · @{username} · {when}": "👤 {uid} · @{username} · {when}",
    "Card requests": "درخواست‌های کارت",
    "Card request": "درخواست کارت",
    "Card access revoked.": "دسترسی کارت لغو شد.",
    "Card access granted.": "دسترسی کارت اعطا شد.",
    "✅ Revoke card access": "✅ لغو دسترسی کارت",
    "💳 Grant card access": "💳 اعطای دسترسی کارت",
    "💳 Send the new 16-digit card number, or /cancel.": "💳 شماره کارت ۱۶ رقمی جدید را بفرستید، یا /cancel.",
    "👤 Send the card holder name, or /cancel.": "👤 نام دارنده کارت را بفرستید، یا /cancel.",
    "Card mode updated.": "حالت کارت به‌روزرسانی شد.",
    "Card access approved.": "دسترسی کارت تأیید شد.",
    "Card request rejected.": "درخواست کارت رد شد.",
    "Invalid card mode.": "حالت کارت نامعتبر است.",
    "Send a valid card holder name.": "نام دارنده کارت معتبر بفرستید.",
    "Send a valid 16-digit card number.": "شماره کارت معتبر ۱۶ رقمی بفرستید.",
    "✅ Card holder updated.": "✅ نام دارنده کارت به‌روزرسانی شد.",
    "✅ Card number updated.": "✅ شماره کارت به‌روزرسانی شد.",
    "🎁 Transfer": "🎁 انتقال",
    "✅ Accept": "✅ پذیرش",
    "❌ Decline": "❌ رد",
    "🎁 Subscription transfer": "🎁 انتقال اشتراک",
    "User {sender} wants to transfer {name} to you.": "کاربر {sender} می‌خواهد اشتراک {name} را به شما منتقل کند.",
    "Only accept if you trust the sender.": "فقط در صورتی که به فرستنده اعتماد دارید بپذیرید.",
    "🎁 Send the recipient's Telegram ID, or /cancel.": "🎁 آیدی تلگرام گیرنده را بفرستید، یا /cancel.",
    "Recipient must have started this bot first.": "گیرنده ابتدا باید این ربات را شروع کرده باشد.",
    "You cannot transfer to yourself.": "نمی‌توانید به خودتان منتقل کنید.",
    "A transfer is already pending for this subscription.": "یک درخواست انتقال برای این اشتراک در انتظار است.",
    "✅ Transfer request sent to the recipient.": "✅ درخواست انتقال برای گیرنده ارسال شد.",
    "⚠️ Could not message the recipient. They must have started the bot and not blocked it.": "⚠️ ارسال پیام به گیرنده ممکن نشد. او باید ربات را شروع کرده و ربات را بلاک نکرده باشد.",
    "Transfer not found.": "انتقال پیدا نشد.",
    "This transfer is no longer valid.": "این انتقال دیگر معتبر نیست.",
    "✅ Transfer accepted. The subscription is now in My Subscriptions.": "✅ انتقال پذیرفته شد. اشتراک اکنون در اشتراک‌های من است.",
    "✅ Subscription {name} was transferred to the recipient.": "✅ اشتراک {name} به گیرنده منتقل شد.",
    "Transfer declined.": "انتقال رد شد.",
    "❌ Transfer declined.": "❌ انتقال رد شد.",
    "❌ The recipient declined the transfer of {name}.": "❌ گیرنده انتقال {name} را رد کرد.",
    "subscription": "اشتراک",
    "💳 New payment receipt": "💳 رسید پرداخت جدید",
    "🧾 New receipt for #{public_id}": "🧾 رسید جدید برای #{public_id}",
    "Order #{public_id}\nUser: @{username} ({uid})\nPlan: {plan}\nAmount: {amount}\n\nReview and approve or reject it.": "سفارش #{public_id}\nکاربر: @{username} ({uid})\nپلن: {plan}\nمبلغ: {amount}\n\nبررسی کنید و تأیید یا رد کنید.",
    "🔎 Review order": "🔎 بررسی سفارش",
    "Your message is too long. Please keep it under {max} characters.": "پیام شما طولانی است. لطفاً آن را کمتر از {max} کاراکتر نگه دارید.",
    "🎁 Invite Friends": "🎁 دعوت دوستان",
    "🎟 Invitation Code": "🎟 کد دعوت",
    "📋 Copy code": "📋 کپی کد",
    "🔗 Copy invite link": "🔗 کپی لینک دعوت",
    "Your code: {code}": "کد شما: {code}",
    "Invite link: {link}": "لینک دعوت: {link}",
    "Invited: {total} · Credited: {credited} · Pending: {pending}": "دعوت‌شده: {total} · واریزشده: {credited} · در انتظار: {pending}",
    "Total earned: {gb}": "مجموع دریافتی: {gb}",
    "New users can enter your code when buying. You earn {percent} of their purchased traffic after approval.": "کاربران جدید می‌توانند هنگام خرید کد شما را وارد کنند. پس از تأیید، {percent} از ترافیک خریداری‌شده آن‌ها به شما اضافه می‌شود.",
    "Could not create an invite code.": "ساخت کد دعوت ممکن نشد.",
    "🎟 Send your invitation code as a message, or tap Cancel.": "🎟 کد دعوت خود را به‌صورت پیام بفرستید، یا لغو را بزنید.",
    "Invitation code applied: {code}": "کد دعوت اعمال شد: {code}",
    "Invitation code: {code}": "کد دعوت: {code}",
    "Invalid invitation code.": "کد دعوت نامعتبر است.",
    "You cannot use your own invitation code.": "نمی‌توانید از کد دعوت خودتان استفاده کنید.",
    "Invitation codes are only for first purchases.": "کد دعوت فقط برای اولین خرید است.",
    "You have already used an invitation code.": "شما قبلاً از یک کد دعوت استفاده کرده‌اید.",
    "🎉 Referral bonus: +{gb}": "🎉 پاداش دعوت: +{gb}",
    "Added to subscription {name}.": "به اشتراک {name} اضافه شد.",
    "🔄 Renew": "🔄 تمدید",
    "🔄 Renewal receipt": "🔄 رسید تمدید",
    "🔄 Renewal for subscription #{sub_id}": "🔄 تمدید برای اشتراک #{sub_id}",
    "Renewal for subscription #{sub_id}": "تمدید برای اشتراک #{sub_id}",
    "A renewal order is already pending for this subscription.": "یک سفارش تمدید برای این اشتراک در انتظار است.",
    "This subscription cannot be renewed.": "این اشتراک قابل تمدید نیست.",
    "Renewal": "تمدید",
    "⬅️ Back to subscription": "⬅️ بازگشت به اشتراک",
    "Your subscription was renewed. Plan: {plan}.\nExpires: {expires}": "اشتراک شما تمدید شد. پلن: {plan}.\nانقضا: {expires}",
    "✅ Order #{public_id} approved · sub #{sub_id} renewed.": "✅ سفارش #{public_id} تأیید شد · اشتراک #{sub_id} تمدید شد.",
    "Renew Rebecca sub · notify user · mark paid {amount}": "تمدید اشتراک ربکا · اطلاع به کاربر · ثبت پرداخت {amount}",
    "Too many requests. Please wait and try again later.": "درخواست‌های بیش از حد. لطفاً بعداً دوباره تلاش کنید.",
    "The AI assistant has reached its daily limit. Please try again later or use 🆘 Report Issue.": "دستیار هوش مصنوعی به سقف روزانه رسیده است. بعداً تلاش کنید یا از 🆘 گزارش مشکل استفاده کنید.",
})


def t(template: str, **kwargs: Any) -> str:
    lang = get_lang()
    text = FA.get(template, template) if lang == "fa" else template
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def _fa_digits(text: str) -> str:
    return text.translate(_FA_DIGITS)


_ASCII_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬",
    "01234567890123456789,",
)


def parse_number(text: str) -> Optional[float]:
    """Parse a user-entered number, accepting Persian/Arabic digits and separators."""
    cleaned = str(text).translate(_ASCII_DIGITS)
    cleaned = (
        cleaned.replace(",", "").replace("٬", "").replace("،", "")
        .replace("٫", ".")
        .replace("تومان", "").replace("GB", "").replace("گیگابایت", "")
        .replace("$", "").strip()
    )
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def format_number(value: Any, lang: Optional[str] = None) -> str:
    lang = lang or get_lang()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        text = f"{int(number):,}"
    else:
        text = f"{number:,.2f}"
    return _fa_digits(text).replace(",", "٬").replace(".", "٫") if lang == "fa" else text


def format_toman(value: Any, lang: Optional[str] = None) -> str:
    lang = lang or get_lang()
    number = format_number(value, lang)
    return f"{number} تومان" if lang == "fa" else f"{number} Toman"


def format_gb(value: Any, lang: Optional[str] = None) -> str:
    lang = lang or get_lang()
    try:
        number = float(value)
        text = f"{number:g}"
    except (TypeError, ValueError):
        text = str(value)
    return f"{_fa_digits(text)} گیگابایت" if lang == "fa" else f"{text} GB"


def format_days(value: Any, lang: Optional[str] = None) -> str:
    lang = lang or get_lang()
    text = format_number(value, lang)
    return f"{text} روز" if lang == "fa" else f"{text}d"


def format_percent(value: Any, lang: Optional[str] = None) -> str:
    lang = lang or get_lang()
    text = format_number(value, lang)
    return f"{text}٪" if lang == "fa" else f"{text}%"


__all__ = [
    "SUPPORTED", "DEFAULT", "FA", "normalize_lang", "set_lang", "get_lang",
    "use_lang", "language_name", "t", "format_number", "format_toman",
    "format_gb", "format_days", "format_percent", "parse_number",
]
