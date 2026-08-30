"""Retire the pg_trgm workspace-search index

Workspace search originally added a pg_trgm GIN index over
lower(messages.content) for full-history message search. Building it
CONCURRENTLY in Fly's release_command proved unshippable: the flycast proxy
severs the connection on the ~10-min zero-traffic build, and the build
OOM-crashed the small shared-CPU Postgres VM. Message search moved to a
recency-bounded scan that needs no index (see backend.db.search_queries), so
this migration only tears the index down.

It drops any copy of idx_messages_content_trgm — a valid one on a database that
built it out-of-band, or the INVALID leftover an aborted CONCURRENTLY build
leaves behind. DROP is fast and flycast-safe, unlike the build. The pg_trgm
extension itself is left installed (harmless, and nothing else has to change if
a future feature wants it back).

Revision ID: c8d1f4a7b2e6
Revises: e2c7b9d4a1f3
Create Date: 2026-08-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d1f4a7b2e6"
down_revision: Union[str, None] = "e2c7b9d4a1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "idx_messages_content_trgm"


def upgrade() -> None:
    # CONCURRENTLY so the drop takes no ACCESS EXCLUSIVE lock on the hot
    # messages table; it must run outside the migration's transaction.
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")


def downgrade() -> None:
    # No-op: the trigram index was retired; there is nothing to recreate.
    pass
