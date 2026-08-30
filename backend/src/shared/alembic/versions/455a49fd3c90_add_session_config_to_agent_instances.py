"""Add session_config to agent_instances

Revision ID: 455a49fd3c90
Revises: 943422f9c33b
Create Date: 2026-06-02

Persists each agent instance's spawn-time configuration (agent, model,
thinking/reasoning effort, permission mode, opencode mode) so the chat
header can render it without scanning the message history. See
plans/session-config-storage.md §4.

Single ADD COLUMN — no backfill, no default, no index. Legacy rows stay
null and degrade to the existing message-history scan on the mobile client.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "455a49fd3c90"
down_revision: Union[str, None] = "943422f9c33b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_instances",
        sa.Column(
            "session_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_instances", "session_config")
