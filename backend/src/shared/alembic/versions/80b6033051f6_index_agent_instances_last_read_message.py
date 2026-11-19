"""Index agent_instances.last_read_message_id

`40d4252deb5b` gave the column a foreign key to `messages.id` with
`ON DELETE SET NULL`, and Postgres does not index a FK column for you. The SET
NULL action runs `UPDATE agent_instances SET last_read_message_id = NULL WHERE
last_read_message_id = $1` once for every deleted message, whether or not any
row points at it, so deleting a session's messages (and an account's) scanned
`agent_instances` once per message and could run into the statement timeout.

Partial (`WHERE last_read_message_id IS NOT NULL`): the action only ever looks
up one non-NULL id, and a strict `=` implies the predicate, so the planner can
use the index for it, generic plans included. Same shape as
`ix_agent_instances_agent_profile` (`e1c8f2a640b7`).

Revision ID: 80b6033051f6
Revises: c4f7a2d9e8b1
Create Date: 2026-11-19 03:27:50.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "80b6033051f6"
down_revision: Union[str, None] = "c4f7a2d9e8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_agent_instances_last_read_message",
        "agent_instances",
        ["last_read_message_id"],
        unique=False,
        postgresql_where=sa.text("last_read_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_agent_instances_last_read_message", table_name="agent_instances")
