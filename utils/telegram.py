"""Thin, failure-tolerant wrappers around common Telegram calls."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


def accessible_message(callback: CallbackQuery) -> Message | None:
    """callback.message can be an 'inaccessible' stub for very old messages."""
    return callback.message if isinstance(callback.message, Message) else None


async def safe_delete(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramAPIError as exc:
        logger.debug("Could not delete message %s in %s: %s", message_id, chat_id, exc)


async def safe_edit(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> bool:
    """Edit a message's text.

    Returns False only when Telegram says nothing changed ("message is not modified").
    If the message cannot be edited for any other reason, a new message is sent instead.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        logger.debug("edit_text failed (%s) — sending a new message", exc)
    except TelegramAPIError as exc:
        logger.warning("edit_text failed: %s", exc)
        return False
    try:
        await message.answer(text, reply_markup=reply_markup)
        return True
    except TelegramAPIError as exc:
        logger.warning("Fallback send failed: %s", exc)
        return False
