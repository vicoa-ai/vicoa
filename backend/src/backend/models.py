"""
Backend API models for Agent Dashboard.

This module contains all Pydantic models used for API request/response serialization.
Models are organized by functional area: questions, agents, billing, and detailed views.
"""

import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from shared.database.enums import (
    AgentStatus,
    TeamRole,
    InstanceAccessLevel,
)
from shared.database.liveness import LiveState
from shared.webhook_schemas import (
    get_webhook_type_schema,
    validate_webhook_config as validate_webhook_config_func,
    WEBHOOK_TYPES,
)

# ============================================================================
# Message Models
# ============================================================================

# Part of the published request schema, so it must not vary by environment:
# the mobile and web clients are built against it.
MAX_ATTACHMENTS_PER_MESSAGE = 5


class UserMessageRequest(BaseModel):
    content: str = Field(..., description="Message content from the user")
    attachment_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_ATTACHMENTS_PER_MESSAGE,
        description="IDs of previously uploaded attachments to send with this message",
    )


class AttachmentResponse(BaseModel):
    id: str
    mime_type: str
    size_bytes: int
    # Images carry pixel dimensions; general files leave these null.
    width: Optional[int] = None
    height: Optional[int] = None
    filename: Optional[str] = None


class DeepgramTokenResponse(BaseModel):
    token: str = Field(..., description="Short-lived Deepgram temporary token")


# ============================================================================
# User Settings Models
# ============================================================================


class UserNotificationSettingsRequest(BaseModel):
    push_notifications_enabled: Optional[bool] = None
    email_notifications_enabled: Optional[bool] = None
    sms_notifications_enabled: Optional[bool] = None
    phone_number: Optional[str] = Field(
        None, description="Phone number in E.164 format (e.g., +1234567890)"
    )
    notification_email: Optional[str] = Field(
        None, description="Email for notifications (defaults to account email)"
    )


class UserNotificationSettingsResponse(BaseModel):
    push_notifications_enabled: bool
    email_notifications_enabled: bool
    sms_notifications_enabled: bool
    phone_number: Optional[str]
    notification_email: str  # Always returns an email (account email as fallback)

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Agent Models
# ============================================================================


