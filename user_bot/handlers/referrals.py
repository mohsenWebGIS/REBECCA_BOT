"""Invite Friends page: invite code, share link and referral stats."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.config import settings
from core.i18n import format_gb, format_number, format_percent, t
from core.services.referrals import ensure_invite_code, referral_stats
from user_bot import keyboards as kb
from user_bot.handlers.util import answer, safe_edit


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    uid = update.effective_user.id
    code = await ensure_invite_code(uid)
    if code is None:
        await safe_edit(query, t("Could not create an invite code."), kb.back_home())
        return
    stats = await referral_stats(uid)
    username = context.application.bot_data.get("bot_username")
    link = f"https://t.me/{username}?start=ref_{code}" if username else None
    lines = [
        "🎁 <b>" + t("🎁 Invite Friends").replace("🎁 ", "") + "</b>",
        t("Your code: {code}", code=f"<code>{code}</code>"),
    ]
    if link:
        lines.append(t("Invite link: {link}", link=f"<code>{link}</code>"))
    lines.extend(
        [
            "",
            t(
                "Invited: {total} · Credited: {credited} · Pending: {pending}",
                total=format_number(stats["total"]),
                credited=format_number(stats["credited"]),
                pending=format_number(stats["pending"]),
            ),
            t("Total earned: {gb}", gb=format_gb(stats["total_bonus_gb"])),
            "",
            t(
                "New users can enter your code when buying. You earn {percent} of their purchased traffic after approval.",
                percent=format_percent(settings.referral_bonus_percent),
            ),
        ]
    )
    await safe_edit(query, "\n".join(lines), kb.referral_menu(code, link))


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(show, pattern=r"^referrals$"))
