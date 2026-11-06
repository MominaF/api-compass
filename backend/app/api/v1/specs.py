"""Specification import and the records it creates. Row-level security limits every query to the
signed-in user's projects, so these routes only need to check that the project exists."""

import asyncio
import re
from dataclasses import asdict
from pathlib import PurePosixPath
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from pydantic import StringConstraints
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, undefer
from starlette.datastructures import UploadFile

from app.api.deps import CurrentUser, DbDep
from app.core.errors import InvalidUploadError, NotFoundError, UploadTooLargeError
from app.models import ApiSchema, Operation, Project, SpecVersion
from app.schemas.spec import (
    OperationRead,
    OperationSummary,
    SchemaRead,
    SpecDetail,
    SpecRead,
    SpecStatusRead,
)
from app.services.openapi_parser import ParsedSpec, SpecFormat, SpecParseError, parse_spec

router = APIRouter(prefix="/projects/{project_id}", tags=["specifications"])

MAX_SPEC_BYTES = 5 * 1024 * 1024
# The multipart boundary and headers add a little to the size of the request.
_MAX_REQUEST_BYTES = MAX_SPEC_BYTES + 64 * 1024
_TOO_LARGE_MESSAGE = "The file is larger than the 5 MB limit."
_FORMATS: dict[str, SpecFormat] = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}


async def _require_project(session: AsyncSession, project_id: UUID) -> None:
    if await session.get(Project, project_id) is None:
        raise NotFoundError("Project not found.")


async def _get_spec(session: AsyncSession, project_id: UUID, spec_id: UUID) -> SpecVersion:
    spec = await session.scalar(
        select(SpecVersion).where(SpecVersion.id == spec_id, SpecVersion.project_id == project_id)
    )
    if spec is None:
        raise NotFoundError("Specification not found.")
    return spec


async def _browsable_spec_id(
    session: AsyncSession, project_id: UUID, spec_id: UUID | None
) -> UUID | None:
    """The requested version, or else the newest one that imported successfully."""
    await _require_project(session, project_id)
    if spec_id is not None:
        return (await _get_spec(session, project_id, spec_id)).id
    latest_ready: UUID | None = await session.scalar(
        select(SpecVersion.id)
        .where(SpecVersion.project_id == project_id, SpecVersion.status == "ready")
        .order_by(SpecVersion.version_number.desc())
        .limit(1)
    )
    return latest_ready


def _clean_filename(name: str) -> str:
    # Keep only the final path segment and text that can be stored and displayed safely.
    name = PurePosixPath(name.replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).encode("utf-8", "ignore").decode()
    return name[-255:]


async def _read_upload(request: Request) -> tuple[str, SpecFormat, bytes]:
    # Check the size before parsing the body, since parsing would first spool it all to disk. This
    # is why the route reads the form itself: a File() parameter is parsed before the route runs.
    try:
        length = int(request.headers["content-length"])
    except (KeyError, ValueError) as exc:
        raise InvalidUploadError("The upload must include a valid Content-Length.") from exc
    if length > _MAX_REQUEST_BYTES:
        raise UploadTooLargeError(_TOO_LARGE_MESSAGE)

    async with request.form(max_files=1, max_fields=1) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise InvalidUploadError("Attach the specification as a file named 'file'.")
        filename = _clean_filename(upload.filename or "")
        spec_format = _FORMATS.get(PurePosixPath(filename).suffix.lower())
        if spec_format is None:
            raise InvalidUploadError("Upload a .json, .yaml or .yml file.")
        content = await upload.read(MAX_SPEC_BYTES + 1)

    if len(content) > MAX_SPEC_BYTES:
        raise UploadTooLargeError(_TOO_LARGE_MESSAGE)
    if not content.strip():
        raise InvalidUploadError("The file is empty.")
    return filename, spec_format, content


def _records(spec_version_id: UUID, parsed: ParsedSpec) -> list[Operation | ApiSchema]:
    operations: list[Operation | ApiSchema] = [
        Operation(
            spec_version_id=spec_version_id,
            position=position,
            operation_id=operation.operation_id,
            method=operation.method,
            path=operation.path,
            summary=operation.summary,
            description=operation.description,
            tags=operation.tags,
            parameters_json=operation.parameters,
            request_body_json=operation.request_body,
            responses_json=operation.responses,
            security_json=operation.security,
            raw_pointer=operation.pointer,
        )
        for position, operation in enumerate(parsed.operations)
    ]
    schemas = [
        ApiSchema(
            spec_version_id=spec_version_id,
            schema_name=schema.name,
            schema_type=schema.type,
            schema_json=schema.schema,
            description=schema.description,
        )
        for schema in parsed.schemas
    ]
    return [*operations, *schemas]


