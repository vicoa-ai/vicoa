"""add machine_agent_models.modes

Revision ID: c7d2e9a1b4f6
Revises: a3f1c9e27b45
Branch Labels: None
Depends On: None

Create Date: 2026-09-14

Nullable JSONB list of an agent's ACP session modes (`[{"id","label"}]`) next
to the cached model list, so the new-session picker can offer a catalog
agent's real modes before a session starts. NULL = not reported (rows written
before this column, or an agent with no mode switching); clients keep their
catalog placeholder for NULL rather than rendering an empty picker.
`models_hash` now covers both lists, so every existing row is rewritten once
on its next report — harmless.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d2e9a1b4f6"
down_revision: Union[str, None] = "a3f1c9e27b45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "machine_agent_models",
        sa.Column("modes", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("machine_agent_models", "modes")
