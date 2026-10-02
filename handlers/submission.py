"""The submission flow: collect -> preview -> confirm/cancel."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..config import Settings
from ..database.database import Database
from ..schemas import MEDIA_PHOTO, MEDIA_VIDEO, MediaData, UrlData
from ..services.drafts import Draft, DraftStore
from ..services.submissions import CooldownError, get_cooldown_remaining, save_draft
from ..utils.formatting import render_preview
from ..utils.links import LinkInfo, extract_links
from ..utils.telegram import accessible_message, safe_delete, safe_edit
from ..utils.validation import check_file_size, check_video_format, validate_draft

logger = logging.getLogger(__name__)
router = Router(name="submission")

# Keep references to fire-and-forget tasks so they are not garbage collected.
_background_tasks: set[asyncio.Task[None]] = set()


class InSubmission(BaseFilter):
    """Passes only while the user has an open draft (is in submission mode)."""

    async def __call__(self, event: Message, drafts: DraftStore) -> bool:
        return event.from_user is not None and drafts.has(event.from_user.id)


# ─────────────────────────── start / cancel ───────────────────────────
@router.callback_query(F.data == "sub:new")
async def start_submission(
    callback: CallbackQuery, db: Database, drafts: DraftStore, settings: Settings
) -> None:
    message = accessible_message(callback)
    if message is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return

    remaining = await get_cooldown_remaining(
        db, callback.from_user.id, settings.submission_cooldown_seconds
    )
    if remaining > 0:
        await callback.answer(texts.COOLDOWN, show_alert=True)
        return

    draft = drafts.start(callback.from_user.id, message.chat.id)
    await callback.answer()
    sent = await message.answer(
        texts.submission_prompt(settings.max_text_length, settings.max_media_per_submission),
        reply_markup=keyboards.cancel(),
    )
    draft.prompt_message_id = sent.message_id


async def _discard_draft(bot: Bot, drafts: DraftStore, user_id: int, keep_message_id: int | None) -> None:
    draft = drafts.discard(user_id)
    if draft is None:
        return
    for message_id in (draft.preview_message_id, draft.prompt_message_id):
        if message_id is not None and message_id != keep_message_id:
            await safe_delete(bot, draft.chat_id, message_id)


@router.callback_query(F.data == "sub:cancel")
async def cancel_callback(
    callback: CallbackQuery, bot: Bot, drafts: DraftStore, settings: Settings
) -> None:
    message = accessible_message(callback)
    await _discard_draft(
        bot, drafts, callback.from_user.id, message.message_id if message else None
    )
    await callback.answer()
    if message is not None:
        await safe_edit(
            message, texts.CANCELLED, keyboards.main_menu(callback.from_user.id in settings.admin_ids)
        )


@router.message(Command("cancel"))
async def cancel_command(
    message: Message, bot: Bot, drafts: DraftStore, settings: Settings
) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    if not drafts.has(user_id):
        await message.answer(texts.NOTHING_TO_CANCEL)
        return
    await _discard_draft(bot, drafts, user_id, None)
    await message.answer(
        texts.CANCELLED, reply_markup=keyboards.main_menu(user_id in settings.admin_ids)
    )


# ─────────────────────────── collecting content ───────────────────────────
def _entity_urls(message: Message) -> list[str]:
    """Hidden links (text with an embedded URL) are not visible in the text itself."""
    entities = message.entities or message.caption_entities or []
    return [e.url for e in entities if e.type == "text_link" and e.url]


def _check_limits(
    draft: Draft,
    settings: Settings,
    cleaned_text: str,
    new_links: list[LinkInfo],
    has_media: bool,
) -> tuple[str, str] | None:
    """Return (rate-limit key, Arabic error) when this message must be rejected."""
    if has_media and len(draft.media) >= settings.max_media_per_submission:
        return "media_limit", texts.too_many_media(settings.max_media_per_submission)

    parts = draft.text_parts + ([cleaned_text] if cleaned_text else [])
    if len("\n".join(parts)) > settings.max_text_length:
        return "text_limit", texts.text_too_long(settings.max_text_length)

    if len(draft.urls) + len(new_links) > settings.max_urls_per_submission:
        return "url_limit", texts.too_many_urls(settings.max_urls_per_submission)
    return None


async def _accept(
    message: Message,
    bot: Bot,
    drafts: DraftStore,
    settings: Settings,
    media: MediaData | None = None,
) -> None:
    """Add one incoming message (text and/or one media item) to the user's draft.

    Album items arrive as separate messages sharing a media_group_id; all of them
    land in the same draft, so an album becomes a single submission.
    """
    user = message.from_user
    if user is None:
        return
    draft = drafts.get(user.id)
    if draft is None:
        return

    extraction = extract_links(message.text or message.caption or "", _entity_urls(message))
    supported = extraction.supported
    unsupported = extraction.unsupported

    added = False
    async with draft.lock:  # albums deliver several updates at once — serialize them
        if draft.confirming or drafts.get(user.id) is not draft:
            return

        known = {u.url for u in draft.urls}
        new_links = [link for link in supported if link.url not in known]

        rejection = _check_limits(
            draft, settings, extraction.cleaned_text, new_links, media is not None
        )
        if rejection is not None:
            key, error = rejection
            if draft.should_notify(key):
                await message.answer(error)
            return

        if extraction.cleaned_text:
            draft.text_parts.append(extraction.cleaned_text)
            added = True
        for link in new_links:
            assert link.platform is not None
            draft.urls.append(UrlData(url=link.url, platform=link.platform))
            added = True
        if media is not None:
            draft.media.append(media)
            added = True
        if added:
            draft.touch()
            draft.version += 1
            version = draft.version

    warnings: list[str] = []
    if unsupported:
        hosts = list(dict.fromkeys(link.host for link in unsupported))
        warnings.append(texts.unsupported_links(hosts))
    if extraction.invalid:
        warnings.append(texts.INVALID_URL)
    for warning in warnings:
        await message.answer(warning)

    if added:
        _schedule_preview(bot, drafts, draft, settings, version)


def _schedule_preview(
    bot: Bot, drafts: DraftStore, draft: Draft, settings: Settings, version: int
) -> None:
    task = asyncio.create_task(_send_preview(bot, drafts, draft, settings, version))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _send_preview(
    bot: Bot, drafts: DraftStore, draft: Draft, settings: Settings, version: int
) -> None:
    """Debounced: waits a moment so an album / burst of messages produces ONE preview."""
    try:
        await asyncio.sleep(settings.preview_delay_seconds)
        async with draft.lock:
            if (
                draft.version != version  # newer content arrived — its own task will preview
                or draft.confirming
                or drafts.get(draft.user_id) is not draft
            ):
                return
            await safe_delete(bot, draft.chat_id, draft.preview_message_id)
            sent = await bot.send_message(
                draft.chat_id, render_preview(draft), reply_markup=keyboards.preview()
            )
            draft.preview_message_id = sent.message_id
    except TelegramAPIError:
        logger.exception("Failed to send preview to user %s", draft.user_id)
    except Exception:
        logger.exception("Unexpected error while sending preview")


@router.message(InSubmission(), F.text, ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot, drafts: DraftStore, settings: Settings) -> None:
    await _accept(message, bot, drafts, settings)


@router.message(InSubmission(), F.photo)
async def on_photo(message: Message, bot: Bot, drafts: DraftStore, settings: Settings) -> None:
    photo = message.photo[-1]  # type: ignore[index]  # largest size
    error = check_file_size(MEDIA_PHOTO, photo.file_size, settings)
    if error:
        await _reject_media(message, drafts, "photo_size", error)
        return
    media = MediaData(
        telegram_file_id=photo.file_id,
        file_unique_id=photo.file_unique_id,
        media_type=MEDIA_PHOTO,
        file_size=photo.file_size,
        width=photo.width,
        height=photo.height,
        caption=message.caption,
        message_id=message.message_id,
        media_group_id=message.media_group_id,
    )
    await _accept(message, bot, drafts, settings, media)


@router.message(InSubmission(), F.video)
async def on_video(message: Message, bot: Bot, drafts: DraftStore, settings: Settings) -> None:
    video = message.video
    assert video is not None
    error = check_video_format(video.mime_type) or check_file_size(
        MEDIA_VIDEO, video.file_size, settings
    )
    if error:
        await _reject_media(message, drafts, "video_error", error)
        return
    media = MediaData(
        telegram_file_id=video.file_id,
        file_unique_id=video.file_unique_id,
        media_type=MEDIA_VIDEO,
        file_size=video.file_size,
        width=video.width,
        height=video.height,
        duration=video.duration,
        caption=message.caption,
        message_id=message.message_id,
        media_group_id=message.media_group_id,
    )
    await _accept(message, bot, drafts, settings, media)


@router.message(InSubmission(), ~F.text)
async def on_unsupported(message: Message, drafts: DraftStore) -> None:
    """Documents, GIFs, stickers, voice notes, etc."""
    await _reject_media(message, drafts, "unsupported", texts.UNSUPPORTED_CONTENT)


async def _reject_media(message: Message, drafts: DraftStore, key: str, error: str) -> None:
    draft = drafts.get(message.from_user.id)  # type: ignore[union-attr]
    if draft is None or draft.should_notify(key):
        await message.answer(error)


# ─────────────────────────── confirm ───────────────────────────
@router.callback_query(F.data == "sub:confirm")
async def confirm_submission(
    callback: CallbackQuery, bot: Bot, db: Database, drafts: DraftStore, settings: Settings
) -> None:
    user = callback.from_user
    draft = drafts.get(user.id)
    if draft is None:
        await callback.answer(texts.SESSION_EXPIRED, show_alert=True)
        return

    async with draft.lock:
        if draft.confirming:
            await callback.answer()
            return

        error = validate_draft(draft, settings)
        if error is not None:
            await callback.answer(error, show_alert=True)
            return

        draft.confirming = True
        try:
            await save_draft(db, user, draft, settings.submission_cooldown_seconds)
        except CooldownError:
            draft.confirming = False
            await callback.answer(texts.COOLDOWN, show_alert=True)
            return
        except Exception:
            draft.confirming = False
            logger.exception("Failed to save submission for user %s", user.id)
            await callback.answer(texts.SAVE_FAILED, show_alert=True)
            return
        drafts.discard(user.id)

    await callback.answer()
    message = accessible_message(callback)
    await safe_delete(bot, draft.chat_id, draft.prompt_message_id)
    if message is not None:
        await safe_edit(message, texts.SUCCESS, keyboards.after_submit())
    else:
        await bot.send_message(draft.chat_id, texts.SUCCESS, reply_markup=keyboards.after_submit())