@router.post(
    "/specs",
    response_model=SpecRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and import a specification",
    description=(
        "A file that can't be imported still creates a version, with status `failed` and the "
        "reasons in `validation_errors`. A file rejected before parsing (wrong type, too large or "
        "empty) creates nothing and returns an error."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def upload_spec(
    project_id: UUID, request: Request, user: CurrentUser, db: DbDep
) -> SpecVersion:
    async with db.user_session(user.id) as session:
        await _require_project(session, project_id)

    filename, spec_format, content = await _read_upload(request)

    # Parsing is CPU-bound, so it runs in a thread and outside any database transaction.
    parsed: ParsedSpec | None = None
    errors: list[dict[str, Any]] | None = None
    try:
        parsed = await asyncio.to_thread(parse_spec, content, spec_format)
    except SpecParseError as exc:
        errors = [asdict(issue) for issue in exc.issues]

    async with db.user_session(user.id) as session:
        # The lock makes concurrent uploads to one project take turns picking a version number.
        if await session.get(Project, project_id, with_for_update=True) is None:
            raise NotFoundError("Project not found.")
        latest = await session.scalar(
            select(func.max(SpecVersion.version_number)).where(SpecVersion.project_id == project_id)
        )
        spec = SpecVersion(
            project_id=project_id,
            version_number=(latest or 0) + 1,
            source_filename=filename,
            format=spec_format,
            status="ready" if parsed else "failed",
            validation_errors=errors,
        )
        if parsed:
            spec.openapi_version = parsed.openapi_version
            spec.api_title = parsed.api_title
            spec.metadata_json = parsed.metadata
            spec.raw_spec_json = parsed.raw
            spec.operation_count = len(parsed.operations)
            spec.schema_count = len(parsed.schemas)
        session.add(spec)
        await session.flush()
        if parsed:
            session.add_all(_records(spec.id, parsed))
            await session.flush()
        await session.refresh(spec, attribute_names=["created_at"])
        return spec


@router.get("/specs", response_model=list[SpecRead])
async def list_specs(project_id: UUID, user: CurrentUser, db: DbDep) -> list[SpecVersion]:
    async with db.user_session(user.id) as session:
        await _require_project(session, project_id)
        result = await session.scalars(
            select(SpecVersion)
            .where(SpecVersion.project_id == project_id)
            .order_by(SpecVersion.version_number.desc())
        )
        return list(result)


@router.get("/specs/{spec_id}", response_model=SpecDetail)
async def get_spec(project_id: UUID, spec_id: UUID, user: CurrentUser, db: DbDep) -> SpecVersion:
    async with db.user_session(user.id) as session:
        spec = await session.scalar(
            select(SpecVersion)
            .options(undefer(SpecVersion.raw_spec_json))
            .where(SpecVersion.id == spec_id, SpecVersion.project_id == project_id)
        )
        if spec is None:
            raise NotFoundError("Specification not found.")
        return spec


@router.get("/specs/{spec_id}/status", response_model=SpecStatusRead)
async def get_spec_status(
    project_id: UUID, spec_id: UUID, user: CurrentUser, db: DbDep
) -> SpecVersion:
    async with db.user_session(user.id) as session:
        return await _get_spec(session, project_id, spec_id)


SpecIdQuery = Annotated[
    UUID | None, Query(description="A specification version. Defaults to the newest ready one.")
]


# Postgres text can't hold NUL, so refuse it here rather than fail in the query.
_FilterText = Annotated[str, StringConstraints(max_length=200, pattern=r"^[^\x00]*$")]


def _search_conditions(query: str) -> list[ColumnElement[bool]]:
    """Every word must appear in some searchable field, so "post orders" finds POST /orders."""
    searchable = func.concat_ws(
        " ",
        Operation.method,
        Operation.path,
        Operation.operation_id,
        Operation.summary,
        Operation.description,
        func.array_to_string(Operation.tags, " "),
    )
    return [searchable.icontains(word, autoescape=True) for word in query.split()]


@router.get("/operations", response_model=list[OperationSummary])
async def list_operations(
    project_id: UUID,
    user: CurrentUser,
    db: DbDep,
    spec_id: SpecIdQuery = None,
    method: Annotated[
        list[_FilterText] | None,
        Query(description="HTTP methods to include. Repeat for several."),
    ] = None,
    tag: Annotated[_FilterText | None, Query(description="Only operations with this tag.")] = None,
    q: Annotated[
        _FilterText | None,
        Query(
            description=(
                "Words to find in the method, path, operation ID, summary, description or tags."
            )
        ),
    ] = None,
) -> list[Operation]:
    conditions = _search_conditions(q or "")
    if method:
        conditions.append(Operation.method.in_([name.upper() for name in method]))
    if tag is not None:
        conditions.append(Operation.tags.contains([tag]))

    async with db.user_session(user.id) as session:
        browsable = await _browsable_spec_id(session, project_id, spec_id)
        result = await session.scalars(
            select(Operation)
            .options(
                load_only(
                    Operation.operation_id,
                    Operation.method,
                    Operation.path,
                    Operation.summary,
                    Operation.description,
                    Operation.tags,
                )
            )
            .where(Operation.spec_version_id == browsable, *conditions)
            .order_by(Operation.position)
        )
        return list(result)


@router.get("/operations/{operation_id}", response_model=OperationRead)
async def get_operation(
    project_id: UUID, operation_id: UUID, user: CurrentUser, db: DbDep
) -> Operation:
    async with db.user_session(user.id) as session:
        operation = await session.scalar(
            select(Operation)
            .join(SpecVersion, Operation.spec_version_id == SpecVersion.id)
            .where(Operation.id == operation_id, SpecVersion.project_id == project_id)
        )
        if operation is None:
            raise NotFoundError("Operation not found.")
        return operation


@router.get("/schemas", response_model=list[SchemaRead])
async def list_schemas(
    project_id: UUID, user: CurrentUser, db: DbDep, spec_id: SpecIdQuery = None
) -> list[ApiSchema]:
    async with db.user_session(user.id) as session:
        browsable = await _browsable_spec_id(session, project_id, spec_id)
        result = await session.scalars(
            select(ApiSchema)
            .where(ApiSchema.spec_version_id == browsable)
            .order_by(ApiSchema.schema_name)
        )
        return list(result)
