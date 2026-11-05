"""Create the spec_versions, operations and schemas tables, protected by row-level security.

Each policy checks that the parent row is visible. The check runs as the same restricted role, so
the projects policy applies to it, and ownership flows down from projects to every child table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _protect(table: str, parent_check: str) -> None:
    # No UPDATE grant: an imported version never changes. Deletes cascade from projects.
    op.execute(f"GRANT SELECT, INSERT, DELETE ON {table} TO api_compass_app")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_owner ON {table}
            FOR ALL
            TO api_compass_app
            USING (EXISTS ({parent_check}))
            WITH CHECK (EXISTS ({parent_check}))
        """
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE spec_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
            version_number integer NOT NULL,
            source_filename text NOT NULL,
            format varchar(10) NOT NULL CHECK (format IN ('json', 'yaml')),
            openapi_version varchar(20),
            api_title text,
            metadata_json jsonb,
            raw_spec_json jsonb,
            status varchar(20) NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
            validation_errors jsonb,
            operation_count integer NOT NULL DEFAULT 0,
            schema_count integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (project_id, version_number)
        )
        """
    )
    _protect("spec_versions", "SELECT 1 FROM projects WHERE projects.id = spec_versions.project_id")

    op.execute(
        """
        CREATE TABLE operations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            spec_version_id uuid NOT NULL REFERENCES spec_versions (id) ON DELETE CASCADE,
            position integer NOT NULL,
            operation_id text,
            method varchar(40) NOT NULL,
            path text NOT NULL,
            summary text,
            description text,
            tags text[] NOT NULL DEFAULT '{}',
            parameters_json jsonb NOT NULL,
            request_body_json jsonb,
            responses_json jsonb NOT NULL,
            security_json jsonb NOT NULL,
            raw_pointer text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (spec_version_id, position)
        )
        """
    )
    _protect(
        "operations",
        "SELECT 1 FROM spec_versions WHERE spec_versions.id = operations.spec_version_id",
    )

    op.execute(
        """
        CREATE TABLE schemas (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            spec_version_id uuid NOT NULL REFERENCES spec_versions (id) ON DELETE CASCADE,
            schema_name text NOT NULL,
            schema_type text,
            schema_json jsonb NOT NULL,
            description text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (spec_version_id, schema_name)
        )
        """
    )
    _protect(
        "schemas", "SELECT 1 FROM spec_versions WHERE spec_versions.id = schemas.spec_version_id"
    )


def downgrade() -> None:
    op.execute("DROP TABLE schemas")
    op.execute("DROP TABLE operations")
    op.execute("DROP TABLE spec_versions")
