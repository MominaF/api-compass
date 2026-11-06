"""Parses an uploaded OpenAPI document into normalized records. Does no I/O.

Uploaded files are untrusted, so this module must never fetch a reference (see `_NoRetrieval`)
and must bound the work a small file can cause (see `_normalize`).
"""

import itertools
import json
import math
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from urllib.parse import unquote

import structlog
import yaml
from jsonschema_path import SchemaPath
from openapi_spec_validator import (
    OpenAPIV30SpecValidator,
    OpenAPIV31SpecValidator,
    OpenAPIV32SpecValidator,
)

log = structlog.get_logger()

SpecFormat = Literal["json", "yaml"]

MAX_ISSUES = 20
MAX_MESSAGE_LENGTH = 500
# Limits on the parsed document. A few kilobytes of YAML aliases can expand to billions of nodes.
MAX_NODES = 1_000_000
MAX_DEPTH = 128

_VALIDATORS = {
    "3.0": OpenAPIV30SpecValidator,
    "3.1": OpenAPIV31SpecValidator,
    "3.2": OpenAPIV32SpecValidator,
}
_VERSION = re.compile(r"^(3\.[012])\.\d+$")
# "query" exists only in 3.2, whose other custom methods live under additionalOperations.
_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace", "query")


@dataclass(frozen=True)
class SpecIssue:
    message: str
    pointer: str | None = None


class SpecParseError(Exception):
    """The document can't be imported. Every issue is safe to show to the user."""

    def __init__(self, *issues: SpecIssue) -> None:
        super().__init__(issues[0].message)
        self.issues = issues


@dataclass(frozen=True)
class ParsedOperation:
    operation_id: str | None
    method: str
    path: str
    summary: str | None
    description: str | None
    tags: list[str]
    parameters: list[Any]
    request_body: dict[str, Any] | None
    responses: dict[str, Any]
    security: list[Any]
    pointer: str


@dataclass(frozen=True)
class ParsedSchema:
    name: str
    type: str | None
    schema: Any
    description: str | None


@dataclass(frozen=True)
class ParsedSpec:
    openapi_version: str
    api_title: str
    metadata: dict[str, Any]
    raw: dict[str, Any]
    operations: list[ParsedOperation]
    schemas: list[ParsedSchema]


def parse_spec(content: bytes, spec_format: SpecFormat) -> ParsedSpec:
    """Run the import pipeline. Raises SpecParseError if the document can't be imported."""
    document = _normalize_document(_load(content, spec_format))
    version = _detect_version(document)
    _check_references(document)
    _validate(document, version)
    try:
        return _extract(document)
    except SpecParseError:
        raise
    except Exception as exc:
        # The validator accepts some shapes the extraction doesn't expect. Report that as a failed
        # import, because a 500 would leave the user with no explanation.
        log.exception("spec_extraction_failed")
        raise SpecParseError(SpecIssue("This specification could not be processed.")) from exc


def _load(content: bytes, spec_format: SpecFormat) -> Any:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SpecParseError(SpecIssue("The file isn't valid UTF-8 text.")) from exc

    try:
        return json.loads(text) if spec_format == "json" else yaml.safe_load(text)
    except json.JSONDecodeError as exc:
        message = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}."
        raise SpecParseError(SpecIssue(message)) from exc
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise SpecParseError(SpecIssue(f"Invalid YAML{where}: {exc.problem}.")) from exc
    except (yaml.YAMLError, ValueError, RecursionError) as exc:
        raise SpecParseError(SpecIssue(f"The file isn't valid {spec_format.upper()}.")) from exc


def _normalize_document(value: Any) -> dict[str, Any]:
    budget = itertools.count()
    document = _normalize(value, depth=0, budget=budget)
    if not isinstance(document, dict):
        raise SpecParseError(SpecIssue("The file doesn't contain an OpenAPI document."))
    return document


def _normalize(value: Any, *, depth: int, budget: Iterator[int]) -> Any:
    """Copy parsed data into plain JSON values that Postgres JSONB accepts.

    The copy expands YAML aliases, so the limits stop alias bombs, and the depth limit also stops
    self-referencing aliases.
    """
    if next(budget) > MAX_NODES or depth > MAX_DEPTH:
        raise SpecParseError(SpecIssue("The specification is too large or too deeply nested."))
    if isinstance(value, dict):
        return {
            _normalize_key(key): _normalize(item, depth=depth + 1, budget=budget)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize(item, depth=depth + 1, budget=budget) for item in value]
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise SpecParseError(SpecIssue("The specification contains a non-finite number."))
    if value is None or isinstance(value, bool | int | float):
        return value
    # YAML parses unquoted dates, which often appear in examples.
    if isinstance(value, date):
        return value.isoformat()
    raise SpecParseError(SpecIssue(f"Unsupported YAML value of type {type(value).__name__}."))


