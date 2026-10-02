"""Mandatory channel-subscription check."""
from __future__ import annotations

import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError

from ..config import ConfigError

logger = logging.getLogger(__name__)

_MEMBER_STATUSES = ("creator", "administrator", "member")
_ADMIN_STATUSES = ("creator", "administrator")


def _status_of(member: object) -> str:
    status = getattr(member, "status", "")
    return str(getattr(status, "value", status))


class SubscriptionService:
    def __init__(self, bot: Bot, channel_id: int | str, cache_ttl: float = 30.0) -> None:
        self._bot = bot
        self._channel_id = channel_id
        self._ttl = cache_ttl
        self._positive_cache: dict[int, float] = {}  # user_id -> expiry (monotonic)

    async def is_subscribed(self, user_id: int, *, force: bool = False) -> bool:
        """True when the user is a member of the channel.

        Positive answers are cached briefly so an album of 5 photos does not cause
        5 API calls; ``force=True`` (the "verify" button) always asks Telegram.
        Any API failure is treated as "not subscribed" (fail closed) and logged.
        """
        now = time.monotonic()
        if not force and self._positive_cache.get(user_id, 0.0) > now:
            return True

        try:
            member = await self._bot.get_chat_member(self._channel_id, user_id)
        except TelegramAPIError as exc:
            logger.error(
                "Cannot check membership of user %s (is the bot an admin of the channel?): %s",
                user_id,
                exc,
            )
            return False

        status = _status_of(member)
        subscribed = status in _MEMBER_STATUSES or (
            status == "restricted" and bool(getattr(member, "is_member", False))
        )
        if subscribed:
            if len(self._positive_cache) > 10_000:
                self._positive_cache = {
                    uid: exp for uid, exp in self._positive_cache.items() if exp > now
                }
            self._positive_cache[user_id] = now + self._ttl
        else:
            self._positive_cache.pop(user_id, None)
        return subscribed

    async def verify_channel_access(self) -> None:
        """Startup sanity check: the bot must be an administrator of the channel."""
        try:
            me = await self._bot.get_me()
            member = await self._bot.get_chat_member(self._channel_id, me.id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            raise ConfigError(
                "البوت ما قدر يوصل للقناة. تأكد من CHANNEL_ID وأن البوت مضاف "
                f"كـ Administrator في القناة. (تفاصيل: {exc})"
            ) from exc
        except TelegramAPIError as exc:
            logger.warning("Could not verify channel access at startup: %s", exc)
            return

        if _status_of(member) not in _ADMIN_STATUSES:
            logger.warning(
                "The bot is NOT an administrator of the channel — membership checks will fail."
            )
        else:
            logger.info("Channel access verified.")
