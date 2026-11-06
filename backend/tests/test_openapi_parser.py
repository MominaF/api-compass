"""The OpenAPI parser, including hostile uploads. Needs no database."""

import contextlib
import http.server
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.services import openapi_parser
from app.services.openapi_parser import ParsedSpec, SpecParseError, parse_spec

BOOKSTORE = Path(__file__).parents[2] / "samples" / "bookstore.openapi.yaml"


def _spec(version: str = "3.1.0", **fields: Any) -> dict[str, Any]:
    return {
        "openapi": version,
        "info": {"title": "T", "version": "1"},
        "paths": {},
        **fields,
    }


def _ok_responses() -> dict[str, Any]:
    return {"200": {"description": "OK"}}


def _parse(document: dict[str, Any]) -> ParsedSpec:
    return parse_spec(json.dumps(document).encode(), "json")


def _issues(content: bytes, spec_format: openapi_parser.SpecFormat = "json") -> list[str]:
    with pytest.raises(SpecParseError) as exc:
        parse_spec(content, spec_format)
    return [issue.message for issue in exc.value.issues]


def _with_schema(schema: Any) -> dict[str, Any]:
    response = {"description": "OK", "content": {"application/json": {"schema": schema}}}
    return _spec(paths={"/x": {"get": {"responses": {"200": response}}}})


@pytest.fixture
def bookstore() -> ParsedSpec:
    return parse_spec(BOOKSTORE.read_bytes(), "yaml")


def test_bookstore_operations_in_document_order(bookstore: ParsedSpec) -> None:
    assert [(o.method, o.path, o.operation_id) for o in bookstore.operations] == [
        ("POST", "/auth/token", "createToken"),
        ("GET", "/customers", "listCustomers"),
        ("POST", "/customers", "createCustomer"),
        ("GET", "/customers/{customerId}", "getCustomer"),
        ("PATCH", "/customers/{customerId}", "updateCustomer"),
        ("GET", "/customers/{customerId}/orders", "listCustomerOrders"),
        ("GET", "/books", "listBooks"),
        ("POST", "/books", "createBook"),
        ("GET", "/books/{bookId}", "getBook"),
        ("GET", "/orders", "listOrders"),
        ("POST", "/orders", "createOrder"),
        ("GET", "/orders/{orderId}", "getOrder"),
    ]


def test_bookstore_metadata(bookstore: ParsedSpec) -> None:
    assert bookstore.openapi_version == "3.1.0"
    assert bookstore.api_title == "Bookstore API"
    assert bookstore.metadata["version"] == "1.0.0"
    assert bookstore.metadata["contact"]["name"] == "Bookstore API Support"
    assert len(bookstore.metadata["servers"]) == 2
    assert [t["name"] for t in bookstore.metadata["tags"]][0] == "Authentication"
    assert bookstore.metadata["security_schemes"]["bearerAuth"]["scheme"] == "bearer"


def test_bookstore_schemas(bookstore: ParsedSpec) -> None:
    by_name = {s.name: s for s in bookstore.schemas}
    assert len(by_name) == 16
    assert by_name["Customer"].type == "object"
    assert by_name["Customer"].description == "A person who buys books."
    assert by_name["OrderStatus"].type == "string"
    # Composed schemas have no type of their own.
    assert by_name["OrderPage"].type is None


def test_bookstore_operation_details(bookstore: ParsedSpec) -> None:
    by_id = {o.operation_id: o for o in bookstore.operations}

    # Path-level parameters are merged, and references to parameters are replaced by their target.
    orders = by_id["listCustomerOrders"]
    assert [(p["name"], p["in"], p.get("required", False)) for p in orders.parameters] == [
        ("customerId", "path", True),
        ("page", "query", False),
        ("pageSize", "query", False),
    ]

    create = by_id["createOrder"]
    assert create.summary == "Create an order"
    assert create.pointer == "/paths/~1orders/post"
    assert create.request_body is not None
    assert create.request_body["required"] is True
    # References inside schemas stay in place, because schemas can be recursive.
    media_type = create.request_body["content"]["application/json"]
    assert media_type["schema"] == {"$ref": "#/components/schemas/OrderCreate"}
    assert media_type["example"]["customerId"] == "cus_001"

    # References to whole responses are replaced by their target.
    assert set(create.responses) == {"201", "400", "401", "409"}
    assert create.responses["401"]["description"] == "The access token is missing or invalid."

    # Security is inherited unless the operation sets its own, even to an empty list.
    assert create.security == [{"bearerAuth": []}]
    assert by_id["createToken"].security == []
    assert by_id["listBooks"].security == []


def test_raw_document_is_preserved(bookstore: ParsedSpec) -> None:
    assert bookstore.raw == yaml.safe_load(BOOKSTORE.read_text())


@pytest.mark.parametrize("version", ["3.0.0", "3.0.3", "3.1.0", "3.1.1", "3.2.0"])
def test_supported_versions(version: str) -> None:
    get = {"responses": _ok_responses()}
    assert _parse(_spec(version, paths={"/x": {"get": get}})).openapi_version == version


