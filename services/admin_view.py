"""Helpers for showing a submission's media to an admin."""
from __future__ import annotations

import logging
from typing import Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InputMediaPhoto, InputMediaVideo

from ..database.models import Media
from ..schemas import MEDIA_PHOTO
from ..utils.telegram import safe_delete

logger = logging.getLogger(__name__)

_GROUP_LIMIT = 10  # Telegram allows 2-10 items per media group


class AdminMediaTracker:
    """Remembers the media messages sent to each admin chat so they can be removed
    when the admin navigates away (keeps the chat tidy)."""

    def __init__(self) -> None:
        self._messages: dict[int, list[int]] = {}

    def remember(self, chat_id: int, message_ids: list[int]) -> None:
        if message_ids:
            self._messages[chat_id] = message_ids

    async def clear(self, bot: Bot, chat_id: int) -> None:
        for message_id in self._messages.pop(chat_id, []):
            await safe_delete(bot, chat_id, message_id)


async def send_submission_media(
    bot: Bot, chat_id: int, media: Sequence[Media]
) -> tuple[list[int], bool]:
    """Send photos/videos using the stored Telegram file_ids (nothing is downloaded).

    Returns (sent_message_ids, all_ok). Several files are sent as an album.
    """
    sent_ids: list[int] = []
    all_ok = True
    items = list(media)

    for start in range(0, len(items), _GROUP_LIMIT):
        chunk = items[start : start + _GROUP_LIMIT]
        try:
            if len(chunk) == 1:
                item = chunk[0]
                if item.media_type == MEDIA_PHOTO:
                    sent = await bot.send_photo(chat_id, item.telegram_file_id)
                else:
                    sent = await bot.send_video(
                        chat_id, item.telegram_file_id, supports_streaming=True
                    )
                sent_ids.append(sent.message_id)
            else:
                group = [
                    InputMediaPhoto(media=m.telegram_file_id)
                    if m.media_type == MEDIA_PHOTO
                    else InputMediaVideo(media=m.telegram_file_id, supports_streaming=True)
                    for m in chunk
                ]
                messages = await bot.send_media_group(chat_id, group)
                sent_ids.extend(m.message_id for m in messages)
        except TelegramAPIError as exc:
            all_ok = False
            logger.warning("Failed to send media chunk to admin %s: %s", chat_id, exc)
    return sent_ids, all_ok
