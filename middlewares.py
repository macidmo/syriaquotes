"""Middlewares: subscription gate (users) and permission guard (admins)."""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser

from . import keyboards, texts
from .config import Settings
from .database.database import Database
from .database.repositories import UserRepository
from .utils.telegram import accessible_message

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

CHECK_SUBSCRIPTION_DATA = "sub:check"


class SubscriptionMiddleware(BaseMiddleware):
    """Runs before every user-facing handler. Non-subscribers only ever see the
    subscription prompt; subscribers get their profile refreshed (at most once a
    minute) and continue."""

    def __init__(self) -> None:
        self._last_touch: dict[int, float] = {}

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: TgUser | None = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)
        if isinstance(event, Message) and event.chat.type != "private":
            return None  # the bot only works in private chats
        if isinstance(event, CallbackQuery) and event.data == CHECK_SUBSCRIPTION_DATA:
            return await handler(event, data)  # this handler does its own (forced) check

        settings: Settings = data["settings"]
        if await data["subscriptions"].is_subscribed(user.id):
            await self._touch_user(data["db"], user)
            return await handler(event, data)

        await self._deny(event, settings)
        return None

    async def _touch_user(self, db: Database, user: TgUser) -> None:
        now = time.monotonic()
        if now - self._last_touch.get(user.id, -60.0) < 60.0:
            return
        if len(self._last_touch) > 10_000:
            self._last_touch.clear()
        self._last_touch[user.id] = now
        try:
            async with db.session() as session:
                await UserRepository(session).upsert(
                    user.id, user.username, user.first_name, user.last_name
                )
        except Exception:  # never block the user because of a bookkeeping failure
            logger.exception("Failed to update user %s", user.id)

    async def _deny(self, event: TelegramObject, settings: Settings) -> None:
        markup = keyboards.gate(settings.channel_url)
        if isinstance(event, Message):
            await event.answer(texts.GATE_TEXT, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            await event.answer()
            message = accessible_message(event)
            if message is not None:
                await message.answer(texts.GATE_TEXT, reply_markup=markup)


class AdminGuardMiddleware(BaseMiddleware):
    """Inner middleware on the admin router: runs for EVERY admin command and
    callback, so admin rights are re-checked on each single action."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        settings: Settings = data["settings"]
        user: TgUser | None = data.get("event_from_user")
        if user is not None and user.id in settings.admin_ids:
            return await handler(event, data)

        logger.warning("Blocked non-admin access attempt by user %s", getattr(user, "id", None))
        if isinstance(event, CallbackQuery):
            await event.answer(texts.ADMIN_DENIED, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(texts.ADMIN_DENIED)
        return None
