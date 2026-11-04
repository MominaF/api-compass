from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


class FakeDB:
    """Stands in for app.db.session.Database so tests need no running Postgres."""

    def __init__(self, ok: bool) -> None:
        self.ok = ok

    async def ping(self) -> bool:
        return self.ok

    async def dispose(self) -> None:
        pass


@pytest.fixture
def app() -> FastAPI:
    # ASGITransport does not run the lifespan, so tests attach the DB themselves.
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_ok_when_db_reachable(app: FastAPI, client: AsyncClient) -> None:
    app.state.db = FakeDB(ok=True)
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["service"] == "API COMPASS"


async def test_health_degraded_when_db_unreachable(app: FastAPI, client: AsyncClient) -> None:
    app.state.db = FakeDB(ok=False)
    r = await client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["database"] == "unavailable"


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    r = await client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_plain_postgres_url_is_rewritten_to_asyncpg() -> None:
    s = Settings(database_url="postgres://u:p@db.example.com:5432/x")
    assert str(s.database_url).startswith("postgresql+asyncpg://")