# Summary view of an agent instance (a single agent session/run)
class AgentInstanceResponse(BaseModel):
    id: str
    agent_type_id: str
    agent_type_name: str | None = None
    name: str | None = None
    status: AgentStatus
    started_at: datetime
    ended_at: datetime | None
    latest_message: str | None = None
    latest_message_at: datetime | None = None  # Timestamp of the latest message
    chat_length: int = 0  # Total message count
    last_heartbeat_at: datetime | None = None
    instance_metadata: dict | None = None
    session_config: dict | None = None
    # Agent profile this session was started from (collab P1). PROVENANCE ONLY:
    # `session_config` above is what the session is actually running, and the
    # two legitimately diverge the moment the user switches model mid-session.
    # Clients render the profile's name/avatar by looking the id up in the list
    # they already hold for the picker — deliberately not joined here, so list
    # endpoints stay a single query.
    agent_profile_id: str | None = None
    project: str | None = None
    # Formal projects-entity id, auto-matched from the working directory (the
    # session ↔ project link). Null when no project is set up for that checkout;
    # the sidebar's top-level group falls back to the `project` path when null.
    project_id: str | None = None
    home_dir: str | None = None
    machine_id: str | None = None
    pinned_at: datetime | None = None
    source: str | None = None
    # Linked git worktree the session runs in; null for a main checkout. Lets
    # the sidebar sub-group a project's sessions by worktree.
    worktree_name: str | None = None
    # Derived at read time from the instance + machine heartbeats; never stored.
    # "live" | "reconnecting" | "agent_stopped" | "machine_offline" | "unknown".
    # See shared/database/liveness.py for why this isn't a column.
    live_state: LiveState = LiveState.UNKNOWN
    # Derived from the server-projected rate_limited_until column: True while a
    # maxed time-window rate limit blocks the session, with the binding reset
    # instant. Powers `vicoa session ls --rate-limited` + the auto-continue
    # automation. Never stored on this DTO.
    rate_limited: bool = False
    rate_limit_resets_at: datetime | None = None

    @model_validator(mode="after")
    def _extract_from_metadata(self) -> "AgentInstanceResponse":
        """Promote metadata keys the clients read as typed top-level fields."""
        if not isinstance(self.instance_metadata, dict):
            return self
        if self.source is None:
            s = self.instance_metadata.get("source")
            if s:
                self.source = str(s)
        if self.worktree_name is None:
            w = self.instance_metadata.get("worktree_name")
            if w:
                self.worktree_name = str(w)
        return self

    @field_serializer(
        "started_at",
        "ended_at",
        "latest_message_at",
        "last_heartbeat_at",
        "pinned_at",
        "rate_limit_resets_at",
    )
    def serialize_datetime(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


class PaginatedAgentInstanceResponse(BaseModel):
    items: list[AgentInstanceResponse]
    total: int
    limit: int
    offset: int = 0
    has_more: bool


class ActivityResponse(BaseModel):
    """Aggregated profile activity (daily user-message counts + all-time totals).

    Powers the desktop Settings -> Profile heatmap/streak. See the frontend
    contract in vicoa-web docs/superpowers/specs/2026-07-13-profile-activity-endpoint.md.
    """

    daily: dict[str, int] = Field(
        default_factory=dict,
        description="UTC 'YYYY-MM-DD' day -> count of user-sent messages that day",
    )
    total_sessions: int = Field(
        ..., description="All-time count of the user's sessions"
    )
    total_user_messages: int = Field(
        ..., description="All-time count of the user's own (user-sent) messages"
    )
    total_messages: int = Field(
        ...,
        description="All-time count of all messages (user + agent) in the user's sessions",
    )
    as_of: str = Field(..., description="ISO timestamp of the aggregation")


# Overview of an agent type with recent instances
# and summary statistics for dashboard cards
class AgentTypeOverview(BaseModel):
    id: str
    name: str
    created_at: datetime
    recent_instances: list[AgentInstanceResponse] = []
    total_instances: int = 0
    active_instances: int = 0

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime, _info):
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Detailed Views
# ============================================================================


# Message model for the chat interface
class MessageResponse(BaseModel):
    id: str
    content: str
    sender_type: str
    sender_user_id: str | None = None
    sender_user_email: str | None = None
    sender_user_display_name: str | None = None
    created_at: datetime
    requires_user_input: bool
    message_metadata: dict | None = None

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime, _info):
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


