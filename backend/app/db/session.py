"""Async SQLAlchemy engine and session management."""

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.db_connect_timeout_seconds
        self.engine: AsyncEngine = create_async_engine(
            str(settings.database_url),
            pool_pre_ping=True,
            connect_args={"timeout": self._timeout},
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def ping(self) -> bool:
        """Return True if the database answers `SELECT 1` within the timeout."""
        try:
            async with asyncio.timeout(self._timeout + 1):
                async with self.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def dispose(self) -> None:
        await self.engine.dispose()
