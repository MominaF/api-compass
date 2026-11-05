"""Specification upload and the records it creates, against a real Postgres."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.api.v1.specs import MAX_SPEC_BYTES, _clean_filename
from app.db.session import Database
from app.models import ApiSchema, Operation, SpecVersion
from tests.conftest import auth

MakeUser = Callable[[], UUID]

BOOKSTORE = Path(__file__).parents[2] / "samples" / "bookstore.openapi.yaml"
MINIMAL = json.dumps({"openapi": "3.0.3", "info": {"title": "Small", "version": "1"}, "paths": {}})
INVALID = '{"openapi": "3.1.0"}'


async def _project(client: AsyncClient, user: UUID) -> str:
    r = await client.post("/api/v1/projects", json={"name": "API"}, headers=auth(user))
    assert r.status_code == 201, r.text
    project_id: str = r.json()["id"]
    return project_id


async def _upload(
    client: AsyncClient,
    user: UUID,
    project_id: str,
    content: str | bytes = MINIMAL,
    filename: str = "spec.json",
) -> Any:
    return await client.post(
        f"/api/v1/projects/{project_id}/specs",
        files={"file": (filename, content)},
        headers=auth(user),
    )


async def test_import_the_bundled_bookstore_api(client: AsyncClient, make_user: MakeUser) -> None:
    """The Phase 2 acceptance test, at the API level."""
    user = make_user()
    project_id = await _project(client, user)
    base = f"/api/v1/projects/{project_id}"

    r = await _upload(client, user, project_id, BOOKSTORE.read_bytes(), "bookstore.openapi.yaml")
    assert r.status_code == 201, r.text
    spec = r.json()
    assert spec["status"] == "ready"
    assert spec["version_number"] == 1
    assert spec["format"] == "yaml"
    assert spec["source_filename"] == "bookstore.openapi.yaml"
    assert spec["openapi_version"] == "3.1.0"
    assert spec["api_title"] == "Bookstore API"
    assert spec["operation_count"] == 12
    assert spec["schema_count"] == 16
    assert spec["validation_errors"] is None
    assert spec["metadata_json"]["security_schemes"]["bearerAuth"]["type"] == "http"
    assert "raw_spec_json" not in spec

    r = await client.get(f"{base}/operations", headers=auth(user))
    operations = r.json()
    assert [(o["method"], o["path"]) for o in operations] == [
        ("POST", "/auth/token"),
        ("GET", "/customers"),
        ("POST", "/customers"),
        ("GET", "/customers/{customerId}"),
        ("PATCH", "/customers/{customerId}"),
        ("GET", "/customers/{customerId}/orders"),
        ("GET", "/books"),
        ("POST", "/books"),
        ("GET", "/books/{bookId}"),
        ("GET", "/orders"),
        ("POST", "/orders"),
        ("GET", "/orders/{orderId}"),
    ]
    assert operations[-2]["summary"] == "Create an order"
    assert operations[-2]["tags"] == ["Orders"]
    assert "responses_json" not in operations[-2]

    r = await client.get(f"{base}/operations/{operations[-2]['id']}", headers=auth(user))
    detail = r.json()
    assert detail["operation_id"] == "createOrder"
    assert detail["raw_pointer"] == "/paths/~1orders/post"
    assert detail["security_json"] == [{"bearerAuth": []}]
    assert detail["request_body_json"]["required"] is True
    assert set(detail["responses_json"]) == {"201", "400", "401", "409"}

    r = await client.get(f"{base}/schemas", headers=auth(user))
    assert len(r.json()) == 16
    customer = next(s for s in r.json() if s["schema_name"] == "Customer")
    assert customer["definition"]["required"] == ["id", "name", "email", "createdAt"]

    r = await client.get(f"{base}/specs/{spec['id']}", headers=auth(user))
    assert r.json()["raw_spec_json"]["paths"]["/orders"]["post"]["operationId"] == "createOrder"

    r = await client.get(f"{base}/specs/{spec['id']}/status", headers=auth(user))
    assert r.json() == {"id": spec["id"], "status": "ready", "validation_errors": None}

    r = await client.get(base, headers=auth(user))
    assert r.json()["latest_spec"]["status"] == "ready"
    assert r.json()["latest_spec"]["operation_count"] == 12
    assert "raw_spec_json" not in r.json()["latest_spec"]


async def test_project_list_includes_each_latest_spec(
    client: AsyncClient, make_user: MakeUser
) -> None:
    user = make_user()
    empty = await _project(client, user)
    uploaded = await _project(client, user)
    await _upload(client, user, uploaded)
    await _upload(client, user, uploaded, INVALID)

    r = await client.get("/api/v1/projects", headers=auth(user))
    by_id = {p["id"]: p["latest_spec"] for p in r.json()}
    assert by_id[empty] is None
    assert by_id[uploaded]["version_number"] == 2
    assert by_id[uploaded]["status"] == "failed"


async def test_invalid_spec_is_recorded_as_failed(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    project_id = await _project(client, user)

    r = await _upload(client, user, project_id, INVALID)
    assert r.status_code == 201
    spec = r.json()
    assert spec["status"] == "failed"
    assert spec["validation_errors"]
    assert spec["operation_count"] == 0
    assert spec["openapi_version"] is None

    base = f"/api/v1/projects/{project_id}"
    assert (await client.get(f"{base}/operations", headers=auth(user))).json() == []
    assert (await client.get(f"{base}/schemas", headers=auth(user))).json() == []


async def test_failed_upload_leaves_the_last_good_version_browsable(
    client: AsyncClient, make_user: MakeUser
) -> None:
    user = make_user()
    project_id = await _project(client, user)
    base = f"/api/v1/projects/{project_id}"

    r = await _upload(client, user, project_id, BOOKSTORE.read_bytes(), "bookstore.yaml")
    first = r.json()
    r = await _upload(client, user, project_id, INVALID)
    second = r.json()
    assert second["version_number"] == 2

    r = await client.get(f"{base}/operations", headers=auth(user))
    assert len(r.json()) == 12

    r = await client.get(f"{base}/specs", headers=auth(user))
    assert [s["id"] for s in r.json()] == [second["id"], first["id"]]
    assert all("raw_spec_json" not in s for s in r.json())


async def test_operations_can_be_read_from_a_specific_version(
    client: AsyncClient, make_user: MakeUser
) -> None:
    user = make_user()
    project_id = await _project(client, user)
    base = f"/api/v1/projects/{project_id}"
    first = (await _upload(client, user, project_id, BOOKSTORE.read_bytes(), "b.yaml")).json()
    await _upload(client, user, project_id)

    r = await client.get(f"{base}/operations", headers=auth(user))
    assert r.json() == []
    r = await client.get(f"{base}/operations", params={"spec_id": first["id"]}, headers=auth(user))
    assert len(r.json()) == 12
    r = await client.get(f"{base}/schemas", params={"spec_id": first["id"]}, headers=auth(user))
    assert len(r.json()) == 16


@pytest.mark.parametrize(
    ("filename", "spec_format"),
    [("a.json", "json"), ("a.yaml", "yaml"), ("a.yml", "yaml"), ("A.JSON", "json")],
)
async def test_accepted_file_types(
    client: AsyncClient, make_user: MakeUser, filename: str, spec_format: str
) -> None:
    user = make_user()
    r = await _upload(client, user, await _project(client, user), filename=filename)
    assert r.json()["status"] == "ready"
    assert r.json()["format"] == spec_format


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("spec.txt", MINIMAL, "Upload a .json, .yaml or .yml file."),
        ("spec", MINIMAL, "Upload a .json, .yaml or .yml file."),
        ("spec.json.exe", MINIMAL, "Upload a .json, .yaml or .yml file."),
        ("spec.json", "", "The file is empty."),
        ("spec.json", "   \n ", "The file is empty."),
    ],
)
async def test_rejected_uploads_create_nothing(
    client: AsyncClient, make_user: MakeUser, filename: str, content: str, message: str
) -> None:
    user = make_user()
    project_id = await _project(client, user)
    r = await _upload(client, user, project_id, content, filename)
    assert r.status_code == 400
    assert r.json()["error"] == {"code": "invalid_upload", "message": message}
    r = await client.get(f"/api/v1/projects/{project_id}/specs", headers=auth(user))
    assert r.json() == []


async def test_upload_without_a_file_is_rejected(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    project_id = await _project(client, user)
    r = await client.post(
        f"/api/v1/projects/{project_id}/specs", data={"other": "x"}, headers=auth(user)
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_upload"


@pytest.mark.parametrize(
    "size",
    [
        MAX_SPEC_BYTES + 1,  # Fits the request allowance, so only the file check can catch it.
        MAX_SPEC_BYTES + 1024 * 1024,  # Caught from the Content-Length header.
    ],
)
async def test_oversized_upload_is_rejected(
    client: AsyncClient, make_user: MakeUser, size: int
) -> None:
    user = make_user()
    project_id = await _project(client, user)
    r = await _upload(client, user, project_id, b" " * size)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "upload_too_large"
    r = await client.get(f"/api/v1/projects/{project_id}/specs", headers=auth(user))
    assert r.json() == []


@pytest.mark.parametrize(
    ("filename", "stored"),
    [
        ("../../etc/spec.json", "spec.json"),
        ("C:\\Users\\me\\spec.json", "spec.json"),
        ("sp\x01ec\x00.json", "spec.json"),
        ("\ud800spec.json", "spec.json"),
        ("a" * 300 + ".json", "a" * 250 + ".json"),
    ],
)
def test_filenames_are_cleaned(filename: str, stored: str) -> None:
    assert _clean_filename(filename) == stored


async def test_stored_filename_has_no_directories(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    r = await _upload(client, user, await _project(client, user), filename="../../etc/spec.json")
    assert r.json()["source_filename"] == "spec.json"


async def test_routes_require_a_token(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    project_id = await _project(client, user)
    r = await client.post(
        f"/api/v1/projects/{project_id}/specs", files={"file": ("spec.json", MINIMAL)}
    )
    assert r.status_code == 401
    r = await client.get(f"/api/v1/projects/{project_id}/operations")
    assert r.status_code == 401


async def test_another_users_records_look_like_they_dont_exist(
    client: AsyncClient, make_user: MakeUser
) -> None:
    owner, other = make_user(), make_user()
    project_id = await _project(client, owner)
    spec = (await _upload(client, owner, project_id, BOOKSTORE.read_bytes(), "b.yaml")).json()
    base = f"/api/v1/projects/{project_id}"
    operation = (await client.get(f"{base}/operations", headers=auth(owner))).json()[0]

    assert (await _upload(client, other, project_id)).status_code == 404
    for path in (
        "/specs",
        f"/specs/{spec['id']}",
        f"/specs/{spec['id']}/status",
        "/operations",
        f"/operations/{operation['id']}",
        "/schemas",
    ):
        r = await client.get(f"{base}{path}", headers=auth(other))
        assert r.status_code == 404, path

    r = await client.get(f"{base}/specs", headers=auth(owner))
    assert len(r.json()) == 1


async def test_records_cant_be_reached_through_another_project(
    client: AsyncClient, make_user: MakeUser
) -> None:
    user = make_user()
    first = await _project(client, user)
    second = await _project(client, user)
    spec = (await _upload(client, user, first, BOOKSTORE.read_bytes(), "b.yaml")).json()
    operation = (
        await client.get(f"/api/v1/projects/{first}/operations", headers=auth(user))
    ).json()[0]

    base = f"/api/v1/projects/{second}"
    for path in (f"/specs/{spec['id']}", f"/operations/{operation['id']}"):
        assert (await client.get(f"{base}{path}", headers=auth(user))).status_code == 404
    r = await client.get(f"{base}/operations", params={"spec_id": spec["id"]}, headers=auth(user))
    assert r.status_code == 404


async def test_unknown_ids_return_404(client: AsyncClient, make_user: MakeUser) -> None:
    user = make_user()
    project_id = await _project(client, user)
    base = f"/api/v1/projects/{project_id}"
    for path in (f"/specs/{uuid4()}", f"/specs/{uuid4()}/status", f"/operations/{uuid4()}"):
        assert (await client.get(f"{base}{path}", headers=auth(user))).status_code == 404
    assert (await _upload(client, user, str(uuid4()))).status_code == 404


async def test_row_level_security_hides_child_records(
    client: AsyncClient, make_user: MakeUser, db: Database
) -> None:
    """The database enforces ownership by itself, even if a route forgets to."""
    owner, other = make_user(), make_user()
    project_id = await _project(client, owner)
    await _upload(client, owner, project_id, BOOKSTORE.read_bytes(), "b.yaml")

    for model in (SpecVersion, Operation, ApiSchema):
        async with db.user_session(owner) as session:
            assert list(await session.scalars(select(model))) != []
        async with db.user_session(other) as session:
            assert list(await session.scalars(select(model))) == []


async def test_row_level_security_blocks_writes_to_another_users_project(
    client: AsyncClient, make_user: MakeUser, db: Database
) -> None:
    owner, other = make_user(), make_user()
    project_id = await _project(client, owner)

    with pytest.raises(DBAPIError, match="row-level security"):
        async with db.user_session(other) as session:
            session.add(
                SpecVersion(
                    project_id=UUID(project_id),
                    version_number=1,
                    source_filename="x.json",
                    format="json",
                    status="ready",
                )
            )


async def test_deleting_a_project_removes_its_records(
    client: AsyncClient, make_user: MakeUser, db: Database
) -> None:
    user = make_user()
    project_id = await _project(client, user)
    spec = (await _upload(client, user, project_id, BOOKSTORE.read_bytes(), "b.yaml")).json()

    r = await client.delete(f"/api/v1/projects/{project_id}", headers=auth(user))
    assert r.status_code == 204

    # Counted as the login role, which row-level security doesn't apply to.
    async with db.engine.connect() as conn:
        for table, column, value in (
            ("spec_versions", "project_id", project_id),
            ("operations", "spec_version_id", spec["id"]),
            ("schemas", "spec_version_id", spec["id"]),
        ):
            count = await conn.scalar(
                text(f"SELECT count(*) FROM {table} WHERE {column} = :id"), {"id": value}
            )
            assert count == 0, table