# Complete detailed view of a specific agent instance
# with full message history
class AgentInstanceDetail(BaseModel):
    id: str
    agent_type_id: str
    agent_type_name: str
    name: str | None = None
    status: AgentStatus
    started_at: datetime
    ended_at: datetime | None
    git_diff: str | None = None
    messages: list[MessageResponse] = []
    last_read_message_id: str | None = None
    last_heartbeat_at: datetime | None = None
    access_level: InstanceAccessLevel = InstanceAccessLevel.WRITE
    is_owner: bool = False
    instance_metadata: dict | None = None
    session_config: dict | None = None
    agent_profile_id: str | None = None
    project: str | None = None
    home_dir: str | None = None
    machine_id: str | None = None
    # See AgentInstanceResponse.worktree_name.
    worktree_name: str | None = None
    # Derived at read time; see AgentInstanceResponse.live_state.
    live_state: LiveState = LiveState.UNKNOWN
    # Derived; see AgentInstanceResponse.rate_limited.
    rate_limited: bool = False
    rate_limit_resets_at: datetime | None = None

    @model_validator(mode="after")
    def _extract_worktree_name(self) -> "AgentInstanceDetail":
        if self.worktree_name is None and isinstance(self.instance_metadata, dict):
            w = self.instance_metadata.get("worktree_name")
            if w:
                self.worktree_name = str(w)
        return self

    @field_serializer(
        "started_at", "ended_at", "last_heartbeat_at", "rate_limit_resets_at"
    )
    def serialize_datetime(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Remote Session Models
# ============================================================================


class MachineSummary(BaseModel):
    machine_id: str
    display_name: str | None = None
    hostname: str | None = None
    platform: str | None = None
    home_dir: str | None = None
    last_heartbeat_at: datetime | None = None
    metadata: dict | None = None
    recent_directories: list[str] = Field(default_factory=list)

    @field_serializer("last_heartbeat_at")
    def serialize_datetime(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return dt.isoformat() + "Z"


class MachineListResponse(BaseModel):
    machines: list[MachineSummary] = Field(default_factory=list)


class AgentModelEntry(BaseModel):
    id: str
    label: str


class MachineAgentModelsResponse(BaseModel):
    """Cached available model lists per agent for a machine — keyed by catalog
    agent id (e.g. 'cursor', 'opencode'). Empty until an ACP agent has run at
    least once on the machine."""

    agent_models: dict[str, list[AgentModelEntry]] = Field(default_factory=dict)


class RenameMachineRequest(BaseModel):
    # Optional + validated server-side so empty/whitespace/over-long all return
    # a 400 from one place (machine-management D15) rather than a pydantic 422.
    display_name: str | None = Field(
        default=None, description="New display name for the machine"
    )


class SpawnSessionRequest(BaseModel):
    directory: str = Field(..., description="Directory to launch the remote session in")
    agent: str | None = Field(
        default="claude",
        description="Agent flavor to start: 'claude', 'codex', or 'opencode'",
    )
    prompt: str | None = Field(
        default=None,
        description="Initial prompt to send when the session starts. Defaults to 'Hi' if not provided.",
    )
    metadata: dict | None = Field(
        default=None, description="Additional request metadata"
    )
    agent_profile_id: UUID | None = Field(
        default=None,
        description=(
            "Agent profile this session is started from (collab P1). Recorded on "
            "the instance for display, and the source of the session's "
            "system_prompt — which is resolved server-side rather than trusted "
            "from `metadata`, so the two can never disagree."
        ),
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
    request_id: str = Field(..., description="Identifier of the queued spawn request")
    agent_instance_id: str = Field(
        ..., description="Pre-allocated agent instance identifier"
    )


class SpawnRequestSummary(BaseModel):
    """Summary of a spawn request for listing."""

    request_id: str
    machine_id: str
    directory: str
    agent: str
    status: str
    message: str | None = None
    agent_instance_id: str | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict | None = None

    @field_serializer("created_at", "claimed_at", "completed_at")
    def serialize_datetime(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Team Models
# ============================================================================


class InstanceShareCreateRequest(BaseModel):
    email: str = Field(..., description="Email address to grant access")
    access: InstanceAccessLevel = Field(
        default=InstanceAccessLevel.READ,
        description="Access level to grant",
    )


class InstanceShareResponse(BaseModel):
    id: str
    email: str
    access: InstanceAccessLevel
    user_id: str | None = None
    display_name: str | None = None
    invited: bool = False
    is_owner: bool = False
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime, _info):
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


class TeamCreateRequest(BaseModel):
    name: str = Field(..., description="Team name")


class TeamUpdateRequest(BaseModel):
    name: str = Field(..., description="Updated team name")


class TeamMemberAddRequest(BaseModel):
    email: str = Field(..., description="Email address of member to add")
    role: TeamRole | None = Field(
        default=None,
        description="Role for the member (defaults to MEMBER if omitted)",
    )


class TeamMemberRoleUpdateRequest(BaseModel):
    role: TeamRole


class TeamSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    role: TeamRole
    member_count: int

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime, _info):
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


class TeamMemberResponse(BaseModel):
    id: str
    role: TeamRole
    user_id: str | None = None
    email: str
    display_name: str | None = None
    invited: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime, _info):
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


class TeamDetailResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    role: TeamRole
    members: list[TeamMemberResponse]

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime, _info):
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# User Agent Models
# ============================================================================


