"""/start, main menu, help, language and cancel."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.db import queries as q
from core.i18n import normalize_lang, set_lang, t
from core.services import referrals as referral_svc
from core.services.sync import sync_for_telegram_id
from user_bot import keyboards as kb, states, ui
from user_bot.handlers.util import answer, safe_edit

logger = logging.getLogger(__name__)


async def _finish_loading(loading, text: str, markup) -> None:
    try:
        await loading.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except BadRequest:
        logger.warning("could not edit loading message; sending a new menu message")
        await loading.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return
    await q.upsert_user(user.id, user.username, user.full_name)
    try:
        await referral_svc.ensure_invite_code(user.id)
        if context.args:
            arg = context.args[0].strip()
            if arg.lower().startswith("ref_"):
                code = referral_svc.normalize_code(arg[4:])
                _inviter, error = await referral_svc.validate_invite_code(code, user.id)
                if error is None:
                    context.user_data["invite_code"] = code
    except Exception:
        logger.exception("invite code setup failed for %s", user.id)
    loading = await update.message.reply_text(t("👋 Loading…"), reply_markup=kb.home_reply())
    rebecca = context.application.bot_data.get("rebecca")
    if rebecca is not None:
        try:
            await sync_for_telegram_id(user.id, rebecca)
        except Exception:
            logger.exception("panel sync failed for %s", user.id)
    db_user = await q.get_user(user.id)
    if db_user is not None and not db_user.get("lang_selected"):
        text, markup = ui.render_language()
        await _finish_loading(loading, text, markup)
        return
    text, markup = await ui.render_main_menu(user.id)
    await _finish_loading(loading, text, markup)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    states.clear_state(update.effective_user.id)
    text, markup = await ui.render_main_menu(update.effective_user.id)
    await safe_edit(query, text, markup)


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    states.clear_state(update.effective_user.id)
    text, markup = await ui.render_main_menu(update.effective_user.id)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def show_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, markup = ui.render_language()
    if update.callback_query is not None:
        await answer(update.callback_query)
        await safe_edit(update.callback_query, text, markup)
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=markup)


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    lang = normalize_lang(query.data.rsplit(":", 1)[-1])
    uid = update.effective_user.id
    await q.update_user(uid, preferred_lang=lang, lang_selected=1)
    set_lang(lang)
    await answer(query, t("Language set."))
    states.clear_state(uid)
    text, markup = await ui.render_main_menu(uid)
    await safe_edit(query, text, markup)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is not None:
        await answer(update.callback_query)
        text, markup = ui.render_help()
        await safe_edit(update.callback_query, text, markup)
    elif update.message is not None:
        text, markup = ui.render_help()
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None:
        return
    states.clear_state(update.effective_user.id)
    if update.callback_query is not None:
        await answer(update.callback_query, t("Cancelled."))
        text, markup = await ui.render_main_menu(update.effective_user.id)
        await safe_edit(update.callback_query, text, markup)
    elif update.message is not None:
        text, markup = await ui.render_main_menu(update.effective_user.id)
        await update.message.reply_text(
            t("Cancelled.") + "\n\n" + text, reply_markup=markup, parse_mode="HTML"
        )


def register(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", show_help))
    application.add_handler(CommandHandler("language", show_language))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(show_menu, pattern=r"^menu:home$"))
    application.add_handler(CallbackQueryHandler(show_help, pattern=r"^help$"))
    application.add_handler(CallbackQueryHandler(show_language, pattern=r"^lang:menu$"))
    application.add_handler(CallbackQueryHandler(set_language, pattern=r"^lang:set:"))

    application.add_handler(CallbackQueryHandler(cancel, pattern=r"^cancel$"))
    application.add_handler(
        MessageHandler(filters.Text([kb.HOME_BUTTON, "🏠"]), go_home)
    )
