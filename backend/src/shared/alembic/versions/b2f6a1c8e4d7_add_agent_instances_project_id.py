"""add agent_instances.project_id (session ↔ project link)

A nullable FK from a session to the formal projects entity, auto-matched on
register from (machine_id, working-dir path) — and, for a linked worktree, the
source repo root / git remote — and backfilled here for existing rows. SET NULL
so deleting a project degrades its runs rather than deleting them; index
(project_id, started_at) serves the "list a project's sessions, newest first"
query grouping/sharing needs. No match ⇒ NULL (NOT Inbox — Inbox is a task
concept).

Revision ID: b2f6a1c8e4d7
Revises: a7c3e5b1d9f4
Create Date: 2026-08-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2f6a1c8e4d7"
down_revision: Union[str, None] = "a7c3e5b1d9f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_instances",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_instances_project_id",
        "agent_instances",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_instances_project_started",
        "agent_instances",
        ["project_id", "started_at"],
    )

    # Best-effort backfill: stamp existing sessions whose working directory sits
    # at/under a project_directories.local_path on the same machine. Longest
    # matching local_path wins. Path-boundary match (starts_with, not LIKE) so
    # /a/b never matches /a/bc and path chars like `_` aren't wildcards. Mirrors
    # project_matching.resolve_project_id_for_session (tier 2, cwd only — the
    # repo_root signal is reported by the wrapper going forward and is absent on
    # historical rows, so worktree sessions backfill on link, not here).
    op.execute(
        """
        WITH matched AS (
            SELECT ai.id AS instance_id,
                   pd.project_id AS project_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY ai.id
                       ORDER BY length(rtrim(pd.local_path, '/')) DESC
                   ) AS rn
            FROM agent_instances ai
            JOIN project_directories pd
              ON pd.user_id = ai.user_id
             AND pd.machine_id = ai.machine_id
             AND (
                   ai.project = rtrim(pd.local_path, '/')
                OR ai.project = rtrim(pd.local_path, '/') || '/'
                OR starts_with(ai.project, rtrim(pd.local_path, '/') || '/')
             )
            WHERE ai.project_id IS NULL
              AND ai.project IS NOT NULL
              AND ai.machine_id IS NOT NULL
        )
        UPDATE agent_instances ai
        SET project_id = matched.project_id
        FROM matched
        WHERE ai.id = matched.instance_id
          AND matched.rn = 1
        """
    )


def downgrade() -> None:
    op.drop_index("ix_agent_instances_project_started", table_name="agent_instances")
    op.drop_constraint(
        "fk_agent_instances_project_id", "agent_instances", type_="foreignkey"
    )
    op.drop_column("agent_instances", "project_id")
