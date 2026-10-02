"""/start and the subscription verification button."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..config import Settings
from ..services.drafts import DraftStore
from ..services.subscription import SubscriptionService
from ..utils.telegram import accessible_message, safe_edit

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings, drafts: DraftStore) -> None:
    # The subscription gate (middleware) already ran: only members reach this point.
    user_id = message.from_user.id  # type: ignore[union-attr]
    drafts.discard(user_id)
    await message.answer(
        texts.welcome(settings.max_text_length),
        reply_markup=keyboards.main_menu(user_id in settings.admin_ids),
    )


@router.callback_query(F.data == "sub:check")
async def check_subscription(
    callback: CallbackQuery, settings: Settings, subscriptions: SubscriptionService
) -> None:
    user_id = callback.from_user.id
    message = accessible_message(callback)
    subscribed = await subscriptions.is_subscribed(user_id, force=True)

    if not subscribed:
        changed = False
        if message is not None:
            changed = await safe_edit(
                message, texts.NOT_SUBSCRIBED, keyboards.gate(settings.channel_url)
            )
        if changed:
            await callback.answer()
        else:  # same text already shown — give feedback through an alert instead
            await callback.answer(texts.NOT_SUBSCRIBED, show_alert=True)
        return

    await callback.answer()
    if message is None:
        return
    await safe_edit(message, texts.VERIFIED)
    await message.answer(
        texts.welcome(settings.max_text_length),
        reply_markup=keyboards.main_menu(user_id in settings.admin_ids),
    )