def test_rejects_swagger_2() -> None:
    document = {"swagger": "2.0", "info": {"title": "T", "version": "1"}, "paths": {}}
    assert "Swagger 2.0 isn't supported" in _issues(json.dumps(document).encode())[0]


@pytest.mark.parametrize("version", ["2.0.0", "3.3.0", "4.0.0", "3.1", "latest"])
def test_rejects_unsupported_versions(version: str) -> None:
    assert f"OpenAPI {version} isn't supported" in _issues(json.dumps(_spec(version)).encode())[0]


def test_explains_an_unquoted_version() -> None:
    assert "must be a string" in _issues(b"openapi: 3.0\ninfo: {title: T, version: '1'}", "yaml")[0]


@pytest.mark.parametrize(
    ("content", "spec_format", "expected"),
    [
        (b'{"openapi": ', "json", "Invalid JSON at line 1"),
        (b"a: b: c", "yaml", "Invalid YAML at line 1"),
        (b"\xff\xfe\x00", "json", "valid UTF-8"),
        (b"[1, 2]", "json", "doesn't contain an OpenAPI document"),
        (b"just text", "yaml", "doesn't contain an OpenAPI document"),
        (b'{"title": "Not OpenAPI"}', "json", "openapi field is missing"),
    ],
)
def test_explains_unreadable_files(
    content: bytes, spec_format: openapi_parser.SpecFormat, expected: str
) -> None:
    assert expected in _issues(content, spec_format)[0]


def test_reports_structural_problems_with_their_location() -> None:
    document = _spec(paths={"/x": {"get": {"responses": {"200": {}}}}})
    with pytest.raises(SpecParseError) as exc:
        _parse(document)
    assert "description" in exc.value.issues[0].message
    assert exc.value.issues[0].pointer is not None


def test_accepts_yaml_quirks() -> None:
    content = b"""
openapi: 3.0.3
info: {title: T, version: "1"}
paths:
  /x:
    get:
      responses:
        200:
          description: OK
          content:
            application/json:
              example: {released: 2026-01-15}
"""
    operation = parse_spec(content, "yaml").operations[0]
    response = operation.responses["200"]
    assert response["content"]["application/json"]["example"]["released"] == "2026-01-15"


def test_accepts_a_byte_order_mark() -> None:
    assert (
        _parse(_spec()).api_title
        == parse_spec(b"\xef\xbb\xbf" + json.dumps(_spec()).encode(), "json").api_title
    )


def test_keeps_operations_from_every_method_form() -> None:
    get = {"responses": _ok_responses()}
    document = _spec(
        "3.2.0",
        paths={"/x": {"query": get, "additionalOperations": {"COPY": get}}},
    )
    operations = _parse(document).operations
    assert [(o.method, o.pointer) for o in operations] == [
        ("QUERY", "/paths/~1x/query"),
        ("COPY", "/paths/~1x/additionalOperations/COPY"),
    ]


def test_resolves_a_referenced_path_item() -> None:
    get = {"operationId": "shared", "responses": _ok_responses()}
    document = _spec(
        paths={"/x": {"$ref": "#/components/pathItems/Shared"}},
        components={"pathItems": {"Shared": {"get": get}}},
    )
    assert _parse(document).operations[0].operation_id == "shared"


def test_operation_parameter_replaces_path_parameter() -> None:
    def parameter(description: str) -> dict[str, Any]:
        return {"name": "q", "in": "query", "description": description, "schema": {}}

    get = {"parameters": [parameter("operation")], "responses": _ok_responses()}
    document = _spec(paths={"/x": {"parameters": [parameter("path")], "get": get}})
    parameters = _parse(document).operations[0].parameters
    assert [p["description"] for p in parameters] == ["operation"]


def test_recursive_schemas_are_kept() -> None:
    node = {"type": "object", "properties": {"child": {"$ref": "#/components/schemas/Node"}}}
    document = _spec(components={"schemas": {"Node": node}})
    assert _parse(document).schemas[0].schema == node


def test_keeps_boolean_and_multi_type_schemas() -> None:
    document = _spec(components={"schemas": {"Any": True, "Name": {"type": ["string", "null"]}}})
    by_name = {s.name: s for s in _parse(document).schemas}
    assert by_name["Any"].type is None
    assert by_name["Any"].schema is True
    assert by_name["Name"].type == "string, null"


def test_rejects_a_missing_reference() -> None:
    document = _with_schema({"$ref": "#/components/schemas/Missing"})
    assert "points to nothing" in _issues(json.dumps(document).encode())[0]


def test_rejects_a_reference_cycle_in_a_response() -> None:
    document = _spec(
        paths={"/x": {"get": {"responses": {"200": {"$ref": "#/components/responses/A"}}}}},
        components={
            "responses": {
                "A": {"$ref": "#/components/responses/B"},
                "B": {"$ref": "#/components/responses/A"},
            }
        },
    )
    with pytest.raises(SpecParseError):
        _parse(document)


