from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SpecStatus = Literal["processing", "ready", "failed"]


class _FromOrm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SpecStatusRead(_FromOrm):
    id: UUID
    status: SpecStatus
    validation_errors: list[dict[str, Any]] | None


class SpecSummary(SpecStatusRead):
    version_number: int
    source_filename: str
    format: str
    openapi_version: str | None
    api_title: str | None
    operation_count: int
    schema_count: int
    created_at: datetime


class SpecRead(SpecSummary):
    metadata_json: dict[str, Any] | None


class SpecDetail(SpecRead):
    raw_spec_json: dict[str, Any] | None


class OperationSummary(_FromOrm):
    id: UUID
    operation_id: str | None
    method: str
    path: str
    summary: str | None
    tags: list[str]


class OperationRead(OperationSummary):
    spec_version_id: UUID
    description: str | None
    parameters_json: list[Any]
    request_body_json: dict[str, Any] | None
    responses_json: dict[str, Any]
    security_json: list[Any]
    raw_pointer: str


class SchemaRead(_FromOrm):
    id: UUID
    schema_name: str
    schema_type: str | None
    # Not named schema_json, which would shadow a Pydantic method.
    definition: Any = Field(validation_alias="schema_json")
    description: str | None
