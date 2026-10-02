"""Async engine / session management."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base

logger = logging.getLogger(__name__)


def _sqlite_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


class Database:
    """Owns the engine. Switching to PostgreSQL only needs a different DATABASE_URL
    (e.g. postgresql+asyncpg://...) — no code changes."""

    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        self._is_sqlite = parsed.get_backend_name() == "sqlite"

        kwargs: dict = {"pool_pre_ping": True}
        if self._is_sqlite:
            kwargs["connect_args"] = {"timeout": 30}
            if parsed.database and parsed.database != ":memory:":
                Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_async_engine(url, **kwargs)
        if self._is_sqlite:
            event.listen(self.engine.sync_engine, "connect", _sqlite_pragmas)

        self._factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self) -> None:
        """Create tables if they do not exist yet."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database ready (%s)", self.engine.dialect.name)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """One unit of work: commits on success, rolls back on any error."""
        async with self._factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self.engine.dispose()
