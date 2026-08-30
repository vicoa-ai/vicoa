"""Add smart payload to notify_message_change trigger

For messages whose full JSON payload fits within the PG NOTIFY size budget,
include the content and all client-required fields directly in the payload so
the SSE generator can skip the per-message DB enrichment query (~95% of
messages). For larger messages, set needs_enrichment=true so the generator
falls back to the existing get_message_by_id() query.

For USER-sent messages, the trigger joins the users table to populate
sender_user_email and sender_user_display_name, so clients always see who
sent the message without an extra round-trip from the SSE generator.

Uses octet_length() on the candidate payload (not character count) so JSON
escaping and multi-byte characters are measured correctly against the 8000-byte
PostgreSQL NOTIFY limit. 7500 bytes gives a small safety margin.

Revision ID: b2e3f4a5c6d7
Revises: b5845c1df2cb
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2e3f4a5c6d7"
down_revision: Union[str, None] = "b5845c1df2cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_message_change() RETURNS trigger AS $$
        DECLARE
            channel_name text;
            payload text;
            candidate_payload text;
            event_type text;
            sender_email text;
            sender_display_name text;
        BEGIN
            channel_name := 'message_channel_' || NEW.agent_instance_id::text;

            IF TG_OP = 'INSERT' THEN
                event_type := 'message_insert';
            ELSIF TG_OP = 'UPDATE' THEN
                event_type := 'message_update';
            END IF;

            -- Resolve sender info for USER messages so clients can render
            -- sender identity without hitting the SSE enrichment path.
            IF NEW.sender_user_id IS NOT NULL THEN
                SELECT email, display_name
                INTO sender_email, sender_display_name
                FROM users
                WHERE id = NEW.sender_user_id;
            END IF;

            -- Build the full candidate payload including content.
            -- Check its byte size before committing to avoid exceeding PG's 8000-byte
            -- NOTIFY limit; 7500 bytes leaves room for the channel name and protocol overhead.
            candidate_payload := json_build_object(
                'event_type', event_type,
                'id', NEW.id,
                'agent_instance_id', NEW.agent_instance_id,
                'sender_type', NEW.sender_type,
                'sender_user_id', NEW.sender_user_id,
                'sender_user_email', sender_email,
                'sender_user_display_name', sender_display_name,
                'content', NEW.content,
                'created_at', to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                'requires_user_input', NEW.requires_user_input,
                'message_metadata', NEW.message_metadata,
                'old_requires_user_input', CASE
                    WHEN TG_OP = 'UPDATE' THEN OLD.requires_user_input
                    ELSE NULL
                END
            )::text;

            IF octet_length(candidate_payload) <= 7500 THEN
                payload := candidate_payload;
            ELSE
                -- Oversized: send the lightweight envelope and let the SSE
                -- generator fetch the full row via get_message_by_id().
                payload := json_build_object(
                    'event_type', event_type,
                    'id', NEW.id,
                    'agent_instance_id', NEW.agent_instance_id,
                    'sender_type', NEW.sender_type,
                    'created_at', to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                    'requires_user_input', NEW.requires_user_input,
                    'old_requires_user_input', CASE
                        WHEN TG_OP = 'UPDATE' THEN OLD.requires_user_input
                        ELSE NULL
                    END,
                    'needs_enrichment', true
                )::text;
            END IF;

            EXECUTE format('NOTIFY %I, %L', channel_name, payload);

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Restore the lightweight-only trigger from 9fe045ea7ad9
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_message_change() RETURNS trigger AS $$
        DECLARE
            channel_name text;
            payload text;
            event_type text;
        BEGIN
            channel_name := 'message_channel_' || NEW.agent_instance_id::text;

            IF TG_OP = 'INSERT' THEN
                event_type := 'message_insert';
            ELSIF TG_OP = 'UPDATE' THEN
                event_type := 'message_update';
            END IF;

            payload := json_build_object(
                'event_type', event_type,
                'id', NEW.id,
                'agent_instance_id', NEW.agent_instance_id,
                'sender_type', NEW.sender_type,
                'created_at', to_char(NEW.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
                'requires_user_input', NEW.requires_user_input,
                'old_requires_user_input', CASE
                    WHEN TG_OP = 'UPDATE' THEN OLD.requires_user_input
                    ELSE NULL
                END
            )::text;

            EXECUTE format('NOTIFY %I, %L', channel_name, payload);

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
