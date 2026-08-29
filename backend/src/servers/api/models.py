"""Pydantic models for FastAPI request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from servers.shared.models import (
    BaseEndSessionRequest,
    BaseEndSessionResponse,
)


class RegisterMachineRequest(BaseModel):
    machine_id: str | None = Field(
        default=None,
        description="Existing machine id to reuse. If omitted a new machine will be created.",
    )
    hardware_id: str | None = Field(
        default=None,
        description=(
            "Stable per-host token (hashed hardware id). When present the "
            "server dedups on (user_id, hardware_id) so re-auth / key rotation "
            "resolves to the same machine regardless of the supplied machine_id."
        ),
    )
    hostname: str = Field(..., description="Reported hostname of the machine")
    platform: str | None = Field(
        default=None, description="OS/platform string reported by the CLI"
    )
    home_dir: str | None = Field(
        default=None, description="Home directory of the user running the daemon"
    )
    display_name: str | None = Field(
        default=None,
        description="Optional user friendly name supplied by the CLI",
    )
    metadata: dict | None = Field(
        default=None,
        description="Additional metadata about the machine (cwd, versions, etc)",
    )


class RegisterMachineResponse(BaseModel):
    machine_id: str = Field(..., description="Identifier of the registered machine")
    display_name: str | None = Field(
        default=None, description="User friendly name stored for the machine"
    )
    hostname: str | None = Field(default=None, description="Reported hostname")
    platform: str | None = Field(default=None, description="Reported platform")
    home_dir: str | None = Field(default=None, description="Reported home directory")
    last_heartbeat_at: datetime | None = Field(
        default=None, description="Timestamp of the last heartbeat"
    )
    metadata: dict | None = Field(
        default=None, description="Metadata stored on the machine record"
    )


class HeartbeatMachineRequest(BaseModel):
    metadata: dict | None = Field(
        default=None, description="Optional metadata updates provided with heartbeat"
    )


class UpdateMachineRecentDirectoryRequest(BaseModel):
    cwd: str = Field(..., description="Directory to add to the machine recent history")
    cli_version: str | None = Field(
        default=None, description="CLI version associated with this directory update"
    )
    python_version: str | None = Field(
        default=None, description="Python version associated with this directory update"
    )


class MachineSummary(BaseModel):
    machine_id: str = Field(..., description="Identifier of the machine")
    display_name: str | None = Field(default=None, description="Display name if set")
    hostname: str | None = Field(default=None, description="Hostname reported")
    platform: str | None = Field(default=None, description="Platform reported")
    home_dir: str | None = Field(default=None, description="Home directory reported")
    last_heartbeat_at: datetime | None = Field(
        default=None, description="Timestamp of the most recent heartbeat"
    )
    metadata: dict | None = Field(
        default=None, description="Stored metadata for the machine"
    )
    recent_directories: list[str] = Field(
        default_factory=list,
        description="Recently used directories reported for this machine",
    )


class MachineListResponse(BaseModel):
    machines: list[MachineSummary] = Field(
        default_factory=list, description="List of machines registered for the user"
    )


class SpawnSessionRequest(BaseModel):
    directory: str = Field(..., description="Directory the session should start in")
    agent: str | None = Field(
        default="claude",
        description="Agent flavor to start: 'claude', 'codex', or 'opencode'",
    )
    prompt: str | None = Field(
        default=None,
        description="Optional initial prompt to POST as the first user "
        "message. Empty/missing starts the session blank — the runner "
        "parks waiting for user input.",
    )
    metadata: dict | None = Field(
        default=None,
        description="Additional metadata (e.g. UI request id) to attach to the request",
    )

    @field_validator("agent", mode="before")
    @classmethod
    def normalize_agent(cls, value: str | None) -> str:
        if value is None:
            return "claude"

        normalized = str(value).strip().lower()

        # Valid ids come from the shared agent catalog (claude/codex/opencode
        # plus the generic ACP agents) so a new agent ships without touching
        # this validator. "claude code" stays as a legacy alias.
        from shared.agent_catalog import AGENT_CATALOG

        known = {agent["id"] for agent in AGENT_CATALOG["agents"]}
        if normalized in known:
            return normalized
        if normalized == "claude code":
            return "claude"
        raise ValueError(f"agent must be one of: {', '.join(sorted(known))}")


class SpawnSessionResponse(BaseModel):
    request_id: str = Field(..., description="Identifier for the spawn request")
    agent_instance_id: str = Field(
        ..., description="Pre-allocated agent instance identifier"
    )


class NextSpawnRequestResponse(BaseModel):
    request_id: str = Field(..., description="Identifier for the spawn request")
    directory: str = Field(..., description="Directory to start the session in")
    agent: str = Field(..., description="Agent flavor requested")
    agent_instance_id: str | None = Field(
        default=None,
        description="Agent instance identifier reserved for this spawn request",
    )
    metadata: dict | None = Field(
        default=None, description="Metadata that accompanied the spawn request"
    )
    requested_at: datetime = Field(
        ..., description="Timestamp when the request was created"
    )


class UpdateSpawnRequestRequest(BaseModel):
    status: Literal["started", "success", "error"] = Field(
        ..., description="Outcome of processing the request"
    )
    agent_instance_id: str | None = Field(
        default=None, description="Agent instance id created for successful spawns"
    )
    message: str | None = Field(
        default=None,
        description="Optional status message or error description",
    )


# Request models
class RegisterAgentInstanceRequest(BaseModel):
    """Request model for registering an agent instance."""

    agent_type: str = Field(
        ..., description="Name of the agent type to associate the instance with"
    )
    agent_instance_id: str | None = Field(
        default=None,
        description="Optional existing instance id to reuse for reconnect scenarios",
    )
    name: str | None = Field(default=None, description="Friendly name for the instance")
    project: str | None = Field(
        default=None,
        description="Project directory path or git repository URL",
    )
    home_dir: str | None = Field(
        default=None,
        description="Home directory path for expanding tilde (~) in project paths",
    )
    transport: str | None = Field(
        default=None, description="Transport mode for the instance (e.g. 'ws')"
    )
    source: str | None = Field(
        default=None,
        description="How the instance was launched: 'daemon' (RPC spawn) or 'tui'",
    )
    worktree_name: str | None = Field(
        default=None,
        description=(
            "Linked git worktree this session runs in, probed by the SDK from "
            "the session's cwd. Null for a repo's main checkout and for "
            "non-git dirs. Stored on instance_metadata and surfaced as a "
            "top-level response field, like `source`."
        ),
    )
    machine_id: str | None = Field(
        default=None,
        description=(
            "Id of the machine this session runs on, read from the daemon "
            "state file by the wrapper/SDK (machine-management D8). Validated "
            "and ownership-scoped server-side; an unknown or foreign id is "
            "silently dropped to null, never an error."
        ),
    )
    session_config: dict | None = Field(
        default=None,
        description=(
            "Spawn-time user-visible config (agent, model, effort, "
            "permission/opencode mode). Mirrors SessionConfig.toJson() on "
            "mobile. Absent field = preserve any pre-staged value on the row; "
            "explicit null = wrapper knows but is empty. See "
            "plans/session-config-storage.md §3.4."
        ),
    )
    task_id: str | None = Field(
        default=None,
        description=(
            "Link this session to a task at spawn time (full UUID). The task "
            "must belong to the caller. The linked task's status is then driven "
            "from the run's status by the shared before_flush sync "
            "(ACTIVE→in_progress, COMPLETED→done, REVIEWED→in_review)."
        ),
    )


class CreateMessageRequest(BaseModel):
    """Request model for creating a new message."""

    agent_instance_id: str = Field(
        ...,
        description="Existing agent instance ID. Creates a new agent instance if ID doesn't exist.",
    )
    agent_type: str | None = Field(
        None, description="Type of agent (e.g., 'claude_code', 'cursor')"
    )
    content: str = Field(
        ..., description="Message content (step description or question text)"
    )
    requires_user_input: bool = Field(
        False, description="Whether this message requires user input (is a question)"
    )
    send_email: bool | None = Field(
        None,
        description="Whether to send email notification (overrides user preference)",
    )
    send_sms: bool | None = Field(
        None, description="Whether to send SMS notification (overrides user preference)"
    )
    send_push: bool | None = Field(
        None,
        description="Whether to send push notification (overrides user preference)",
    )
    git_diff: str | None = Field(
        None,
        description=(
            "Git diff content to store with the instance. "
            "Base64-encoded values are automatically detected and decoded."
        ),
    )
    message_metadata: dict | None = Field(
        None,
        description="Optional metadata to store with the message (e.g., webhook URLs)",
    )


class CreateUserMessageRequest(BaseModel):
    """Request model for creating a user message."""

    agent_instance_id: str = Field(
        ..., description="Agent instance ID to send the message to"
    )
    content: str = Field(..., description="Message content")
    mark_as_read: bool = Field(
        True,
        description="Whether to mark this message as read (update last_read_message_id)",
    )


class UpdateAgentInstanceRequest(BaseModel):
    """Request model for partial updates to an agent instance.

    All fields are optional; only the fields present in the request body are
    written, others are left untouched. Used by the rename flow (name) and by
    the Claude TUI wrapper's JSONLMonitor (session_config) — see
    plans/session-config-storage.md §3.3 (Post-init PATCH).
    """

    name: str | None = Field(
        default=None, description="Updated name for the agent instance"
    )
    session_config: dict | None = Field(
        default=None,
        description=(
            "Partial session_config merge. Keys present in this dict overwrite "
            "the corresponding keys on the row; other keys are preserved. Use "
            "an empty dict for a no-op. Absent field = preserve the entire "
            "existing session_config."
        ),
    )
    instance_metadata: dict | None = Field(
        default=None,
        description=(
            "Partial instance_metadata merge, same semantics as session_config. "
            "Carries the live `usage` blob (context window + rate limits) stamped "
            "by the headless runners. Absent field = preserve existing metadata."
        ),
    )
    task_id: str | None = Field(
        default=None,
        description=(
            "Link (or, with an explicit null, unlink) this session's task. "
            "Field-present semantics: absent = leave the link unchanged, null = "
            "unlink, a UUID = link. The task must belong to the caller. Linking "
            "drives the task's status from the run's status via the shared "
            "before_flush sync, so linking an already-running session flips its "
            "task to in_progress."
        ),
    )


class EndSessionRequest(BaseEndSessionRequest):
    """FastAPI-specific request model for ending a session."""

    pass


# Response models
class RegisterAgentInstanceResponse(BaseModel):
    """Response payload for registering an agent instance."""

    agent_instance_id: str = Field(..., description="Identifier of the agent instance")
    agent_type_id: str | None = Field(
        default=None, description="Database identifier of the agent type"
    )
    agent_type_name: str | None = Field(
        default=None, description="Human-readable agent type name"
    )
    status: str = Field(..., description="Current status of the agent instance")
    name: str | None = Field(
        default=None, description="Friendly name stored on the instance"
    )
    instance_metadata: dict | None = Field(
        default=None, description="Arbitrary metadata associated with the instance"
    )
    project: str | None = Field(
        default=None, description="Project directory path or git repository URL"
    )
    home_dir: str | None = Field(
        default=None,
        description="Home directory path for expanding tilde (~) in project paths",
    )
    machine_id: str | None = Field(
        default=None,
        description="Id of the machine this session runs on, if linked (D14)",
    )
    session_config: dict | None = Field(
        default=None,
        description="Spawn-time user-visible config persisted on the row",
    )


class MessageResponse(BaseModel):
    """Response model for individual messages."""

    id: str = Field(..., description="Message ID")
    content: str = Field(..., description="Message content")
    sender_type: str = Field(..., description="Sender type: 'agent' or 'user'")
    created_at: str = Field(..., description="ISO timestamp when message was created")
    requires_user_input: bool = Field(
        ..., description="Whether this message requires user input"
    )
    message_metadata: dict | None = Field(
        default=None,
        description="Structured metadata (e.g. image attachments) stamped on the message",
    )


class CreateMessageResponse(BaseModel):
    """Response model for create message endpoint."""

    success: bool = Field(
        ..., description="Whether the message was created successfully"
    )
    agent_instance_id: str = Field(
        ..., description="Agent instance ID (new or existing)"
    )
    message_id: str = Field(..., description="ID of the message that was created")
    queued_user_messages: list[MessageResponse] = Field(
        default_factory=list,
        description="List of queued user messages with full metadata",
    )


class CreateUserMessageResponse(BaseModel):
    """Response model for create user message endpoint."""

    success: bool = Field(
        ..., description="Whether the message was created successfully"
    )
    message_id: str = Field(..., description="ID of the created message")
    marked_as_read: bool = Field(
        ..., description="Whether the message was marked as read"
    )


class GetMessagesResponse(BaseModel):
    """Response model for get messages endpoint."""

    agent_instance_id: str = Field(..., description="Agent instance ID")
    messages: list[MessageResponse] = Field(
        default_factory=list, description="List of messages"
    )
    status: str = Field(
        "ok",
        description="Status: 'ok' if messages retrieved, 'stale' if last_read_message_id is outdated",
    )


class EndSessionResponse(BaseEndSessionResponse):
    """FastAPI-specific response model for end session endpoint."""

    pass


class VerifyAuthResponse(BaseModel):
    """Response model for auth verification endpoint."""

    success: bool = Field(..., description="Whether authentication was successful")
    user_id: str = Field(..., description="Authenticated user's ID")
    email: str = Field(..., description="User's email address")
    display_name: str | None = Field(None, description="User's display name")
    message: str = Field(..., description="Success or error message")


class SyncCommandsRequest(BaseModel):
    """Request model for syncing slash commands from CLI."""

    agent_type: Literal["claude", "codex", "opencode"] = Field(
        ..., description="Agent type: 'claude', 'codex', or 'opencode'"
    )
    commands: dict[str, dict[str, str]] = Field(
        ...,
        description=(
            "Commands dict: {name: {description: ..., kind: 'command'|'skill', "
            "insert?: ...}}. kind/insert are optional for old CLIs."
        ),
    )


class SyncCommandsResponse(BaseModel):
    """Response model for sync commands endpoint."""

    success: bool = Field(..., description="Whether the sync was successful")
    synced_count: int = Field(..., description="Number of commands synced")
    agent_type: str = Field(..., description="Agent type that was synced")


class SyncFilesRequest(BaseModel):
    """Request model for syncing project files from CLI."""

    project_path: str = Field(..., description="Absolute path to the project directory")
    files: list[str] = Field(
        ...,
        description="List of relative file paths from project_path",
    )


class SyncFilesResponse(BaseModel):
    """Response model for sync files endpoint."""

    success: bool = Field(..., description="Whether the sync was successful")
    synced_count: int = Field(..., description="Number of files synced")
    project_path: str = Field(..., description="Project path that was synced")


class MachineRpcRequest(BaseModel):
    """Request body for the POST /machines/{id}/rpc RPC fallback (§2.8)."""

    method: str = Field(..., description="RPC method to invoke on the daemon")
    params: dict = Field(default_factory=dict, description="Method parameters")