def _normalize_key(key: Any) -> str:
    # YAML parses unquoted status codes such as `200:` as integers.
    if isinstance(key, int) and not isinstance(key, bool):
        return str(key)
    if isinstance(key, str):
        return _normalize_string(key)
    raise SpecParseError(SpecIssue(f"Unsupported object key: {str(key)[:100]}."))


def _normalize_string(value: str) -> str:
    # JSONB rejects NUL characters, and lone surrogates (valid in JSON escapes) can't be encoded.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SpecParseError(SpecIssue("The specification contains invalid text.")) from exc
    if "\x00" in value:
        raise SpecParseError(SpecIssue("The specification contains invalid text."))
    return value


def _detect_version(document: dict[str, Any]) -> str:
    if "swagger" in document:
        raise SpecParseError(
            SpecIssue(
                "Swagger 2.0 isn't supported. Convert the file to OpenAPI 3.x and upload it again.",
                "/swagger",
            )
        )
    version = document.get("openapi")
    if version is None:
        raise SpecParseError(
            SpecIssue("This isn't an OpenAPI document: the openapi field is missing.")
        )
    if not isinstance(version, str):
        raise SpecParseError(
            SpecIssue('The openapi field must be a string, such as "3.1.0".', "/openapi")
        )
    if not _VERSION.match(version):
        raise SpecParseError(
            SpecIssue(
                f"OpenAPI {version[:50]} isn't supported. Use OpenAPI 3.0, 3.1 or 3.2.", "/openapi"
            )
        )
    return version


def _check_references(document: dict[str, Any]) -> None:
    issues: list[SpecIssue] = []
    for pointer, ref in _iter_references(document, ""):
        if not ref.startswith("#"):
            issues.append(SpecIssue(f"External references aren't supported: {ref[:200]}", pointer))
        elif (ref == "#" or ref.startswith("#/")) and _lookup(document, ref) is _MISSING:
            issues.append(SpecIssue(f"This reference points to nothing: {ref[:200]}", pointer))
    if issues:
        raise SpecParseError(*issues[:MAX_ISSUES])


