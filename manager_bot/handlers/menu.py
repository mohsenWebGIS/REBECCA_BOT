"""/admin hub, home navigation, language and cancel."""
from __future__ import annotations

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
from manager_bot import keyboards as kb, states, ui
from manager_bot.util import answer, manager_only, safe_edit


@manager_only
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    states.clear_state(uid)
    if await q.get_manager_lang(uid) is None:
        text, markup = t("Choose your language:"), kb.language()
    else:
        text, markup = await ui.render_admin_menu()
    if update.callback_query is not None:
        await answer(update.callback_query)
        await safe_edit(update.callback_query, text, markup)
    elif update.message is not None:
        sent = await update.message.reply_text(
            t("👋 Loading…"), reply_markup=kb.home_reply()
        )
        try:
            await sent.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except BadRequest:
            await update.message.reply_text(
                text, reply_markup=markup, parse_mode="HTML"
            )


@manager_only
async def show_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, markup = t("Choose your language:"), kb.language()
    if update.callback_query is not None:
        await answer(update.callback_query)
        await safe_edit(update.callback_query, text, markup)
    elif update.message is not None:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


@manager_only
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    lang = normalize_lang(query.data.rsplit(":", 1)[-1])
    await q.set_manager_lang(update.effective_user.id, lang)
    set_lang(lang)
    await answer(query, t("Language set."))
    states.clear_state(update.effective_user.id)
    text, markup = await ui.render_admin_menu()
    await safe_edit(query, text, markup)


@manager_only
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    states.clear_state(update.effective_user.id)
    if update.callback_query is not None:
        await answer(update.callback_query, t("Cancelled."))
        text, markup = await ui.render_admin_menu()
        await safe_edit(update.callback_query, text, markup)
    elif update.message is not None:
        text, markup = await ui.render_admin_menu()
        await update.message.reply_text(
            t("Cancelled.") + "\n\n" + text, reply_markup=markup, parse_mode="HTML"
        )


@manager_only
async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    states.clear_state(update.effective_user.id)
    text, markup = await ui.render_admin_menu()
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


@manager_only
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_settings()
    await safe_edit(query, text, markup)


def register(application: Application) -> None:
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("start", admin))
    application.add_handler(CommandHandler("language", show_language))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(admin, pattern=r"^home$"))
    application.add_handler(CallbackQueryHandler(settings, pattern=r"^settings$"))
    application.add_handler(CallbackQueryHandler(show_language, pattern=r"^lang:menu$"))
    application.add_handler(CallbackQueryHandler(set_language, pattern=r"^lang:set:"))
    application.add_handler(CallbackQueryHandler(cancel, pattern=r"^cancel$"))
    application.add_handler(
        MessageHandler(filters.Text([kb.HOME_BUTTON, "🏠"]), go_home)
    )
