"""Alerts feed, per-admin category toggles and audit logs."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.i18n import t
from manager_bot import ui
from manager_bot.util import answer, manager_only, safe_edit

DEFAULT_TOGGLES = {
    "new_order": True,
    "new_ticket": True,
    "sla_breach": True,
    "api_errors": True,
    "daily_digest": True,
    "weekly_digest": True,
}

_TOGGLES: dict[int, dict[str, bool]] = {}


def toggles_for(admin_id: int) -> dict[str, bool]:
    return _TOGGLES.setdefault(admin_id, dict(DEFAULT_TOGGLES))


@manager_only
async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    toggles = toggles_for(update.effective_user.id)
    text, markup = await ui.render_alerts(toggles)
    await safe_edit(query, text, markup)


@manager_only
async def toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    key = query.data.rsplit(":", 1)[-1]
    toggles = toggles_for(update.effective_user.id)
    toggles[key] = not toggles.get(key, True)
    await answer(
        query,
        t(
            "{name}: {state}",
            name=t(key),
            state=t("on") if toggles[key] else t("off"),
        ),
    )
    text, markup = await ui.render_alerts(toggles)
    await safe_edit(query, text, markup)


@manager_only
async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_full_logs(0)
    await safe_edit(query, text, markup)


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(show, pattern=r"^alerts$"))
    application.add_handler(CallbackQueryHandler(toggle, pattern=r"^alerts:toggle:\w+$"))
    application.add_handler(CallbackQueryHandler(logs, pattern=r"^alerts:logs$"))
