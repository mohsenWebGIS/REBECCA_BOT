"""Register all user-bot handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, TypeHandler

from user_bot.handlers import ai, buy, notif, referrals, router, start, subs, tickets
from user_bot.middleware import attach_language


def register_all(application: Application) -> None:
    application.add_handler(TypeHandler(Update, attach_language), group=-1)
    start.register(application)
    subs.register(application)
    buy.register(application)
    tickets.register(application)
    notif.register(application)
    ai.register(application)
    referrals.register(application)
    router.register(application)