class UserAgentRequest(BaseModel):
    name: str = Field(..., description="Name of the user agent")
    webhook_type: str | None = Field(None, description="Type of webhook integration")
    webhook_config: dict | None = Field(None, description="Webhook configuration")
    is_active: bool = Field(True, description="Whether the agent is active")

    @field_validator("webhook_type")
    @classmethod
    def validate_webhook_type(cls, v: str | None) -> str | None:
        """Validate that the webhook type is supported."""
        if v is None:
            return None

        if not get_webhook_type_schema(v):
            supported = ", ".join(WEBHOOK_TYPES.keys())
            raise ValueError(
                f"Unknown webhook type: {v}. Supported types are: {supported}"
            )

        return v

    @field_validator("webhook_config")
    @classmethod
    def validate_webhook_config(cls, v: dict | None, info) -> dict | None:
        """Validate webhook configuration against the webhook type schema."""
        if v is None:
            return None

        # Get the webhook_type from the data
        webhook_type = info.data.get("webhook_type")

        # If no webhook_type, can't validate config
        if not webhook_type:
            return v

        # Validate the configuration
        is_valid, error_msg = validate_webhook_config_func(webhook_type, v)
        if not is_valid:
            raise ValueError(f"Invalid webhook configuration: {error_msg}")

        return v


class UserAgentResponse(BaseModel):
    id: str
    name: str
    webhook_type: str | None = None
    webhook_config: dict | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    instance_count: int = 0
    active_instance_count: int = 0
    waiting_instance_count: int = 0
    completed_instance_count: int = 0
    error_instance_count: int = 0

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime, _info):
        return dt.isoformat() + "Z"

    model_config = ConfigDict(from_attributes=True)


class CreateAgentInstanceRequest(BaseModel):
    """Request to create a new agent instance with dynamic runtime fields based on webhook type."""

    name: str | None = Field(
        None, description="Optional display name for the agent instance"
    )

    # Accept any additional fields dynamically based on the webhook's runtime_fields
    # (e.g., prompt, worktree_name, branch_name for VICOA_SERVE)
    model_config = ConfigDict(extra="allow")


class WebhookTriggerResponse(BaseModel):
    success: bool
    agent_instance_id: str | None = None
    message: str
    error: str | None = None


# ============================================================================
# Projects & Tasks Models (plans/todos/tasks-and-projects-feature.md)
# ============================================================================

TaskStatusLiteral = Literal[
    "backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"
]
TaskPriorityLiteral = Literal["urgent", "high", "medium", "low", "none"]


class ProjectDirectoryResponse(BaseModel):
    """Where the project is checked out on one machine."""

    machine_id: UUID
    machine_name: str | None = None
    local_path: str

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    # Task-identifier prefix; None until the project's first task allocates one.
    key: str | None = None
    git_remote_url: str | None = None
    color: str | None = None
    icon: str | None = None
    # Served image-icon URL + who set it ('user' | 'git' | None). Clients render
    # the fallback chain icon_image_uri → emoji icon/color → generated default.
    icon_image_uri: str | None = None
    icon_source: str | None = None
    is_inbox: bool
    is_archived: bool
    archived_at: datetime | None = None
    # Inlined rather than a separate endpoint: the lists are tiny and both the
    # Tasks page and the new-session directory resolver need them alongside the
    # project itself.
    directories: list[ProjectDirectoryResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SetProjectDirectoryRequest(BaseModel):
    machine_id: UUID
    local_path: str = Field(..., min_length=1, max_length=4096)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    color: str | None = Field(default=None, max_length=16)
    icon: str | None = Field(default=None, max_length=64)
    git_remote_url: str | None = None


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    color: str | None = Field(default=None, max_length=16)
    icon: str | None = Field(default=None, max_length=64)
    git_remote_url: str | None = None
    is_archived: bool | None = None
    # The task-identifier prefix ("VIC" → tasks read "VIC-42"). Auto-derived on
    # a project's first task; editable here. Uppercased and validated against
    # the same shape the deriver produces.
    key: str | None = Field(default=None, min_length=2, max_length=8)

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        upper = v.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,7}", upper):
            raise ValueError(
                "key must be 2-8 characters, letters and digits, starting with a letter"
            )
        return upper


