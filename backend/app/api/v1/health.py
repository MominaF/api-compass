from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    database: Literal["ok", "unavailable"]


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response) -> HealthResponse:
    """Liveness and dependency check. Returns 503 when the database is unreachable."""
    settings = get_settings()
    db_ok: bool = await request.app.state.db.ping()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        service=settings.app_name,
        version=request.app.version,
        environment=settings.environment,
        database="ok" if db_ok else "unavailable",
    )