def _iter_references(node: Any, pointer: str) -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            yield f"{pointer}/$ref", ref
        for key, item in node.items():
            yield from _iter_references(item, f"{pointer}/{_escape_pointer(key)}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _iter_references(item, f"{pointer}/{index}")


class _NoRetrieval(dict[str, Any]):
    """Resolver handlers that claim every URI scheme and refuse to fetch any of them.

    By default the validator reads http:// and file:// references, and falls back to urlopen for
    schemes without a handler. Claiming every scheme also covers references that _check_references
    can't see, such as a relative one made absolute by a JSON Schema $id.
    """

    def __contains__(self, _: object) -> bool:
        return True

    def __getitem__(self, _: str) -> Any:
        return self._refuse

    @staticmethod
    def _refuse(uri: str) -> Any:
        raise ValueError(f"External references aren't supported: {uri}")


def _validate(document: dict[str, Any], version: str) -> None:
    validator_class = _VALIDATORS[version.rsplit(".", 1)[0]]
    path = SchemaPath.from_dict(document, handlers=_NoRetrieval())
    try:
        errors = list(itertools.islice(validator_class(path).iter_errors(), MAX_ISSUES))
    except Exception as exc:
        # Unresolvable references and malformed nodes surface as assorted library exceptions.
        log.info("spec_validator_raised", error=type(exc).__name__)
        raise SpecParseError(
            SpecIssue(f"The specification couldn't be validated: {_shorten(str(exc))}")
        ) from exc
    if errors:
        raise SpecParseError(*(_issue_from_error(error) for error in errors))


def _issue_from_error(error: Any) -> SpecIssue:
    parts = getattr(error, "absolute_path", None) or []
    pointer = "".join(f"/{_escape_pointer(str(part))}" for part in parts) or None
    return SpecIssue(_shorten(str(getattr(error, "message", error))), pointer)


def _shorten(message: str) -> str:
    if len(message) <= MAX_MESSAGE_LENGTH:
        return message
    return message[:MAX_MESSAGE_LENGTH] + "…"


def _extract(document: dict[str, Any]) -> ParsedSpec:
    info = document["info"]
    components = document.get("components") or {}
    return ParsedSpec(
        openapi_version=document["openapi"],
        api_title=info["title"],
        metadata={
            "version": info.get("version"),
            "description": info.get("description"),
            "contact": info.get("contact"),
            "servers": document.get("servers") or [],
            "tags": document.get("tags") or [],
            "security_schemes": {
                name: _dereference(document, scheme)
                for name, scheme in (components.get("securitySchemes") or {}).items()
            },
        },
        raw=document,
        operations=list(_extract_operations(document)),
        schemas=[
            _extract_schema(name, schema)
            for name, schema in (components.get("schemas") or {}).items()
        ],
    )


def _extract_operations(document: dict[str, Any]) -> Iterator[ParsedOperation]:
    default_security = document.get("security") or []
    for path, raw_item in (document.get("paths") or {}).items():
        item = _dereference(document, raw_item)
        base = f"/paths/{_escape_pointer(path)}"
        shared = item.get("parameters") or []
        for method in _HTTP_METHODS:
            if method in item:
                yield _extract_operation(
                    document,
                    path,
                    method,
                    item[method],
                    shared,
                    default_security,
                    f"{base}/{method}",
                )
        for method, operation in (item.get("additionalOperations") or {}).items():
            yield _extract_operation(
                document,
                path,
                method,
                operation,
                shared,
                default_security,
                f"{base}/additionalOperations/{_escape_pointer(method)}",
            )


def _extract_operation(
    document: dict[str, Any],
    path: str,
    method: str,
    operation: dict[str, Any],
    shared_parameters: list[Any],
    default_security: list[Any],
    pointer: str,
) -> ParsedOperation:
    # An operation's parameter replaces a path-level one with the same name and location.
    parameters: dict[tuple[str, str], Any] = {}
    for raw in [*shared_parameters, *(operation.get("parameters") or [])]:
        parameter = _dereference(document, raw)
        parameters[(parameter["name"], parameter["in"])] = parameter

    request_body = operation.get("requestBody")
    return ParsedOperation(
        operation_id=operation.get("operationId"),
        method=method.upper(),
        path=path,
        summary=operation.get("summary"),
        description=operation.get("description"),
        tags=operation.get("tags") or [],
        parameters=list(parameters.values()),
        request_body=None if request_body is None else _dereference(document, request_body),
        responses={
            code: _dereference(document, response)
            for code, response in (operation.get("responses") or {}).items()
        },
        # An empty list on the operation means "no auth", so only a missing field inherits.
        security=operation.get("security", default_security),
        pointer=pointer,
    )


def _extract_schema(name: str, schema: Any) -> ParsedSchema:
    # In 3.1 a schema can be a boolean, and its type can be a list such as ["string", "null"].
    fields = schema if isinstance(schema, dict) else {}
    schema_type = fields.get("type")
    if isinstance(schema_type, list):
        schema_type = ", ".join(str(part) for part in schema_type)
    description = fields.get("description")
    return ParsedSchema(
        name=name,
        type=schema_type if isinstance(schema_type, str) else None,
        schema=schema,
        description=description if isinstance(description, str) else None,
    )


_MISSING = object()


def _lookup(document: dict[str, Any], ref: str) -> Any:
    """Follow an internal reference such as #/components/schemas/Customer."""
    node: Any = document
    for raw_part in ref.removeprefix("#").split("/")[1:]:
        part = unquote(raw_part).replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdecimal() and int(part) < len(node):
            node = node[int(part)]
        else:
            return _MISSING
    return node


def _dereference(document: dict[str, Any], node: Any) -> Any:
    """Replace a Reference Object with its target, so operations are self-contained.

    Used for parameters, request bodies and responses. References inside schemas stay in place:
    they can be recursive, and their targets are stored as schema records.
    """
    seen: set[str] = set()
    while isinstance(node, dict) and isinstance(node.get("$ref"), str):
        ref = node["$ref"]
        if ref in seen:
            raise SpecParseError(SpecIssue(f"This reference points to itself: {ref[:200]}"))
        seen.add(ref)
        target = _lookup(document, ref)
        if target is _MISSING:
            raise SpecParseError(SpecIssue(f"This reference points to nothing: {ref[:200]}"))
        # In 3.1 a reference can override its target's summary and description.
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        node = {**target, **siblings} if isinstance(target, dict) else target
    return node


def _escape_pointer(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")
