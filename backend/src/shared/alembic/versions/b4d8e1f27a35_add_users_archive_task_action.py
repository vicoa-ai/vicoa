"""add users.archive_task_action (what archiving a session does to its task)

Archiving a session marks the task it works on done, which is not always what
the user means. ``archive_task_action`` is the standing answer: 'ask' (the web
asks each time, the default), 'mark_done' (the task follows the session) or
'leave' (the task keeps its status). Additive only; every existing row gets
'ask', which behaves like today for any client that cannot ask.

Revision ID: b4d8e1f27a35
Revises: 9c3e5a7b1d24
Create Date: 2026-10-30 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b4d8e1f27a35"
down_revision: Union[str, None] = "9c3e5a7b1d24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "archive_task_action",
            sa.String(length=16),
            nullable=False,
            server_default="ask",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "archive_task_action")
