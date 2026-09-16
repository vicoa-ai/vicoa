"""Index agent_instances.agent_profile_id

`afb81952c1a3` added the column with a foreign key, and Postgres does not index a
FK column for you — so an agent's run history (`GET /api/v1/agents/{id}/sessions`)
and its session count both sequential-scanned `agent_instances`.

Partial (`WHERE agent_profile_id IS NOT NULL`) because the overwhelming majority
of sessions are ad-hoc and carry NULL here, the same shape as the existing
`ix_agent_instances_rate_limited_until`.

Revision ID: e1c8f2a640b7
Revises: d5b03ac71e64
Create Date: 2026-09-09 12:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c8f2a640b7"
down_revision: Union[str, None] = "d5b03ac71e64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_agent_instances_agent_profile",
        "agent_instances",
        ["agent_profile_id"],
        unique=False,
        postgresql_where=sa.text("agent_profile_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_agent_instances_agent_profile", table_name="agent_instances")
