"""add_user_instance_list_sse_channel

Revision ID: e1a42f472efc
Revises: d4b5c6e7f8a9
Create Date: 2026-04-24 15:05:57.636247

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1a42f472efc"
down_revision: Union[str, None] = "d4b5c6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Notifies a per-user channel on meaningful agent_instances changes so SSE
    # clients can update their instance list without polling.
    #
    # Watched columns (all real columns on agent_instances):
    #   status           — primary state shown in sidebar
    #   name             — session title shown in sidebar
    #   ended_at         — session finish signal
    #   instance_metadata — low-frequency, can carry UI hints
    #   git_diff         — content omitted from payload; only a boolean flag is sent
    #                      (full diff is already delivered via message_channel_{id})
    #
    # NOT watched:
    #   last_heartbeat_at — updates every 30 s per session; no UI value for the list
    op.execute("""
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

            -- Resolve agent type name from user_agents (indexed lookup, negligible cost)
            SELECT name INTO v_agent_type_name
            FROM user_agents
            WHERE id = NEW.user_agent_id;

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
    """)

    # INSERT — fires when a new session is registered
    op.execute("""
        CREATE TRIGGER agent_instance_list_insert_notify
        AFTER INSERT ON agent_instances
        FOR EACH ROW
        EXECUTE FUNCTION notify_instance_list_change();
    """)

    # UPDATE — only watches meaningful columns; last_heartbeat_at intentionally excluded
    op.execute("""
        CREATE TRIGGER agent_instance_list_update_notify
        AFTER UPDATE OF status, name, ended_at, instance_metadata, git_diff ON agent_instances
        FOR EACH ROW
        WHEN (
            OLD.status            IS DISTINCT FROM NEW.status OR
            OLD.name              IS DISTINCT FROM NEW.name OR
            OLD.ended_at          IS DISTINCT FROM NEW.ended_at OR
            OLD.instance_metadata::text IS DISTINCT FROM NEW.instance_metadata::text OR
            OLD.git_diff          IS DISTINCT FROM NEW.git_diff
        )
        EXECUTE FUNCTION notify_instance_list_change();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS agent_instance_list_insert_notify ON agent_instances;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS agent_instance_list_update_notify ON agent_instances;"
    )
    op.execute("DROP FUNCTION IF EXISTS notify_instance_list_change();")
