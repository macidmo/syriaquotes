"""Entry point: python main.py (from the project directory)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = Path(__file__).resolve().parent.name

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent
from . import texts
from .config import ConfigError, load_settings
from .database.database import Database
from .handlers import build_router
from .logging_config import setup_logging
from .services.admin_view import AdminMediaTracker
from .services.drafts import DraftStore
from .services.subscription import SubscriptionService

logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> bool:
    """Global safety net: one failing update must never stop the bot."""
    logger.error("Unhandled error while processing an update", exc_info=event.exception)
    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(texts.UNEXPECTED_ERROR, show_alert=True)
        elif update.message is not None:
            await update.message.answer(texts.UNEXPECTED_ERROR)
    except TelegramAPIError:
        pass
    return True


async def _purge_loop(drafts: DraftStore) -> None:
    while True:
        await asyncio.sleep(600)
        removed = drafts.purge_expired()
        if removed:
            logger.info("Purged %s expired drafts", removed)


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is empty — nobody can open the admin panel.")

    db = Database(settings.database_url)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    purge_task: asyncio.Task[None] | None = None
    try:
        await db.init()

        subscriptions = SubscriptionService(bot, settings.channel_id)
        await subscriptions.verify_channel_access()

        drafts = DraftStore(ttl_seconds=settings.draft_ttl_minutes * 60)
        dp = Dispatcher()
        dp.workflow_data.update(
            settings=settings,
            db=db,
            drafts=drafts,
            subscriptions=subscriptions,
            media_tracker=AdminMediaTracker(),
        )
        dp.include_router(build_router())
        dp.errors.register(on_error)

        purge_task = asyncio.create_task(_purge_loop(drafts))
        me = await bot.get_me()
        logger.info("Bot started as @%s (id=%s)", me.username, me.id)

        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if purge_task is not None:
            purge_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await purge_task
        await bot.session.close()
        await db.dispose()
        logger.info("Bot stopped.")


def run() -> None:
    try:
        asyncio.run(main())
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    run()
