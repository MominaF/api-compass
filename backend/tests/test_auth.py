"""Token verification. None of these need a database."""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from app.core.auth import AuthenticatedUser, TokenVerifier, build_token_verifier
from app.core.config import Settings
from app.core.errors import ServiceUnavailableError, UnauthorizedError
from app.main import create_app
from tests.conftest import ISSUER, KID, SIGNING_KEY, make_token


async def test_valid_token_returns_user_from_sub(verifier: TokenVerifier) -> None:
    user_id = uuid4()
    assert await verifier.verify(make_token(str(user_id))) == AuthenticatedUser(id=user_id)


def _alg_none_token() -> str:
    claims = {
        "sub": str(uuid4()),
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 300,
    }
    return jwt.encode(claims, "", algorithm="none", headers={"kid": KID})


def _public_key_as_hs256_secret_token() -> str:
    # The classic algorithm-confusion forgery: sign with the public key as a shared secret.
    public_pem = SIGNING_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = {"alg": "HS256", "kid": KID, "typ": "JWT"}
    claims = {
        "sub": str(uuid4()),
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 300,
    }

    def b64(data: bytes) -> bytes:
        return base64.urlsafe_b64encode(data).rstrip(b"=")

    signing_input = b64(json.dumps(header).encode()) + b"." + b64(json.dumps(claims).encode())
    signature = hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + b64(signature)).decode()


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(make_token(str(uuid4()), exp=int(time.time()) - 60), id="expired"),
        pytest.param(make_token(str(uuid4()), aud="anon"), id="wrong-audience"),
        pytest.param(make_token(str(uuid4()), iss="https://evil.example/auth/v1"), id="wrong-iss"),
        pytest.param(make_token("not-a-uuid"), id="non-uuid-sub"),
        pytest.param(
            make_token(str(uuid4()), key=ec.generate_private_key(ec.SECP256R1())),
            id="signed-by-another-key",
        ),
        pytest.param(_alg_none_token(), id="alg-none"),
        pytest.param(_public_key_as_hs256_secret_token(), id="algorithm-confusion"),
    ],
)
async def test_bad_tokens_are_rejected(verifier: TokenVerifier, token: str) -> None:
    with pytest.raises(UnauthorizedError):
        await verifier.verify(token)


class FailingKeys:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        raise self.exc


async def test_unknown_signing_key_is_unauthorized() -> None:
    verifier = TokenVerifier(FailingKeys(PyJWKClientError("no matching key")), issuer=ISSUER)
    with pytest.raises(UnauthorizedError):
        await verifier.verify(make_token(str(uuid4())))


async def test_unreachable_key_endpoint_is_503_not_401() -> None:
    # An outage must not look like an expired session, or clients would sign users out.
    verifier = TokenVerifier(FailingKeys(PyJWKClientConnectionError("down")), issuer=ISSUER)
    with pytest.raises(ServiceUnavailableError):
        await verifier.verify(make_token(str(uuid4())))


def test_verifier_exists_only_when_supabase_is_configured() -> None:
    assert build_token_verifier(Settings(supabase_url=None)) is None
    assert build_token_verifier(Settings(supabase_url="https://x.supabase.co/")) is not None


@pytest.fixture
async def http(verifier: TokenVerifier) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    application = create_app()
    application.state.token_verifier = verifier
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield application, c


async def test_missing_token_gets_401_envelope(http: tuple[FastAPI, AsyncClient]) -> None:
    _, client = http
    r = await client.get("/api/v1/projects")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_unconfigured_auth_gets_503(http: tuple[FastAPI, AsyncClient]) -> None:
    application, client = http
    application.state.token_verifier = None
    r = await client.get("/api/v1/projects", headers={"Authorization": "Bearer x"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "service_unavailable"
