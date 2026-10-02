"""Business logic for saving a confirmed draft."""
from __future__ import annotations

import logging
import math
from datetime import datetime

from aiogram.types import User as TgUser

from ..database.database import Database
from ..database.models import utcnow
from ..database.repositories import SubmissionRepository, UserRepository
from .drafts import Draft

logger = logging.getLogger(__name__)


class CooldownError(Exception):
    def __init__(self, remaining: int) -> None:
        super().__init__(f"cooldown: {remaining}s remaining")
        self.remaining = remaining


def remaining_cooldown(last_created: datetime | None, cooldown_seconds: int) -> int:
    if last_created is None or cooldown_seconds <= 0:
        return 0
    elapsed = (utcnow() - last_created).total_seconds()
    return max(0, math.ceil(cooldown_seconds - elapsed))


async def get_cooldown_remaining(db: Database, telegram_id: int, cooldown_seconds: int) -> int:
    async with db.session() as session:
        last = await SubmissionRepository(session).last_created_at_for_telegram_user(telegram_id)
    return remaining_cooldown(last, cooldown_seconds)


async def save_draft(
    db: Database, tg_user: TgUser, draft: Draft, cooldown_seconds: int
) -> int:
    """Persist the draft as one Submission (+ its URLs and media). Returns its id.

    Raises CooldownError when the user submitted too recently. The whole operation
    runs in one transaction.
    """
    async with db.session() as session:
        submissions = SubmissionRepository(session)
        last = await submissions.last_created_at_for_telegram_user(tg_user.id)
        remaining = remaining_cooldown(last, cooldown_seconds)
        if remaining > 0:
            raise CooldownError(remaining)

        user = await UserRepository(session).upsert(
            tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name
        )
        submission = await submissions.create(user.id, draft.text, draft.urls, draft.media)
        submission_id = submission.id

    logger.info(
        "Submission #%s saved (user=%s, media=%s, urls=%s)",
        submission_id,
        tg_user.id,
        len(draft.media),
        len(draft.urls),
    )
    return submission_id
