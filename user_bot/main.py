"""Customer-facing Telegram bot entrypoint."""
from __future__ import annotations

import logging
import sys

from telegram import Update
from telegram.ext import Application, ContextTypes

from core.bot_commands import USER_COMMANDS, USER_COMMANDS_FA, publish_commands
from core.config import settings
from core.db import close_db, init_db
from core.rebecca_api import RebeccaClient
from user_bot import handlers
from user_bot.jobs import start_scheduler

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    await init_db()
    application.bot_data["rebecca"] = RebeccaClient()
    application.bot_data["scheduler"] = start_scheduler(application)
    try:
        me = await application.bot.get_me()
        application.bot_data["bot_username"] = me.username
    except Exception:
        logger.exception("could not resolve user bot username")
    await publish_commands(application.bot, USER_COMMANDS, USER_COMMANDS_FA)
    logger.info("user bot started")


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
    if not settings.user_bot_token:
        raise SystemExit("USER_BOT_TOKEN is not set in .env")
    application = (
        Application.builder()
        .token(settings.user_bot_token)
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
    # httpx logs the full request URL at INFO; Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if settings.user_bot_token is None:
        sys.exit("USER_BOT_TOKEN is not set in .env")
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