class PrincipalResponse(BaseModel):
    """A user or an agent, in the one shape every surface renders (§2 layer 1).

    Never carries an email: a principal may show a display name and a picture on
    a shared or public surface, and nothing else (§10.4).
    """

    type: Literal["user", "agent", "system"]
    id: UUID | None = None
    name: str | None = None
    avatar_image_uri: str | None = None
    emoji: str | None = None
    # Cache-buster for the avatar proxy; the URL itself is stable.
    updated_at: datetime | None = None


class TaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    # Per-project sequential number and the rendered "VIC-42". Both are None for
    # a task whose project has no key yet (or that predates the backfill), and
    # clients must render such a task without an identifier rather than
    # inventing one.
    number: int | None = None
    identifier: str | None = None
    title: str
    description: str | None = None
    status: TaskStatusLiteral
    priority: TaskPriorityLiteral
    position: float
    parent_task_id: UUID | None = None
    # Denormalized so a sub-task's session prompt can say "Part of: <title>"
    # without a second fetch (§8.3).
    parent_title: str | None = None
    assignee_type: Literal["user", "agent"] | None = None
    assignee_id: UUID | None = None
    assignee: PrincipalResponse | None = None
    labels: list["TaskLabelResponse"] = Field(default_factory=list)
    start_date: datetime | None = None
    due_date: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskAssigneeFields(BaseModel):
    """Shared assignee validation: the pair moves together or not at all."""

    assignee_type: Literal["user", "agent"] | None = None
    assignee_id: UUID | None = None

    @model_validator(mode="after")
    def check_assignee_pair(self):
        if (self.assignee_type is None) != (self.assignee_id is None):
            raise ValueError(
                "assignee_type and assignee_id must be set or cleared together"
            )
        return self


class CreateTaskRequest(TaskAssigneeFields):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    # Omitted → the user's Inbox ("No project" bucket).
    project_id: UUID | None = None
    status: TaskStatusLiteral = "backlog"
    priority: TaskPriorityLiteral = "none"
    position: float = 0
    parent_task_id: UUID | None = None
    label_ids: list[UUID] | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None


