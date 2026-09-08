"""rename user_agents to agent_types

Naming cleanup (collaboration plan P0.5) so the word "agent" is free for the
user-facing ``agent_profiles`` resource that P1 introduces. ``user_agents``
never meant "a user's agent" — it means *agent type* ("claude code", "codex"),
auto-created on session registration.

Internals only. This is metadata-only DDL (instant, no table rewrite) and it is
invisible to clients:

* ``/api/v1/user-agents`` keeps its path — 9 mobile call sites depend on it and
  installed builds never force-upgrade.
* The REST fields were already ``agent_type_id`` / ``agent_type_name``.
* The WebSocket instance body keeps its legacy ``user_agent_id`` key (see
  ``shared/websocket/envelope.py``); only the column behind it is renamed.

``ALTER TABLE ... RENAME`` does **not** rewrite plpgsql function bodies, and
``notify_instance_list_change`` (the per-user instance-list NOTIFY trigger,
added in e1a42f472efc) reads ``FROM user_agents`` and ``NEW.user_agent_id``.
Left alone it would start raising on every INSERT/UPDATE of ``agent_instances``
— i.e. every session registration — so it is recreated here in the same
transaction. The body below is e1a42f472efc's verbatim, with only those two
identifiers updated.

Revision ID: a3f1d95c7b02
Revises: c9e4b7d13f28
Create Date: 2026-09-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f1d95c7b02"
down_revision: Union[str, None] = "c9e4b7d13f28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every schema object that carries the old name. Postgres renames none of these
# for you when the table is renamed. (name, new_name, kind)
_RENAMES: list[tuple[str, str, str]] = [
    # indexes
    ("ix_user_agents_user_id", "ix_agent_types_user_id", "index"),
    ("uq_user_agents_user_id_name", "uq_agent_types_user_id_name", "index"),
    (
        "idx_agent_instances_user_agent_id",
        "idx_agent_instances_agent_type_id",
        "index",
    ),
    # constraints (their backing indexes follow the constraint rename)
    ("user_agents_pkey", "agent_types_pkey", "constraint:agent_types"),
    ("user_agents_user_id_fkey", "agent_types_user_id_fkey", "constraint:agent_types"),
    (
        "agent_instances_user_agent_id_fkey",
        "agent_instances_agent_type_id_fkey",
        "constraint:agent_instances",
    ),
]


def _rename_objects(pairs: list[tuple[str, str, str]]) -> None:
    for old, new, kind in pairs:
        if kind == "index":
            op.execute(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"')
        else:
            table = kind.split(":", 1)[1]
            op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"')


# ``notify_instance_list_change`` from e1a42f472efc, parameterised on the two
# identifiers this migration moves so upgrade and downgrade share one body.
_NOTIFY_FN = """
        CREATE OR REPLACE FUNCTION notify_instance_list_change() RETURNS trigger AS $$
        DECLARE
            channel_name text;
            payload text;
            event_label text;
            v_agent_type_name text;
        BEGIN
            channel_name := 'user_instances_channel_' || NEW.user_id::text;

            IF TG_OP = 'INSERT' THEN
                event_label := 'instance_created';
            ELSE
                event_label := 'instance_updated';
            END IF;

            -- Resolve agent type name from {table} (indexed lookup, negligible cost)
            SELECT name INTO v_agent_type_name
            FROM {table}
            WHERE id = NEW.{column};

            payload := json_build_object(
                'event_type',        event_label,
                'id',                NEW.id,
                'user_id',           NEW.user_id,
                'status',            NEW.status,
                'name',              NEW.name,
                'agent_type_name',   v_agent_type_name,
                'project',           NEW.project,
                'started_at',        to_char(NEW.started_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                'ended_at',          to_char(NEW.ended_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                'instance_metadata', NEW.instance_metadata,
                'has_git_changes',   (NEW.git_diff IS NOT NULL AND NEW.git_diff != ''),
                'timestamp',         to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
            )::text;

            EXECUTE format('NOTIFY %I, %L', channel_name, payload);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.rename_table("user_agents", "agent_types")
    op.alter_column("agent_instances", "user_agent_id", new_column_name="agent_type_id")
    _rename_objects(_RENAMES)
    op.execute(_NOTIFY_FN.format(table="agent_types", column="agent_type_id"))


def downgrade() -> None:
    op.execute(_NOTIFY_FN.format(table="user_agents", column="user_agent_id"))
    _rename_objects([(new, old, kind) for old, new, kind in _RENAMES])
    op.alter_column("agent_instances", "agent_type_id", new_column_name="user_agent_id")
    op.rename_table("agent_types", "user_agents")
