"""Shared test fixtures. Tokens are signed with a locally generated key, so no test needs a
real Supabase project."""

import json
import os
import time
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jwt import PyJWK
from jwt.algorithms import ECAlgorithm
from sqlalchemy import text

from app.core.auth import TokenVerifier
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

ISSUER = "https://test-project.supabase.co/auth/v1"
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
KID = "test-key"


class StaticKeys:
    """Stands in for PyJWKClient: serves the test public key without any HTTP."""

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        jwk = json.loads(ECAlgorithm.to_jwk(SIGNING_KEY.public_key()))
        return PyJWK.from_dict({**jwk, "alg": "ES256", "kid": KID})


def make_token(
    sub: str,
    *,
    key: Any = SIGNING_KEY,
    algorithm: str = "ES256",
    **overrides: Any,
) -> str:
    claims = {
        "sub": sub,
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": KID})


@pytest.fixture
def verifier() -> TokenVerifier:
    return TokenVerifier(StaticKeys(), issuer=ISSUER)


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    """A real database. Requires migrations; skipped when Postgres isn't running locally."""
    database = Database(Settings())
    if not await database.ping():
        await database.dispose()
        if os.getenv("REQUIRE_DB") == "1":
            pytest.fail("Database is required (REQUIRE_DB=1) but unreachable.")
        pytest.skip("No database reachable at DATABASE_URL.")
    yield database
    await database.dispose()


@pytest.fixture
async def make_user(db: Database) -> AsyncIterator[Callable[[], UUID]]:
    """Creates user IDs for a test and removes their projects afterward. Cleanup runs as the
    login role, which isn't subject to the policies under test."""
    users: list[UUID] = []

    def _make_user() -> UUID:
        users.append(uuid4())
        return users[-1]

    yield _make_user
    async with db.engine.begin() as conn:
        await conn.execute(text("DELETE FROM projects WHERE owner_id = ANY(:ids)"), {"ids": users})


@pytest.fixture
def app(db: Database, verifier: TokenVerifier) -> FastAPI:
    # ASGITransport does not run the lifespan, so tests attach dependencies themselves.
    application = create_app()
    application.state.db = db
    application.state.token_verifier = verifier
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def auth(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(str(user_id))}"}
