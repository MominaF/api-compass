"""Async SQLAlchemy engine and session management."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

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

    @asynccontextmanager
    async def user_session(self, user_id: UUID) -> AsyncIterator[AsyncSession]:
        """Open a transaction in which row-level security applies to `user_id`.

        The connection's login role may bypass RLS, so the transaction switches to the restricted
        app role. Both settings are transaction-local, so they can't leak through the pool.
        The transaction commits when the block exits and rolls back if it raises.
        """
        async with self.sessionmaker() as session, session.begin():
            await session.execute(text("SET LOCAL ROLE api_compass_app"))
            await session.execute(
                text("SELECT set_config('app.current_user_id', :user_id, true)"),
                {"user_id": str(user_id)},
            )
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
