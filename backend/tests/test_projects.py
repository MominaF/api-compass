"""Projects API and row-level security, against a real Postgres."""

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.session import Database
from app.models import Project
from tests.conftest import auth

MakeUser = Callable[[], UUID]


async def _create(client: AsyncClient, user: UUID, name: str = "Bookstore API") -> dict[str, str]:
    r = await client.post("/api/v1/projects", json={"name": name}, headers=auth(user))
    assert r.status_code == 201, r.text
    body: dict[str, str] = r.json()
    return body


async def test_project_lifecycle(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    r = await client.post(
        "/api/v1/projects",
        json={"name": "  Bookstore API  ", "description": "Books"},
        headers=auth(user),
    )
    assert r.status_code == 201
    project = r.json()
    assert project["name"] == "Bookstore API"
    assert "owner_id" not in project
    url = f"/api/v1/projects/{project['id']}"

    r = await client.get("/api/v1/projects", headers=auth(user))
    assert [p["id"] for p in r.json()] == [project["id"]]

    r = await client.get(url, headers=auth(user))
    assert r.json() == project

    r = await client.patch(url, json={"name": "Renamed"}, headers=auth(user))
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["description"] == "Books"
    assert r.json()["updated_at"] > project["updated_at"]

    r = await client.patch(url, json={"description": None}, headers=auth(user))
    assert r.json()["description"] is None

    r = await client.delete(url, headers=auth(user))
    assert r.status_code == 204
    assert (await client.get(url, headers=auth(user))).status_code == 404


async def test_list_is_newest_first(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    first = await _create(client, user, "First")
    second = await _create(client, user, "Second")
    r = await client.get("/api/v1/projects", headers=auth(user))
    assert [p["id"] for p in r.json()] == [second["id"], first["id"]]


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 121}], ids=str)
async def test_invalid_names_are_rejected(
    client: AsyncClient, make_user: MakeUser, body: dict[str, str]
) -> None:
    r = await client.post("/api/v1/projects", json=body, headers=auth(make_user()))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_name_cannot_be_cleared(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    project = await _create(client, user)
    r = await client.patch(
        f"/api/v1/projects/{project['id']}", json={"name": None}, headers=auth(user)
    )
    assert r.status_code == 422


async def test_owner_comes_from_token_not_body(
    client: AsyncClient, db: Database, make_user: MakeUser
) -> None:
    user, victim = make_user(), make_user()
    r = await client.post(
        "/api/v1/projects",
        json={"name": "Spoofed", "owner_id": str(victim)},
        headers=auth(user),
    )
    assert r.status_code == 201
    async with db.user_session(victim) as session:
        assert list(await session.scalars(select(Project))) == []


async def test_other_users_cannot_reach_a_project(client: AsyncClient, make_user: MakeUser) -> None:
    owner, other = make_user(), make_user()
    project = await _create(client, owner)
    url = f"/api/v1/projects/{project['id']}"

    assert (await client.get("/api/v1/projects", headers=auth(other))).json() == []
    assert (await client.get(url, headers=auth(other))).status_code == 404
    r = await client.patch(url, json={"name": "Hijacked"}, headers=auth(other))
    assert r.status_code == 404
    assert (await client.delete(url, headers=auth(other))).status_code == 404

    r = await client.get(url, headers=auth(owner))
    assert r.status_code == 200
    assert r.json()["name"] == project["name"]


async def test_requests_without_a_token_cannot_reach_a_project(
    client: AsyncClient, make_user: MakeUser
) -> None:
    project = await _create(client, make_user())
    r = await client.get(f"/api/v1/projects/{project['id']}")
    assert r.status_code == 401


# The tests below bypass the API, proving the database enforces isolation by itself.


async def test_rls_hides_rows_from_other_users(db: Database, make_user: MakeUser) -> None:
    owner, other = make_user(), make_user()
    async with db.user_session(owner) as session:
        session.add(Project(owner_id=owner, name="Mine"))
    async with db.user_session(other) as session:
        assert list(await session.scalars(select(Project))) == []
        deleted = await session.execute(
            text("DELETE FROM projects WHERE owner_id = :o"), {"o": owner}
        )
        assert deleted.rowcount == 0  # type: ignore[attr-defined]
    async with db.user_session(owner) as session:
        assert len(list(await session.scalars(select(Project)))) == 1


async def test_rls_returns_nothing_when_no_user_is_set(db: Database, make_user: MakeUser) -> None:
    owner = make_user()
    async with db.user_session(owner) as session:
        session.add(Project(owner_id=owner, name="Mine"))
    async with db.engine.begin() as conn:
        await conn.execute(text("SET LOCAL ROLE api_compass_app"))
        assert (await conn.execute(text("SELECT count(*) FROM projects"))).scalar_one() == 0


async def test_rls_blocks_inserting_for_another_user(db: Database, make_user: MakeUser) -> None:
    user = make_user()
    with pytest.raises(DBAPIError, match="row-level security"):
        async with db.user_session(user) as session:
            session.add(Project(owner_id=uuid4(), name="Planted"))


async def test_rls_blocks_transferring_a_project(db: Database, make_user: MakeUser) -> None:
    owner, other = make_user(), make_user()
    async with db.user_session(owner) as session:
        project = Project(owner_id=owner, name="Mine")
        session.add(project)
    with pytest.raises(DBAPIError, match="row-level security"):
        async with db.user_session(owner) as session:
            await session.execute(
                text("UPDATE projects SET owner_id = :other WHERE id = :id"),
                {"other": other, "id": project.id},
            )


async def test_app_role_cannot_bypass_rls(db: Database) -> None:
    async with db.engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
                    "WHERE rolname = 'api_compass_app'"
                )
            )
        ).one()
    assert tuple(row) == (False, False, False)


async def test_role_and_user_do_not_leak_through_the_pool(
    db: Database, make_user: MakeUser
) -> None:
    async with db.user_session(make_user()) as session:
        assert await session.scalar(text("SELECT current_user")) == "api_compass_app"
    # Reuse the pooled connection after the transaction has ended.
    async with db.engine.connect() as conn:
        assert await conn.scalar(text("SELECT current_user")) != "api_compass_app"
        setting = await conn.scalar(text("SELECT current_setting('app.current_user_id', true)"))
        assert not setting
