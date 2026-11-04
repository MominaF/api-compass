"""Integration test against a real Postgres. Skipped locally when no database is running;
CI sets REQUIRE_DB=1 so a missing database fails the build instead."""

import os

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import Database


async def test_database_reachable_and_pgvector_installed() -> None:
    db = Database(Settings())
    try:
        if not await db.ping():
            if os.getenv("REQUIRE_DB") == "1":
                pytest.fail("Database is required (REQUIRE_DB=1) but unreachable.")
            pytest.skip("No database reachable at DATABASE_URL.")
        async with db.engine.connect() as conn:
            available = await conn.scalar(
                text("SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")
            )
        assert available == 1, "pgvector extension is not available on this Postgres server"
    finally:
        await db.dispose()
