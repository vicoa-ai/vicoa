"""agent_instances.rate_limited_until: timestamp -> timestamptz

The column held naive timestamps while the task dispatch sweep compares it in
Python with an aware "now", which raises TypeError. The sweep claims every due
dispatch in one pass, so one queued dispatch on a rate-limited task session
failed the whole pass. With a time zone the value reads back aware and the
comparison holds; the usage projection that sets it already produces aware UTC.

A plain cast, in the session's time zone, on purpose. The writer stores an
aware value, which Postgres converts to the session's time zone for a naive
column: the stored values are UTC on a server whose zone is UTC, and local
time on one whose zone isn't. Reading them back in that same zone recovers the
instant on both. Forcing UTC here (`SET timezone` or `USING ... AT TIME ZONE
'UTC'`) would shift the rows on a non-UTC server by its offset.

On a UTC server, Postgres 12+ changes timestamp <-> timestamptz without
rewriting the table; only the partial index `ix_agent_instances_rate_limited_until`
is rebuilt. On any other zone the table is rewritten once.

Revision ID: 6a0b261d035c
Revises: 80b6033051f6
Create Date: 2026-11-23 03:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a0b261d035c"
down_revision: Union[str, None] = "80b6033051f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "agent_instances",
        "rate_limited_until",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "agent_instances",
        "rate_limited_until",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
    )
