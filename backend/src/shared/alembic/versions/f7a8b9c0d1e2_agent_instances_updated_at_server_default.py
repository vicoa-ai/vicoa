"""agent_instances_updated_at_server_default

Revision ID: f7a8b9c0d1e2
Revises: d4e5f6a7b8c9
Branch Labels: None
Depends On: None

Create Date: 2026-05-22

Migration d4e5f6a7b8c9 added agent_instances.updated_at as NOT NULL with only
a Python-side SQLAlchemy default. During a deploy gap the migration lands
before the new code, so the still-running old revision builds INSERTs whose
model has no updated_at column -> Postgres rejects the row on the NOT NULL
constraint.

Adding a DB-side server_default makes inserts succeed regardless of which code
revision issues them. now() also covers any external/manual writers.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_instances ALTER COLUMN updated_at SET DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_instances ALTER COLUMN updated_at DROP DEFAULT")
