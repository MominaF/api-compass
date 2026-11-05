from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.spec import SpecSummary

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ProjectDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class ProjectCreate(BaseModel):
    name: ProjectName
    description: ProjectDescription | None = None


class ProjectUpdate(BaseModel):
    # Omit a field to leave it unchanged. A name can't be cleared, a description can.
    name: ProjectName = None  # type: ignore[assignment]
    description: ProjectDescription | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    # The most recent upload, whether or not it succeeded. None until the first upload.
    latest_spec: SpecSummary | None = None
