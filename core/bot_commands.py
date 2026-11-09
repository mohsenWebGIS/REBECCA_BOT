"""Publish Telegram slash-command menus for both bots."""
from __future__ import annotations

import logging

from telegram import Bot, BotCommand

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand("start", "Open the main menu"),
    BotCommand("help", "Show help"),
    BotCommand("language", "Change language"),
    BotCommand("cancel", "Cancel the current action"),
]
USER_COMMANDS_FA = [
    BotCommand("start", "باز کردن منوی اصلی"),
    BotCommand("help", "راهنما"),
    BotCommand("language", "تغییر زبان"),
    BotCommand("cancel", "لغو عملیات جاری"),
]

MANAGER_COMMANDS = [
    BotCommand("admin", "Open the manager menu"),
    BotCommand("start", "Open the manager menu"),
    BotCommand("language", "Change language"),
    BotCommand("cancel", "Cancel the current action"),
]
MANAGER_COMMANDS_FA = [
    BotCommand("admin", "باز کردن منوی مدیر"),
    BotCommand("start", "باز کردن منوی مدیر"),
    BotCommand("language", "تغییر زبان"),
    BotCommand("cancel", "لغو عملیات جاری"),
]


async def publish_commands(
    bot: Bot,
    commands: list[BotCommand],
    commands_fa: list[BotCommand],
) -> None:
    for menu, code in ((commands, None), (commands_fa, "fa")):
        try:
            await bot.set_my_commands(menu, language_code=code)
        except Exception:
            logger.exception("failed to publish commands (language_code=%s)", code)


__all__ = [
    "USER_COMMANDS",
    "USER_COMMANDS_FA",
    "MANAGER_COMMANDS",
    "MANAGER_COMMANDS_FA",
    "publish_commands",
]
