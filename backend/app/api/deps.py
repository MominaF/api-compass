"""Dependencies shared by authenticated routes."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import AuthenticatedUser, TokenVerifier
from app.core.errors import ServiceUnavailableError, UnauthorizedError
from app.db.session import Database

_bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser:
    verifier: TokenVerifier | None = request.app.state.token_verifier
    if verifier is None:
        raise ServiceUnavailableError("Sign-in is not configured on this server.")
    if credentials is None:
        raise UnauthorizedError("Sign in to continue.")
    return await verifier.verify(credentials.credentials)


DbDep = Annotated[Database, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
