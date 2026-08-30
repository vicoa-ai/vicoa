"""widen_machines_platform_column

Revision ID: c3d4e5f6a7b8
Revises: b5845c1df2cb
Branch Labels: None
Depends On: None

Create Date: 2026-05-03

Windows platform strings from platform.platform() can exceed 64 characters
(e.g. "Windows-10-10.0.19041-SP0-Intel64 Family 6 Model 142...").
Widening to 255 matches hostname/display_name and prevents 500 errors on
machine registration from Windows daemons.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2e3f4a5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "machines",
        "platform",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "machines",
        "platform",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