@pytest.fixture
def server() -> Iterator[tuple[str, list[str]]]:
    """A local server that records requests, to prove that the parser makes none."""
    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"type": "object"}')

        def log_message(self, *_: Any) -> None:
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", hits
    httpd.shutdown()
    httpd.server_close()
    thread.join()


@pytest.mark.parametrize(
    "ref",
    [
        "{url}/remote.json",
        "{url}/remote.json#/components/schemas/X",
        "other-file.yaml#/components/schemas/X",
        "file:///etc/hosts",
        "ftp://127.0.0.1/remote.json",
    ],
)
def test_rejects_external_references_without_fetching(
    ref: str, server: tuple[str, list[str]]
) -> None:
    url, hits = server
    document = _with_schema({"$ref": ref.format(url=url)})
    assert "External references aren't supported" in _issues(json.dumps(document).encode())[0]
    assert hits == []


@pytest.mark.parametrize(
    "ref", ["{url}/remote.json", "file:///etc/hosts", "ftp://127.0.0.1/remote.json"]
)
def test_validator_cannot_fetch_even_without_the_reference_check(
    ref: str, server: tuple[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second layer of defense, for references the first check can't recognize as external."""
    url, hits = server
    monkeypatch.setattr(openapi_parser, "_check_references", lambda _: None)
    document = _with_schema({"$ref": ref.format(url=url)})
    assert "couldn't be validated" in _issues(json.dumps(document).encode())[0]
    assert hits == []


def test_schema_id_cannot_redirect_a_reference(server: tuple[str, list[str]]) -> None:
    url, hits = server
    document = _with_schema({"$id": f"{url}/base/", "$ref": "#/info"})
    with contextlib.suppress(SpecParseError):
        _parse(document)
    assert hits == []


def test_rejects_a_yaml_alias_bomb() -> None:
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    for level in range(1, 12):
        previous = f"*a{level - 1}"
        lines.append(f"a{level}: &a{level} [{', '.join([previous] * 10)}]")
    content = "\n".join(lines).encode()
    assert len(content) < 2000
    assert "too large or too deeply nested" in _issues(content, "yaml")[0]


def test_rejects_a_self_referencing_yaml_alias() -> None:
    assert "too large or too deeply nested" in _issues(b"a: &a {b: *a}", "yaml")[0]


def test_rejects_deep_nesting() -> None:
    content = b"[" * 100_000 + b"]" * 100_000
    assert _issues(content, "json")


@pytest.mark.parametrize(
    "content",
    [
        b"!!python/object/apply:os.system [echo unsafe]",
        b"a: !!python/name:os.system",
    ],
)
def test_does_not_construct_python_objects_from_yaml(content: bytes) -> None:
    assert "Invalid YAML" in _issues(content, "yaml")[0]


@pytest.mark.parametrize(
    "content",
    [
        b'{"openapi": "3.1.0", "info": {"title": "\\u0000", "version": "1"}, "paths": {}}',
        b'{"openapi": "3.1.0", "info": {"title": "\\ud800", "version": "1"}, "paths": {}}',
        b'{"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "x": NaN, "paths": {}}',
        b'{"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "x": 1e999, "paths": {}}',
    ],
)
def test_rejects_values_postgres_cannot_store(content: bytes) -> None:
    assert _issues(content)


def test_inlines_referenced_examples() -> None:
    media = {
        "examples": {
            "named": {"$ref": "#/components/examples/Ada"},
            "direct": {"value": {"name": "Grace"}},
        }
    }
    parsed = _parse(
        _spec(
            paths={
                "/a": {
                    "post": {
                        "parameters": [
                            {
                                "name": "q",
                                "in": "query",
                                "schema": {"type": "string"},
                                "examples": {"named": {"$ref": "#/components/examples/Ada"}},
                            }
                        ],
                        "requestBody": {"$ref": "#/components/requestBodies/Body"},
                        "responses": {"200": {"description": "OK", "content": {"a/json": media}}},
                    }
                }
            },
            components={
                "examples": {"Ada": {"summary": "Ada", "value": {"name": "Ada"}}},
                "requestBodies": {"Body": {"content": {"a/json": media}}},
            },
        )
    )
    operation = parsed.operations[0]
    ada = {"summary": "Ada", "value": {"name": "Ada"}}
    assert operation.parameters[0]["examples"]["named"] == ada
    assert operation.request_body is not None
    assert operation.request_body["content"]["a/json"]["examples"]["named"] == ada
    examples = operation.responses["200"]["content"]["a/json"]["examples"]
    assert examples == {"named": ada, "direct": {"value": {"name": "Grace"}}}
    # The stored document stays exactly as uploaded.
    assert parsed.raw["components"]["requestBodies"]["Body"]["content"]["a/json"] == media
