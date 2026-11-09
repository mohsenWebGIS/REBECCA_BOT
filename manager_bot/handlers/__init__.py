"""Register all manager-bot handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import Application, TypeHandler

from manager_bot.handlers import (
    alerts,
    broadcast,
    card,
    discounts,
    menu,
    orders,
    router,
    stats,
    tickets,
    users,
)
from manager_bot.middleware import attach_language


def register_all(application: Application) -> None:
    application.add_handler(TypeHandler(Update, attach_language), group=-1)
    menu.register(application)
    card.register(application)
    orders.register(application)
    tickets.register(application)
    users.register(application)
    discounts.register(application)
    broadcast.register(application)
    stats.register(application)
    alerts.register(application)
    router.register(application)
