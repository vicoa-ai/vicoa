"""revoke the API keys minted for webhook agents

Webhook agents are removed. Triggering one minted a non-expiring API key named
"<agent type name> Key" and sent it to the configured URL; with nothing left to
use those keys, they are revoked. The `agent_types.webhook_type` /
`webhook_config` columns are only unmapped for now: release_command migrates
before the old machines of both Fly apps are replaced, and they still select
every mapped column. A later migration drops them. Data only.

Revision ID: 83319b5520d0
Revises: a8e4c2f6d0b3
Create Date: 2026-10-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83319b5520d0"
down_revision: Union[str, None] = "a8e4c2f6d0b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE api_keys AS k
        SET is_active = FALSE
        FROM agent_types AS t
        WHERE t.user_id = k.user_id
          AND t.webhook_type IS NOT NULL
          AND k.name = t.name || ' Key'
          AND k.expires_at IS NULL
          AND k.is_active
        """
    )


def downgrade() -> None:
    # Which of these keys were active before is not recorded, and handing a
    # revoked credential back would be the wrong default anyway.
    pass
