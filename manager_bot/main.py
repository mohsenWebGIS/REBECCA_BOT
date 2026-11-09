"""Private admin Telegram bot entrypoint."""
from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application, ContextTypes

from core.bot_commands import MANAGER_COMMANDS, MANAGER_COMMANDS_FA, publish_commands
from core.config import settings
from core.db import close_db, init_db
from core.rebecca_api import RebeccaClient
from manager_bot import handlers
from manager_bot.jobs import start_scheduler

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    await init_db()
    application.bot_data["rebecca"] = RebeccaClient()
    application.bot_data["scheduler"] = start_scheduler(application)
    await publish_commands(application.bot, MANAGER_COMMANDS, MANAGER_COMMANDS_FA)
    logger.info("manager bot started")


async def _post_shutdown(application: Application) -> None:
    scheduler = application.bot_data.get("scheduler")
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    client = application.bot_data.get("rebecca")
    if client is not None:
        await client.close()
    await close_db()


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("update failed", exc_info=context.error)


def build_application() -> Application:
    if not settings.manager_bot_token:
        raise SystemExit("MANAGER_BOT_TOKEN is not set in .env")
    application = (
        Application.builder()
        .token(settings.manager_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    handlers.register_all(application)
    application.add_error_handler(_on_error)
    return application


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not settings.manager_bot_token:
        sys.exit("MANAGER_BOT_TOKEN is not set in .env")
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
