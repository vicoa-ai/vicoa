"""Task depth: project keys, task numbers, comments, reactions, activity, subscribers

Collaboration plan §3.5 (P2). Tasks become addressable as KEY-42.

Revision ID: a3f1c9e27b45
Revises: e1c8f2a640b7
Create Date: 2026-09-09

Deploy order matters and is not optional: `tasks.number`, `projects.key` and
`projects.task_counter` land on the ORM models, so every `db.query(Task)` and
`db.query(Project)` enumerates them in its SELECT. Code deployed ahead of this
migration means `UndefinedColumn` on every query touching those tables — a
whole-backend outage, not "the new feature is inert". Run `alembic upgrade head`
BEFORE the backend deploy (collaboration §10.10).
"""

import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3f1c9e27b45"
down_revision = "e1c8f2a640b7"
branch_labels = None
depends_on = None


# Mirror of shared.database.task_identity.derive_key_base. Duplicated on purpose:
# a migration must keep producing the keys it produced on the day it ran, even
# after the live helper's rules change.
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")
_LEADING_DIGITS = re.compile(r"^[0-9]+")
_FALLBACK = "PRJ"


def _derive_key_base(name: str) -> str:
    stripped = _LEADING_DIGITS.sub("", _NON_ALNUM.sub("", name or ""))
    base = stripped[:3].upper()
    return base if len(base) >= 2 else _FALLBACK


def _backfill_keys(conn) -> None:
    """Give every project that holds a task a key, unique within its owner.

    Only projects with tasks: a key is a task-identifier prefix, and handing one
    to an empty project would take a name out of the namespace for nothing. The
    runtime allocates lazily on a project's first task for the same reason.
    """
    rows = conn.execute(
        sa.text(
            """
            SELECT p.id, p.user_id, p.name
            FROM projects p
            WHERE EXISTS (SELECT 1 FROM tasks t WHERE t.project_id = p.id)
            ORDER BY p.user_id, p.created_at, p.id
            """
        )
    ).fetchall()

    taken: dict[str, set[str]] = {}
    for project_id, user_id, name in rows:
        owned = taken.setdefault(str(user_id), set())
        base = _derive_key_base(name)
        key = base
        suffix = 2
        while key in owned:
            key = f"{base}{suffix}"[:8]
            suffix += 1
        owned.add(key)
        conn.execute(
            sa.text("UPDATE projects SET key = :key WHERE id = :id"),
            {"key": key, "id": project_id},
        )


def upgrade() -> None:
    op.add_column("projects", sa.Column("key", sa.String(length=8), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "task_counter", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column("tasks", sa.Column("number", sa.Integer(), nullable=True))

    conn = op.get_bind()

    # Numbers first, ordered the way the tasks were written, so an existing
    # backlog reads in the order it was created rather than at random.
    conn.execute(
        sa.text(
            """
            UPDATE tasks t
            SET number = numbered.rn
            FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY project_id ORDER BY created_at, id
                       ) AS rn
                FROM tasks
            ) AS numbered
            WHERE t.id = numbered.id
            """
        )
    )
    # The counter is the high-water mark, never a live count: deleting a task
    # must not hand its number to the next one.
    conn.execute(
        sa.text(
            """
            UPDATE projects p
            SET task_counter = COALESCE(m.max_number, 0)
            FROM (
                SELECT project_id, MAX(number) AS max_number
                FROM tasks GROUP BY project_id
            ) AS m
            WHERE p.id = m.project_id
            """
        )
    )
    _backfill_keys(conn)

    op.create_index(
        "uq_projects_user_key",
        "projects",
        ["user_id", sa.text("upper(key)")],
        unique=True,
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.create_index(
        "uq_tasks_project_number",
        "tasks",
        ["project_id", "number"],
        unique=True,
        postgresql_where=sa.text("number IS NOT NULL"),
    )

    op.create_table(
        "task_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        # One-level threads: a reply points at a root, and a reply to a reply is
        # re-pointed at that root by the write path, so this column never forms
        # a chain deeper than one hop.
        sa.Column("parent_comment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_type", sa.String(length=8), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "author_type IN ('user','agent')", name="ck_task_comments_author_type"
        ),
        sa.CheckConstraint(
            "kind IN ('comment','system')", name="ck_task_comments_kind"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_comment_id"], ["task_comments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_comments_task", "task_comments", ["task_id", "created_at"])
    op.create_index("ix_task_comments_project", "task_comments", ["project_id"])
    op.create_index(
        "ix_task_comments_parent",
        "task_comments",
        ["parent_comment_id"],
        postgresql_where=sa.text("parent_comment_id IS NOT NULL"),
    )

    op.create_table(
        "task_reactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=8), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('task','comment')", name="ck_task_reactions_target_type"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_type",
            "target_id",
            "user_id",
            "emoji",
            name="uq_task_reactions_target_user_emoji",
        ),
    )
    op.create_index(
        "ix_task_reactions_target", "task_reactions", ["target_type", "target_id"]
    )

    op.create_table(
        "task_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(length=8), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IS NULL OR actor_type IN ('user','agent','system')",
            name="ck_task_activity_actor_type",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_activity_task", "task_activity", ["task_id", "created_at"])
    op.create_index("ix_task_activity_project", "task_activity", ["project_id"])

    op.create_table(
        "task_subscribers",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('creator','assignee','commenter','mentioned','manual')",
            name="ck_task_subscribers_reason",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "user_id"),
    )
    op.create_index("ix_task_subscribers_user", "task_subscribers", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_task_subscribers_user", table_name="task_subscribers")
    op.drop_table("task_subscribers")
    op.drop_index("ix_task_activity_project", table_name="task_activity")
    op.drop_index("ix_task_activity_task", table_name="task_activity")
    op.drop_table("task_activity")
    op.drop_index("ix_task_reactions_target", table_name="task_reactions")
    op.drop_table("task_reactions")
    op.drop_index("ix_task_comments_parent", table_name="task_comments")
    op.drop_index("ix_task_comments_project", table_name="task_comments")
    op.drop_index("ix_task_comments_task", table_name="task_comments")
    op.drop_table("task_comments")
    op.drop_index("uq_tasks_project_number", table_name="tasks")
    op.drop_index("uq_projects_user_key", table_name="projects")
    op.drop_column("tasks", "number")
    op.drop_column("projects", "task_counter")
    op.drop_column("projects", "key")