class UpdateTaskRequest(TaskAssigneeFields):
    """PATCH body — only explicitly sent fields are applied, so date fields
    can be cleared by sending null."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    project_id: UUID | None = None
    status: TaskStatusLiteral | None = None
    priority: TaskPriorityLiteral | None = None
    position: float | None = None
    parent_task_id: UUID | None = None
    label_ids: list[UUID] | None = None
    start_date: datetime | None = None
    due_date: datetime | None = None


class TaskLabelResponse(BaseModel):
    id: UUID
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)


class CreateTaskLabelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        return _normalize_label_color(v)


class UpdateTaskLabelRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return None if v is None else _normalize_label_color(v)


TaskReactionTargetLiteral = Literal["task", "comment"]

# Bounded so one comment cannot be a document. Generous enough for a pasted
# stack trace, small enough that the timeline stays a timeline.
MAX_COMMENT_BODY_CHARS = 20_000


# How many reactors a summary names before it stops. A tooltip that lists forty
# people is not more informative than one that lists eight and says "and 32
# others", and the payload grows with every reaction on a shared board.
MAX_NAMED_REACTORS = 8


class TaskReactionSummary(BaseModel):
    """One emoji on one target, collapsed across users."""

    emoji: str
    count: int
    # Whether the requesting user is one of them — drives the pill's filled state.
    reacted: bool
    # Who reacted, oldest first, capped at MAX_NAMED_REACTORS. `count` is the
    # true total, so a client can render "and N others" from the difference.
    # Display names only, never emails (§10.4) — this feeds public pages in P4.
    reactors: list[PrincipalResponse] = Field(default_factory=list)


class TaskCommentResponse(BaseModel):
    id: UUID
    task_id: UUID
    author: PrincipalResponse
    # None once soft-deleted: the row stays so the thread keeps its shape, but
    # the text does not travel to the client.
    body: str | None = None
    kind: Literal["comment", "system"]
    reactions: list[TaskReactionSummary] = Field(default_factory=list)
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None


class TaskActivityResponse(BaseModel):
    id: UUID
    # None when the change had no request context (a background sweep). Rendered
    # as an unattributed line rather than dropped.
    actor: PrincipalResponse | None = None
    action: str
    details: dict = Field(default_factory=dict)
    created_at: datetime


class TaskTimelineResponse(BaseModel):
    """Comments and activity in one fetch.

    One round trip, one cache key, and — because reactions and principals are
    resolved server-side across the whole page — no N+1 from the client
    hydrating each row.
    """

    comments: list[TaskCommentResponse] = Field(default_factory=list)
    activity: list[TaskActivityResponse] = Field(default_factory=list)
    # Reactions on the task itself, not on any comment — the task body is a
    # reactable target too, the same way a GitHub issue's opening post is.
    reactions: list[TaskReactionSummary] = Field(default_factory=list)


class CreateTaskCommentRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=MAX_COMMENT_BODY_CHARS)


class UpdateTaskCommentRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=MAX_COMMENT_BODY_CHARS)


class ToggleTaskReactionRequest(BaseModel):
    target_type: TaskReactionTargetLiteral
    target_id: UUID
    emoji: str = Field(..., min_length=1, max_length=16)


def _normalize_label_color(value: str) -> str:
    """Pin label colors to #rrggbb — the web injects them into inline styles
    (multica's LabelChip invariant), so anything looser is an injection
    vector."""
    import re

    stripped = value.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", stripped):
        raise ValueError("color must be a #rrggbb hex value")
    return f"#{stripped.lower()}"


# ---------------------------------------------------------------------------
# Automations (scheduled agent runs) — automation-scheduled-tasks plan §v1
# ---------------------------------------------------------------------------

AutomationScheduleKindLiteral = Literal["once", "recurring"]
AutomationRunStatusLiteral = Literal["fired", "missed_offline", "failed", "skipped"]


class AutomationRunResponse(BaseModel):
    id: UUID
    automation_id: UUID
    agent_instance_id: UUID | None = None
    planned_at: datetime | None = None
    fired_at: datetime
    status: AutomationRunStatusLiteral
    detail: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationResponse(BaseModel):
    id: UUID
    title: str
    prompt: str
    machine_id: UUID
    directory: str
    worktree: dict | None = None
    session_config: dict
    # Live reference to an agent profile (collab P1). When set, the scheduler
    # resolves the profile at dispatch and `session_config` is the fallback
    # snapshot rather than the source of truth.
    agent_profile_id: UUID | None = None
    schedule_kind: AutomationScheduleKindLiteral
    frequency: dict | None = None
    timezone: str
    next_run_at: datetime | None = None
    enabled: bool
    last_run_at: datetime | None = None
    last_run_status: AutomationRunStatusLiteral | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _validate_session_config(config: dict) -> dict:
    """A session config must at least name its agent — the scheduler dispatches
    by agent (`toSpawnMetadata` branches on it)."""
    agent = config.get("agent")
    if not isinstance(agent, str) or not agent.strip():
        raise ValueError("session_config.agent is required")
    return config


class CreateAutomationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    prompt: str = Field(..., min_length=1)
    machine_id: UUID
    directory: str = Field(..., min_length=1)
    # {"mode": "none"|"new"|"existing", "path"?: str}
    worktree: dict | None = None
    session_config: dict
    agent_profile_id: UUID | None = None
    schedule_kind: AutomationScheduleKindLiteral
    # One-time: absolute instant (client sends a UTC-anchored ISO datetime).
    run_at: datetime | None = None
    # Recurring: structured frequency (see shared/scheduling/frequency.py).
    frequency: dict | None = None
    timezone: str = Field(default="UTC", max_length=64)
    enabled: bool = True

    @field_validator("session_config")
    @classmethod
    def _check_session_config(cls, v: dict) -> dict:
        return _validate_session_config(v)

    @model_validator(mode="after")
    def _check_schedule(self) -> "CreateAutomationRequest":
        if self.schedule_kind == "once" and self.run_at is None:
            raise ValueError("run_at is required when schedule_kind is 'once'")
        if self.schedule_kind == "recurring" and not self.frequency:
            raise ValueError("frequency is required when schedule_kind is 'recurring'")
        return self


class UpdateAutomationRequest(BaseModel):
    """PATCH body — only explicitly sent fields are applied. Sending any of
    schedule_kind / frequency / timezone / run_at recomputes the next fire time
    (toggling `enabled` alone does not)."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    prompt: str | None = Field(default=None, min_length=1)
    machine_id: UUID | None = None
    directory: str | None = Field(default=None, min_length=1)
    worktree: dict | None = None
    session_config: dict | None = None
    agent_profile_id: UUID | None = None
    schedule_kind: AutomationScheduleKindLiteral | None = None
    run_at: datetime | None = None
    frequency: dict | None = None
    timezone: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None

    @field_validator("session_config")
    @classmethod
    def _check_session_config(cls, v: dict | None) -> dict | None:
        return None if v is None else _validate_session_config(v)


class RecordAutomationRunRequest(BaseModel):
    """Report the outcome of a client-side ("run now") spawn so it lands in
    history. Scheduler-fired runs are recorded server-side, not via this."""

    status: AutomationRunStatusLiteral
    agent_instance_id: UUID | None = None
    detail: str | None = None


# ---------------------------------------------------------------------------
# Workspace search (cmd+K palette) — cross-entity substring search
# ---------------------------------------------------------------------------


class SearchSessionResult(BaseModel):
    id: str
    name: str | None = None
    agent_type_name: str | None = None
    status: AgentStatus
    project: str | None = None
    started_at: datetime
    # Newest message regardless of match — the sidebar's title fallback for
    # unnamed sessions, so the palette can render the same title.
    latest_message: str | None = None
    latest_message_at: datetime | None = None
    match_source: Literal["name", "project", "message"]
    # Context window around the hit; only set for message matches.
    snippet: str | None = None

    @field_serializer("started_at", "latest_message_at")
    def serialize_datetime(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return dt.isoformat() + "Z"


class SearchTaskResult(BaseModel):
    id: UUID
    title: str
    status: TaskStatusLiteral
    priority: TaskPriorityLiteral
    project_id: UUID
    updated_at: datetime
    match_source: Literal["title", "description"]
    snippet: str | None = None


class SearchAutomationResult(BaseModel):
    id: UUID
    title: str
    enabled: bool
    schedule_kind: AutomationScheduleKindLiteral
    next_run_at: datetime | None = None
    match_source: Literal["title", "prompt"]
    snippet: str | None = None


class WorkspaceSearchResponse(BaseModel):
    query: str
    sessions: list[SearchSessionResult]
    tasks: list[SearchTaskResult]
    automations: list[SearchAutomationResult]
