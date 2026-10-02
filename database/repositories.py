"""Data-access layer. Every query is parameterized through SQLAlchemy."""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import MediaData, StatsData, UrlData
from .models import Media, Submission, SubmissionStatus, Url, User, utcnow


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def upsert(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> User:
        """Create the user or refresh profile fields + last_activity_at."""
        now = utcnow()
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, joined_at=now, last_activity_at=now)
            try:
                self.session.add(user)
                await self.session.flush()
            except IntegrityError:  # created concurrently by another update
                await self.session.rollback()
                user = await self.get_by_telegram_id(telegram_id)
                if user is None:
                    raise
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.last_activity_at = now
        await self.session.flush()
        return user

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar_one())


class SubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        text: str,
        urls: Sequence[UrlData],
        media: Sequence[MediaData],
    ) -> Submission:
        now = utcnow()
        submission = Submission(
            user_id=user_id, text=text, status=SubmissionStatus.NEW.value, created_at=now
        )
        submission.urls = [Url(url=u.url, platform=u.platform) for u in urls]
        submission.media = [
            Media(
                telegram_file_id=m.telegram_file_id,
                file_unique_id=m.file_unique_id,
                media_type=m.media_type,
                file_size=m.file_size,
                width=m.width,
                height=m.height,
                duration=m.duration,
                caption=m.caption,
                message_id=m.message_id,
                media_group_id=m.media_group_id,
                created_at=now,
            )
            for m in media
        ]
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def get(self, submission_id: int) -> Submission | None:
        result = await self.session.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def count(self, status: str | None = None) -> int:
        stmt = select(func.count(Submission.id))
        if status is not None:
            stmt = stmt.where(Submission.status == status)
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_page(
        self,
        status: str | None,
        offset: int,
        limit: int,
        *,
        newest_first: bool = True,
    ) -> list[Submission]:
        order = Submission.id.desc() if newest_first else Submission.id.asc()
        stmt = select(Submission).order_by(order).offset(offset).limit(limit)
        if status is not None:
            stmt = stmt.where(Submission.status == status)
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_status(
        self, submission_id: int, status: SubmissionStatus, reviewer_telegram_id: int
    ) -> Submission | None:
        submission = await self.get(submission_id)
        if submission is None:
            return None
        submission.status = status.value
        submission.reviewed_at = utcnow()
        submission.reviewed_by = reviewer_telegram_id
        await self.session.flush()
        return submission

    async def delete(self, submission_id: int) -> bool:
        submission = await self.get(submission_id)
        if submission is None:
            return False
        await self.session.delete(submission)
        await self.session.flush()
        return True

    async def last_created_at_for_telegram_user(self, telegram_id: int) -> datetime | None:
        stmt = (
            select(func.max(Submission.created_at))
            .join(User, User.id == Submission.user_id)
            .where(User.telegram_id == telegram_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def collect(self, day_start: datetime, week_start: datetime) -> StatsData:
        users = await UserRepository(self.session).count()

        rows = await self.session.execute(
            select(Submission.status, func.count(Submission.id)).group_by(Submission.status)
        )
        by_status = {status: int(count) for status, count in rows.all()}

        async def since(moment: datetime) -> int:
            result = await self.session.execute(
                select(func.count(Submission.id)).where(Submission.created_at >= moment)
            )
            return int(result.scalar_one())

        return StatsData(
            total_users=users,
            total_submissions=sum(by_status.values()),
            new=by_status.get(SubmissionStatus.NEW.value, 0),
            reviewed=by_status.get(SubmissionStatus.REVIEWED.value, 0),
            published=by_status.get(SubmissionStatus.PUBLISHED.value, 0),
            rejected=by_status.get(SubmissionStatus.REJECTED.value, 0),
            today=await since(day_start),
            week=await since(week_start),
        )
