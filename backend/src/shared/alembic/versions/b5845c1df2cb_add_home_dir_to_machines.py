"""add_home_dir_to_machines

Revision ID: b5845c1df2cb
Revises: a3f9b2c1d4e5
Create Date: 2026-04-28 01:13:51.982366

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b5845c1df2cb"
down_revision: Union[str, None] = "a3f9b2c1d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "machines", sa.Column("home_dir", sa.String(length=1024), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("machines", "home_dir")
