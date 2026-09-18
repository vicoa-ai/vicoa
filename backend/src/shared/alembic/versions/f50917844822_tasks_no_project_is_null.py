"""Tasks: "No project" is NULL — retire the per-user Inbox row

plans/todos/project-first-picker-and-sidebar.md §4a. A task with no project
was kept NOT NULL by pointing it at a hidden, per-user ``is_inbox`` project.
Sessions already use ``project_id IS NULL`` for the same thing; this makes
tasks (and their denormalized comment/activity rows) do the same, so one
convention covers both and no surface has to special-case a phantom project.

Schema:
  * ``tasks.project_id``, ``task_comments.project_id``,
    ``task_activity.project_id`` become nullable, and their FK goes from
    ``CASCADE`` to ``SET NULL`` — deleting a project files its tasks rather
    than destroying them (the app clears ``number`` explicitly; the FK is the
    belt-and-braces).

Data:
  * Every Inbox task (with its comments/activity) is moved to NULL and loses
    its ``number`` — an identifier is project-scoped, an unfiled task has none.
  * The Inbox rows are deleted. ``projects.is_inbox`` and its partial unique
    index stay one release (clients still read the flag; it is now always
    false) and are dropped by a follow-up migration.

Revision ID: f50917844822
Revises: a1c6d3e8f52b
Create Date: 2026-09-18

Run ``alembic upgrade head`` BEFORE the backend deploy: the new code never
creates an Inbox, and the old code tolerates NULL project ids nowhere, so the
old backend must not run against the migrated data either — deploy promptly.
"""

import sqlalchemy as sa
from alembic import op

revision = "f50917844822"
down_revision = "a1c6d3e8f52b"
branch_labels = None
depends_on = None

# (table, FK column) → the FK is re-pointed at projects.id with SET NULL.
_PROJECT_FKS = (
    ("tasks", "project_id"),
    ("task_comments", "project_id"),
    ("task_activity", "project_id"),
)


def _fk_name(table: str, column: str) -> str | None:
    """The name of the FK constraint on ``table.column``, whatever Postgres
    auto-named it (the original migrations created them unnamed)."""
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON kcu.constraint_name = tc.constraint_name
             AND kcu.table_schema = tc.table_schema
            WHERE tc.table_name = :table
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = :column
            LIMIT 1
            """
        ),
        {"table": table, "column": column},
    ).first()
    return row[0] if row else None


def _repoint_fk(table: str, column: str, ondelete: str) -> None:
    name = _fk_name(table, column)
    if name is not None:
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        f"{table}_{column}_fkey",
        table,
        "projects",
        [column],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    for table, column in _PROJECT_FKS:
        op.alter_column(table, column, existing_type=sa.Uuid(), nullable=True)
        _repoint_fk(table, column, "SET NULL")

    # Unfile every Inbox task, then retire the Inbox rows. Comments/activity
    # first (they only ever point where their task points), then the tasks
    # (number cleared with the project), then the projects. `user_id` on an
    # Inbox task is already its owner's, so it needs no change.
    op.execute(
        sa.text(
            """
            UPDATE task_comments SET project_id = NULL
            WHERE project_id IN (SELECT id FROM projects WHERE is_inbox)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE task_activity SET project_id = NULL
            WHERE project_id IN (SELECT id FROM projects WHERE is_inbox)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE tasks SET project_id = NULL, number = NULL
            WHERE project_id IN (SELECT id FROM projects WHERE is_inbox)
            """
        )
    )
    op.execute(sa.text("DELETE FROM projects WHERE is_inbox"))


def downgrade() -> None:
    # Re-home every unfiled task in a fresh per-user Inbox so the columns can
    # go back to NOT NULL. Numbers are re-allocated from 1 per Inbox (they were
    # cleared on the way up; the identifiers were never stable across a move).
    op.execute(
        sa.text(
            """
            INSERT INTO projects (id, user_id, name, is_inbox, is_archived,
                                  task_counter, created_at, updated_at)
            SELECT gen_random_uuid(), u.user_id, 'Inbox', true, false, 0,
                   now(), now()
            FROM (
                SELECT DISTINCT user_id FROM tasks WHERE project_id IS NULL
            ) AS u
            WHERE NOT EXISTS (
                SELECT 1 FROM projects p
                WHERE p.user_id = u.user_id AND p.is_inbox
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE tasks t
            SET project_id = p.id
            FROM projects p
            WHERE t.project_id IS NULL AND p.user_id = t.user_id AND p.is_inbox
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE tasks t
            SET number = numbered.rn
            FROM (
                SELECT t2.id,
                       row_number() OVER (
                           PARTITION BY t2.project_id ORDER BY t2.created_at, t2.id
                       ) AS rn
                FROM tasks t2
                JOIN projects p ON p.id = t2.project_id AND p.is_inbox
                WHERE t2.number IS NULL
            ) AS numbered
            WHERE t.id = numbered.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE projects p
            SET task_counter = GREATEST(p.task_counter, m.max_number)
            FROM (
                SELECT project_id, MAX(number) AS max_number
                FROM tasks WHERE number IS NOT NULL GROUP BY project_id
            ) AS m
            WHERE m.project_id = p.id AND p.is_inbox
            """
        )
    )
    for child in ("task_comments", "task_activity"):
        op.execute(
            sa.text(
                f"""
                UPDATE {child} c
                SET project_id = t.project_id
                FROM tasks t
                WHERE c.task_id = t.id AND c.project_id IS NULL
                """
            )
        )

    for table, column in _PROJECT_FKS:
        _repoint_fk(table, column, "CASCADE")
        op.alter_column(table, column, existing_type=sa.Uuid(), nullable=False)
