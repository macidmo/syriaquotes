"""Admin panel (inside Telegram). Access is re-checked on every action by
AdminGuardMiddleware."""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..config import Settings
from ..database.database import Database
from ..database.models import Submission, SubmissionStatus, utcnow
from ..database.repositories import StatsRepository, SubmissionRepository
from ..middlewares import AdminGuardMiddleware
from ..services.admin_view import AdminMediaTracker, send_submission_media
from ..utils import formatting
from ..utils.telegram import accessible_message, safe_delete, safe_edit

logger = logging.getLogger(__name__)

PAGE_SIZE = 8
_NEW = SubmissionStatus.NEW.value
_ACTION_RE = re.compile(r"^adm:(view|rev|rej|del|delok):(\d+):([na]\d+)$")

router = Router(name="admin")
router.message.filter(F.chat.type == ChatType.PRIVATE)
_guard = AdminGuardMiddleware()
router.message.middleware(_guard)
router.callback_query.middleware(_guard)


# ─────────────────────────── helpers ───────────────────────────
def _parse_action(data: str | None) -> tuple[str, int, str] | None:
    match = _ACTION_RE.match(data or "")
    if match is None:
        return None
    return match.group(1), int(match.group(2)), match.group(3)


def _parse_int(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    tail = data[len(prefix):]
    return int(tail) if tail.isdigit() else None


async def _require_message(callback: CallbackQuery) -> Message | None:
    message = accessible_message(callback)
    if message is None:
        await callback.answer(texts.MESSAGE_UNAVAILABLE, show_alert=True)
    return message


async def _show_panel(message: Message, db: Database, bot: Bot, tracker: AdminMediaTracker) -> None:
    async with db.session() as session:
        new_count = await SubmissionRepository(session).count(_NEW)
    await tracker.clear(bot, message.chat.id)
    await safe_edit(message, formatting.render_panel(new_count), keyboards.admin_panel())


async def _present(
    bot: Bot,
    message: Message,
    sub: Submission,
    ctx: str,
    tracker: AdminMediaTracker,
    settings: Settings,
    *,
    position: tuple[int, int] | None = None,
) -> None:
    """Show one submission: its media (as an album when possible) followed by the
    detail card with action buttons at the bottom of the chat."""
    chat_id = message.chat.id
    await tracker.clear(bot, chat_id)

    markup = keyboards.submission_actions(
        sub.id,
        sub.status,
        ctx,
        has_prev=bool(position and position[0] > 1),
        has_next=bool(position and position[0] < position[1]),
    )

    if not sub.media:
        card = formatting.render_submission_card(sub, settings.timezone, position=position)
        await safe_edit(message, card, markup)
        return

    await safe_delete(bot, chat_id, message.message_id)
    sent_ids, ok = await send_submission_media(bot, chat_id, sub.media)
    tracker.remember(chat_id, sent_ids)
    card = formatting.render_submission_card(
        sub, settings.timezone, position=position, media_failed=not ok
    )
    await bot.send_message(chat_id, card, reply_markup=markup)


async def _show_new(
    bot: Bot,
    message: Message,
    db: Database,
    tracker: AdminMediaTracker,
    settings: Settings,
    offset: int,
) -> None:
    """The review queue: oldest new submission first, one at a time."""
    async with db.session() as session:
        repo = SubmissionRepository(session)
        total = await repo.count(_NEW)
        subs: list[Submission] = []
        if total:
            offset = max(0, min(offset, total - 1))
            subs = await repo.get_page(_NEW, offset, 1, newest_first=False)

    if not subs:
        await tracker.clear(bot, message.chat.id)
        await safe_edit(message, texts.NO_NEW, keyboards.back_to_panel())
        return
    await _present(
        bot, message, subs[0], f"n{offset}", tracker, settings, position=(offset + 1, total)
    )


async def _show_all(
    bot: Bot, message: Message, db: Database, tracker: AdminMediaTracker, page: int
) -> None:
    async with db.session() as session:
        repo = SubmissionRepository(session)
        total = await repo.count()
        pages = max(1, math.ceil(total / PAGE_SIZE))
        page = max(1, min(page, pages))
        subs = await repo.get_page(None, (page - 1) * PAGE_SIZE, PAGE_SIZE) if total else []

    await tracker.clear(bot, message.chat.id)
    if not subs:
        await safe_edit(message, texts.NO_SUBMISSIONS, keyboards.back_to_panel())
        return
    await safe_edit(
        message,
        formatting.render_list_header(page, pages, total),
        keyboards.submissions_list(subs, page, pages),
    )


async def _return_to_list(
    bot: Bot,
    message: Message,
    db: Database,
    tracker: AdminMediaTracker,
    settings: Settings,
    ctx: str,
) -> None:
    num = int(ctx[1:])
    if ctx[0] == "n":
        await _show_new(bot, message, db, tracker, settings, num)
    else:
        await _show_all(bot, message, db, tracker, num)


# ─────────────────────────── panel ───────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message, db: Database) -> None:
    async with db.session() as session:
        new_count = await SubmissionRepository(session).count(_NEW)
    await message.answer(formatting.render_panel(new_count), reply_markup=keyboards.admin_panel())


@router.callback_query(F.data.in_({"adm:home", "adm:refresh"}))
async def panel(
    callback: CallbackQuery, bot: Bot, db: Database, media_tracker: AdminMediaTracker
) -> None:
    message = await _require_message(callback)
    if message is None:
        return
    await callback.answer()
    await _show_panel(message, db, bot, media_tracker)


@router.callback_query(F.data == "adm:exit")
async def exit_panel(
    callback: CallbackQuery, bot: Bot, settings: Settings, media_tracker: AdminMediaTracker
) -> None:
    message = await _require_message(callback)
    if message is None:
        return
    await callback.answer()
    await media_tracker.clear(bot, message.chat.id)
    await safe_edit(
        message,
        texts.welcome(settings.max_text_length),
        keyboards.main_menu(is_admin=True),
    )


@router.callback_query(F.data == "adm:noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ─────────────────────────── lists ───────────────────────────
@router.callback_query(F.data.startswith("adm:new:"))
async def new_submissions(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    media_tracker: AdminMediaTracker,
) -> None:
    message = await _require_message(callback)
    offset = _parse_int(callback.data, "adm:new:")
    if message is None:
        return
    if offset is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    await _show_new(bot, message, db, media_tracker, settings, offset)


@router.callback_query(F.data.startswith("adm:all:"))
async def all_submissions(
    callback: CallbackQuery, bot: Bot, db: Database, media_tracker: AdminMediaTracker
) -> None:
    message = await _require_message(callback)
    page = _parse_int(callback.data, "adm:all:")
    if message is None:
        return
    if page is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    await _show_all(bot, message, db, media_tracker, page)


@router.callback_query(F.data == "adm:stats")
async def stats(
    callback: CallbackQuery, bot: Bot, db: Database, settings: Settings, media_tracker: AdminMediaTracker
) -> None:
    message = await _require_message(callback)
    if message is None:
        return
    now_local = datetime.now(settings.timezone)
    day_start = (
        now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    week_start = utcnow() - timedelta(days=7)
    async with db.session() as session:
        data = await StatsRepository(session).collect(day_start, week_start)
    await callback.answer()
    await media_tracker.clear(bot, message.chat.id)
    await safe_edit(message, formatting.render_stats(data), keyboards.stats_keyboard())


# ─────────────────────────── single submission ───────────────────────────
@router.callback_query(F.data.startswith("adm:view:"))
async def view_submission(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    media_tracker: AdminMediaTracker,
) -> None:
    message = await _require_message(callback)
    parsed = _parse_action(callback.data)
    if message is None:
        return
    if parsed is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    _, sub_id, ctx = parsed

    position: tuple[int, int] | None = None
    async with db.session() as session:
        repo = SubmissionRepository(session)
        sub = await repo.get(sub_id)
        if sub is not None and ctx[0] == "n":
            position = (int(ctx[1:]) + 1, await repo.count(_NEW))

    if sub is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        await _return_to_list(bot, message, db, media_tracker, settings, ctx)
        return
    await callback.answer()
    await _present(bot, message, sub, ctx, media_tracker, settings, position=position)


async def _change_status(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    tracker: AdminMediaTracker,
    status: SubmissionStatus,
    toast: str,
) -> None:
    message = await _require_message(callback)
    parsed = _parse_action(callback.data)
    if message is None:
        return
    if parsed is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    _, sub_id, ctx = parsed

    async with db.session() as session:
        sub = await SubmissionRepository(session).set_status(
            sub_id, status, callback.from_user.id
        )

    if sub is None:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        await _return_to_list(bot, message, db, tracker, settings, ctx)
        return

    logger.info("Admin %s set submission #%s to %s", callback.from_user.id, sub_id, status.value)
    await callback.answer(toast)
    if ctx[0] == "n":  # the item left the "new" queue — continue with the next one
        await _show_new(bot, message, db, tracker, settings, int(ctx[1:]))
    else:
        await _present(bot, message, sub, ctx, tracker, settings)


@router.callback_query(F.data.startswith("adm:rev:"))
async def mark_reviewed(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    media_tracker: AdminMediaTracker,
) -> None:
    await _change_status(
        callback, bot, db, settings, media_tracker, SubmissionStatus.REVIEWED, texts.REVIEWED_TOAST
    )


@router.callback_query(F.data.startswith("adm:rej:"))
async def mark_rejected(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    media_tracker: AdminMediaTracker,
) -> None:
    await _change_status(
        callback, bot, db, settings, media_tracker, SubmissionStatus.REJECTED, texts.REJECTED_TOAST
    )


@router.callback_query(F.data.startswith("adm:del:"))
async def ask_delete(callback: CallbackQuery) -> None:
    message = await _require_message(callback)
    parsed = _parse_action(callback.data)
    if message is None:
        return
    if parsed is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    _, sub_id, ctx = parsed
    await callback.answer()
    await safe_edit(
        message,
        f"{texts.DELETE_CONFIRM}\n\n#{sub_id}",
        keyboards.confirm_delete(sub_id, ctx),
    )


@router.callback_query(F.data.startswith("adm:delok:"))
async def confirm_delete(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    media_tracker: AdminMediaTracker,
) -> None:
    message = await _require_message(callback)
    parsed = _parse_action(callback.data)
    if message is None:
        return
    if parsed is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    _, sub_id, ctx = parsed

    async with db.session() as session:
        deleted = await SubmissionRepository(session).delete(sub_id)

    if not deleted:
        await callback.answer(texts.NOT_FOUND, show_alert=True)
        await _return_to_list(bot, message, db, media_tracker, settings, ctx)
        return

    logger.info("Admin %s deleted submission #%s", callback.from_user.id, sub_id)
    await callback.answer()
    await media_tracker.clear(bot, message.chat.id)
    await safe_edit(message, texts.DELETED, keyboards.after_delete(ctx))
