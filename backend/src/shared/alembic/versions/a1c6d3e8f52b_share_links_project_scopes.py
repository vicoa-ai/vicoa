"""Share links: one project link with scopes, not one link per content kind

Collaboration §3.4 (P4 follow-up). `project_sessions` and `project_board` were
two kinds of link, so sharing a project twice produced two URLs and the dialog
had to explain which was which. They become one kind — `project` — with a
`scopes` array saying which halves it carries ('tasks', 'sessions'), the same
vocabulary `project_grants.scopes` already uses.

Existing rows are rewritten in place, tokens untouched, so every live link
keeps working and gains the shape the new viewer reads:

    project_sessions  ->  kind='project', scopes=['sessions']
    project_board     ->  kind='project', scopes=['tasks']

`filters` moves under the scope it belongs to ({...} -> {"sessions": {...}}),
because one link can now carry both halves and "statuses" means a different
thing to each.

Revision ID: a1c6d3e8f52b
Revises: f7b2c4d9e1a3
Create Date: 2026-09-19

Rewrites data; run ``alembic upgrade head`` BEFORE the backend deploy (§10.10).
The old kinds stop resolving the moment the new code is live, so the two must
not be split across a long window.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1c6d3e8f52b"
down_revision = "f7b2c4d9e1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "share_links",
        sa.Column(
            "scopes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # The constraints name the old kinds; drop them, migrate, put them back.
    op.drop_constraint("ck_share_links_kind", "share_links", type_="check")
    op.drop_constraint("ck_share_links_project_target", "share_links", type_="check")
    op.execute(
        """
        UPDATE share_links
           SET scopes = CASE kind
                   WHEN 'project_sessions' THEN '["sessions"]'::jsonb
                   WHEN 'project_board' THEN '["tasks"]'::jsonb
                   ELSE '[]'::jsonb
               END,
               filters = CASE
                   -- `'null'::jsonb` is a value, not an absent one: a row that
                   -- narrows nothing must not gain a `{"sessions": null}`.
                   WHEN NULLIF(filters, 'null'::jsonb) IS NULL THEN NULL
                   WHEN kind = 'project_sessions'
                       THEN jsonb_build_object('sessions', filters)
                   WHEN kind = 'project_board'
                       THEN jsonb_build_object('tasks', filters)
                   ELSE filters
               END,
               kind = CASE WHEN kind = 'session' THEN 'session' ELSE 'project' END
        """
    )
    op.create_check_constraint(
        "ck_share_links_kind", "share_links", "kind IN ('session','project')"
    )
    op.create_check_constraint(
        "ck_share_links_project_target",
        "share_links",
        "(kind <> 'session') = (project_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_share_links_scopes",
        "share_links",
        "(kind = 'project') = (jsonb_array_length(scopes) > 0)",
    )
    op.create_check_constraint(
        "ck_share_links_comments_need_tasks",
        "share_links",
        "NOT allow_comments OR scopes @> '[\"tasks\"]'::jsonb",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_share_links_comments_need_tasks", "share_links", type_="check"
    )
    op.drop_constraint("ck_share_links_scopes", "share_links", type_="check")
    op.drop_constraint("ck_share_links_kind", "share_links", type_="check")
    op.drop_constraint("ck_share_links_project_target", "share_links", type_="check")
    # A link that carries both halves has no pre-split equivalent; it goes back
    # as the tasks link, which is the half that can carry comments.
    op.execute(
        """
        UPDATE share_links
           SET kind = CASE
                   WHEN kind = 'session' THEN 'session'
                   WHEN scopes @> '["tasks"]'::jsonb THEN 'project_board'
                   ELSE 'project_sessions'
               END,
               filters = CASE
                   WHEN NULLIF(filters, 'null'::jsonb) IS NULL THEN NULL
                   WHEN kind = 'session' THEN filters
                   WHEN scopes @> '["tasks"]'::jsonb THEN filters -> 'tasks'
                   ELSE filters -> 'sessions'
               END
        """
    )
    op.create_check_constraint(
        "ck_share_links_kind",
        "share_links",
        "kind IN ('session','project_sessions','project_board')",
    )
    op.create_check_constraint(
        "ck_share_links_project_target",
        "share_links",
        "(kind <> 'session') = (project_id IS NOT NULL)",
    )
    op.drop_column("share_links", "scopes")
