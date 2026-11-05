"""Verifies Supabase Auth access tokens against the project's public signing keys (JWKS).

The user's identity comes only from a verified token, never from anything else the client sends.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError, UnauthorizedError

# Asymmetric only. Accepting HS256 here would let a public key be used as a shared secret.
ALLOWED_ALGORITHMS = ["ES256", "RS256"]
AUDIENCE = "authenticated"


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


class TokenVerifier:
    def __init__(self, keys: SigningKeySource, issuer: str) -> None:
        self._keys = keys
        self._issuer = issuer

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            # PyJWKClient uses blocking HTTP when its key cache misses.
            key = await asyncio.to_thread(self._keys.get_signing_key_from_jwt, token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
            return AuthenticatedUser(id=UUID(claims["sub"]))
        except PyJWKClientConnectionError as exc:
            raise ServiceUnavailableError("Could not verify the session. Try again.") from exc
        except (PyJWTError, ValueError) as exc:
            raise UnauthorizedError("The session is invalid or has expired.") from exc


def build_token_verifier(settings: Settings) -> TokenVerifier | None:
    """Return a verifier for the configured project, or None if Supabase is not configured."""
    if not settings.supabase_url:
        return None
    base = settings.supabase_url.rstrip("/")
    return TokenVerifier(
        PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json", cache_keys=True, timeout=5),
        issuer=f"{base}/auth/v1",
    )
