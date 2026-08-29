"""Database queries and operations for servers."""

from .queries import (
    # Low-level functions
    create_agent_instance,
    create_or_get_user_agent,
    create_agent_message,
    create_user_message,
    end_session,
    get_agent_instance,
    get_instance_status_by_id,
    get_latest_message_id_for_instance,
    get_user_messages_after_id,
    get_queued_user_messages,
    get_attachment_for_agent,
    get_or_create_agent_instance,
    mark_message_consumed,
    push_recent_directory_after_spawn,
    upsert_machine_agent_models,
    wait_for_answer,
    update_session_title_if_needed,
    # High-level functions
    send_agent_message,
)

__all__ = [
    # Low-level functions
    "create_agent_instance",
    "create_or_get_user_agent",
    "create_agent_message",
    "create_user_message",
    "end_session",
    "get_agent_instance",
    "get_instance_status_by_id",
    "get_latest_message_id_for_instance",
    "get_user_messages_after_id",
    "get_queued_user_messages",
    "get_attachment_for_agent",
    "get_or_create_agent_instance",
    "mark_message_consumed",
    "push_recent_directory_after_spawn",
    "upsert_machine_agent_models",
    "wait_for_answer",
    "update_session_title_if_needed",
    # High-level functions
    "send_agent_message",
]
