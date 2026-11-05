"""Create the projects table, protected by row-level security.

The app's login role can bypass RLS (it always does on local Postgres, where it is a superuser),
so requests run as api_compass_app, a restricted role that can't. Policies compare owner_id to
the transaction-local app.current_user_id setting; when it is unset, no rows match.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_compass_app') THEN
                CREATE ROLE api_compass_app NOLOGIN NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT api_compass_app TO CURRENT_USER")
    op.execute("GRANT USAGE ON SCHEMA public TO api_compass_app")

    op.execute(
        """
        CREATE TABLE projects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL,
            name varchar(120) NOT NULL,
            description text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_projects_owner_id ON projects (owner_id)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON projects TO api_compass_app")

    op.execute("ALTER TABLE projects ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE projects FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY projects_owner ON projects
            FOR ALL
            TO api_compass_app
            USING (owner_id = nullif(current_setting('app.current_user_id', true), '')::uuid)
            WITH CHECK (owner_id = nullif(current_setting('app.current_user_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE projects")
    op.execute("REVOKE USAGE ON SCHEMA public FROM api_compass_app")
    op.execute("DROP ROLE api_compass_app")
