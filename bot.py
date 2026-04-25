import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    InlineQueryHandler,
)

import config
from database.db import Database
from database.repository import UserRepository, WhisperRepository
from handlers import READ_CB_PREFIX
from handlers.callbacks import handle_read
from handlers.commands import help_cmd, start
from handlers.inline import handle_inline_query
from services.rate_limiter import RateLimiter
from services.whisper import WhisperService
from utils.cleanup import run_cleanup

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    await db.connect()

    whisper_repo = WhisperRepository(db)
    user_repo = UserRepository(db)

    application.bot_data["service"] = WhisperService(
        whisper_repo,
        user_repo,
        ttl_days=config.WHISPER_TTL_DAYS,
        bot=application.bot,
        notify_channel_id=config.NOTIFY_CHANNEL_ID or None,
    )
    application.bot_data["rate_limiter"] = RateLimiter(
        max_calls=config.RATE_LIMIT_MAX,
        window_seconds=config.RATE_LIMIT_WINDOW,
    )
    application.bot_data["pending"] = {}

    task = asyncio.create_task(
        run_cleanup(whisper_repo, interval=config.CLEANUP_INTERVAL)
    )
    application.bot_data["_cleanup_task"] = task
    logger.info("Bot initialised")


async def _post_shutdown(application: Application) -> None:
    task: asyncio.Task = application.bot_data.get("_cleanup_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    db: Database = application.bot_data.get("db")
    if db:
        await db.close()


async def _error_handler(_: object, context) -> None:
    logger.error("Unhandled exception processing update", exc_info=context.error)


def main() -> None:
    db = Database(config.DB_PATH)

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["db"] = db

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(InlineQueryHandler(handle_inline_query))
    app.add_handler(CallbackQueryHandler(handle_read, pattern=f"^{READ_CB_PREFIX}"))
    app.add_error_handler(_error_handler)

    logger.info("Starting Whisper Bot…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
