"""General user commands + fallbacks. Must be registered LAST."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..config import Settings

router = Router(name="user")


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    await message.answer(
        f"{texts.welcome(settings.max_text_length)}\n\n{texts.HELP_FOOTER}",
        reply_markup=keyboards.main_menu(user_id in settings.admin_ids),
    )


@router.message()
async def unknown_message(message: Message, settings: Settings) -> None:
    """Anything the other handlers did not understand."""
    user_id = message.from_user.id  # type: ignore[union-attr]
    await message.answer(
        texts.UNKNOWN_MESSAGE,
        reply_markup=keyboards.main_menu(user_id in settings.admin_ids),
    )


@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    """Buttons from old messages / unknown callback data."""
    await callback.answer(texts.STALE_BUTTON, show_alert=True)
