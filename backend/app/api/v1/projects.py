"""Project endpoints. Row-level security limits every query to the signed-in user's projects,
so another user's project looks the same as one that doesn't exist: a 404."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep
from app.core.errors import NotFoundError
from app.models import Project, SpecVersion
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.schemas.spec import SpecSummary

router = APIRouter(prefix="/projects", tags=["projects"])


async def _get_project(session: AsyncSession, project_id: UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found.")
    return project


async def _with_latest_spec(
    session: AsyncSession, projects: Sequence[Project]
) -> list[ProjectRead]:
    """Build responses that include each project's most recent upload, in one query."""
    latest = await session.scalars(
        select(SpecVersion)
        .where(SpecVersion.project_id.in_([project.id for project in projects]))
        .ext(distinct_on(SpecVersion.project_id))
        .order_by(SpecVersion.project_id, SpecVersion.version_number.desc())
    )
    by_project = {spec.project_id: SpecSummary.model_validate(spec) for spec in latest}
    return [
        ProjectRead.model_validate(project).model_copy(
            update={"latest_spec": by_project.get(project.id)}
        )
        for project in projects
    ]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, user: CurrentUser, db: DbDep) -> Project:
    async with db.user_session(user.id) as session:
        project = Project(owner_id=user.id, name=body.name, description=body.description or None)
        session.add(project)
        await session.flush()
        await session.refresh(project)
        return project


@router.get("", response_model=list[ProjectRead])
async def list_projects(user: CurrentUser, db: DbDep) -> list[ProjectRead]:
    async with db.user_session(user.id) as session:
        result = await session.scalars(select(Project).order_by(Project.created_at.desc()))
        return await _with_latest_spec(session, list(result))


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, user: CurrentUser, db: DbDep) -> ProjectRead:
    async with db.user_session(user.id) as session:
        project = await _get_project(session, project_id)
        return (await _with_latest_spec(session, [project]))[0]


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID, body: ProjectUpdate, user: CurrentUser, db: DbDep
) -> ProjectRead:
    async with db.user_session(user.id) as session:
        project = await _get_project(session, project_id)
        if "name" in body.model_fields_set:
            project.name = body.name
        if "description" in body.model_fields_set:
            project.description = body.description or None
        await session.flush()
        await session.refresh(project)
        return (await _with_latest_spec(session, [project]))[0]


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, user: CurrentUser, db: DbDep) -> None:
    async with db.user_session(user.id) as session:
        await session.delete(await _get_project(session, project_id))
