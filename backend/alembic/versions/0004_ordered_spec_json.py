"""Store the operation and schema data shown to users as json, which keeps key order.

JSONB reorders object keys, so fields and examples wouldn't appear in the order the specification
gives them. Nothing queries inside these columns, so JSONB's indexing isn't needed. Specifications
imported before this migration keep the order they already have until they are uploaded again.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("operations", "parameters_json"),
    ("operations", "request_body_json"),
    ("operations", "responses_json"),
    ("schemas", "schema_json"),
)


def _set_type(column_type: str) -> None:
    for table, column in _COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {column_type} "
            f"USING {column}::{column_type}"
        )


def upgrade() -> None:
    _set_type("json")


def downgrade() -> None:
    _set_type("jsonb")
