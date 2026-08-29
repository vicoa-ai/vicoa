"""Add message_attachments table

Revision ID: a3f2c9d41e88
Revises: 41f641820d6a
Create Date: 2026-06-10 12:00:00.000000

Image attachments for chat messages. Rows are created at upload time with
message_id NULL and bound to a message at send time; bytes live in S3 at
s3_key. message_id cascades with the message; user/instance cascade with
their parents.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a3f2c9d41e88"
down_revision: Union[str, None] = "41f641820d6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("agent_instance_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_instance_id"], ["agent_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_message_attachments_message",
        "message_attachments",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        "idx_message_attachments_user_created",
        "message_attachments",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_message_attachments_user_created", table_name="message_attachments"
    )
    op.drop_index("idx_message_attachments_message", table_name="message_attachments")
    op.drop_table("message_attachments")
