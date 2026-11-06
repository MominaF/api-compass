from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Store Python None as SQL NULL rather than the JSON value null.
_Json = JSONB(none_as_null=True)
# For data shown to the user: unlike JSONB, JSON keeps keys in the order the specification has them.
_OrderedJson = JSON(none_as_null=True)
_Timestamp = TIMESTAMP(timezone=True)


class SpecVersion(Base):
    __tablename__ = "spec_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version_number: Mapped[int]
    source_filename: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(10))
    openapi_version: Mapped[str | None] = mapped_column(String(20))
    api_title: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(_Json)
    # Deferred because it can be megabytes, and most reads don't need it.
    raw_spec_json: Mapped[dict[str, Any] | None] = mapped_column(_Json, deferred=True)
    status: Mapped[str] = mapped_column(String(20))
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(_Json)
    operation_count: Mapped[int] = mapped_column(server_default=text("0"))
    schema_count: Mapped[int] = mapped_column(server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(_Timestamp, server_default=func.now())


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    spec_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("spec_versions.id", ondelete="CASCADE")
    )
    # The operation's place in the document, since the stored raw_spec_json doesn't keep key order.
    position: Mapped[int]
    operation_id: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(40))
    path: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text))
    parameters_json: Mapped[list[Any]] = mapped_column(_OrderedJson)
    request_body_json: Mapped[dict[str, Any] | None] = mapped_column(_OrderedJson)
    responses_json: Mapped[dict[str, Any]] = mapped_column(_OrderedJson)
    security_json: Mapped[list[Any]] = mapped_column(_Json)
    raw_pointer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_Timestamp, server_default=func.now())


class ApiSchema(Base):
    __tablename__ = "schemas"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    spec_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("spec_versions.id", ondelete="CASCADE")
    )
    schema_name: Mapped[str] = mapped_column(Text)
    schema_type: Mapped[str | None] = mapped_column(Text)
    # A 3.1 schema can be the boolean true or false, so this isn't always an object.
    schema_json: Mapped[Any] = mapped_column(_OrderedJson)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(_Timestamp, server_default=func.now())
