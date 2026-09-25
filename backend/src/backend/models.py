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
    # The task this run works on (tasks plan §8b). Read-only here; it is set by
    # PATCH /agent-instances/{id}. Clients need it to tell "this session already
    # belongs to a task" from "this session is unfiled" — the `#` composer
    # reference uses it to decide whether a referenced task is a new link.
    task_id: str | None = None
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
    # See AgentInstanceResponse.project_id. The web sidebar composes a
    # just-created session's row from this detail (the WS `instance-created`
    # body is the bare column set), so without it the new session groups by
    # path basename and shows as a second "project" until the next list load.
    project_id: str | None = None
    # See AgentInstanceResponse.task_id. The chat page reads the session from
    # this detail, so the composer's `#` reference needs it here too.
    task_id: str | None = None
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
    """Cached available model (and mode) lists per agent for a machine — keyed
    by catalog agent id (e.g. 'cursor', 'opencode'). Empty until an ACP agent
    has run at least once on the machine or a daemon probe has cached it.
    ``agent_modes`` only has keys for agents whose source reported modes; a
    client keeps its catalog placeholder for the rest."""

    agent_models: dict[str, list[AgentModelEntry]] = Field(default_factory=dict)
    agent_modes: dict[str, list[AgentModelEntry]] = Field(default_factory=dict)


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

        # Catalog ids (claude/codex/opencode plus the generic ACP agents) are
        # always valid, and "claude code" stays as a legacy alias.
        from shared.agent_catalog import AGENT_CATALOG

        known = {agent["id"] for agent in AGENT_CATALOG["agents"]}
        if normalized in known:
            return normalized
        if normalized == "claude code":
            return "claude"

        # Anything else is checked for *shape* only. A user-defined provider
        # lives in that user's ~/.vicoa/config.json on their own machine, so the
        # backend cannot hold a list of them — and the daemon is the real
        # authority regardless: it refuses an id it does not recognise, with the
        # list it does. Clients pick from the machine row's `available_agents`,
        # which the daemon publishes including custom providers. Rejecting
        # unknown ids here would only mean a custom agent 422s before the
        # machine that owns it ever sees the request.
        from protocol.provider_overrides import is_valid_provider_id

        if is_valid_provider_id(normalized):
            return normalized
        raise ValueError(
            "agent must be a catalog id "
            f"({', '.join(sorted(known))}) or a lowercase provider slug"
        )


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


# --- Teams (collaboration §3.2) ---------------------------------------------
#
# Roles and statuses are plain lowercase strings on the wire, matching the
# varchar+CHECK columns. No client shipped against the pre-P3 enum shape.

TeamRoleLiteral = Literal["owner", "admin", "member"]
TeamInviteRoleLiteral = Literal["admin", "member"]
TeamMemberStatusLiteral = Literal["invited", "active"]


class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Team name")


class TeamUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class TeamMemberInviteRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    role: TeamInviteRoleLiteral = "member"


class TeamMemberRoleUpdateRequest(BaseModel):
    role: TeamInviteRoleLiteral


class TeamInviteCreateRequest(BaseModel):
    role: TeamInviteRoleLiteral = "member"
    # None ⇒ never expires. Default one week, like GitHub org invites.
    expires_in_days: int | None = Field(default=7, ge=1, le=365)
    max_uses: int | None = Field(default=None, ge=1, le=1000)


class TeamSummary(BaseModel):
    id: UUID
    name: str
    # Reserved, not yet routable (D-D). Returned so a client can show it in
    # settings; nothing resolves it.
    slug: str
    avatar_image_uri: str | None = None
    role: TeamRoleLiteral
    member_count: int
    created_at: datetime
    updated_at: datetime


class TeamMemberResponse(BaseModel):
    id: UUID
    user_id: UUID | None = None
    # Shown only to team admins/owners; members see display names only.
    email: str | None = None
    display_name: str | None = None
    avatar_image_uri: str | None = None
    role: TeamRoleLiteral
    status: TeamMemberStatusLiteral
    joined_at: datetime | None = None
    created_at: datetime


class TeamDetailResponse(TeamSummary):
    members: list[TeamMemberResponse]


class TeamInviteResponse(BaseModel):
    id: UUID
    token: str
    role: TeamRoleLiteral
    expires_at: datetime | None = None
    max_uses: int | None = None
    uses: int
    created_at: datetime


class TeamInvitePreviewResponse(BaseModel):
    """What a signed-in visitor sees before redeeming a join link."""

    team_id: UUID
    name: str
    avatar_image_uri: str | None = None
    role: TeamRoleLiteral
    member_count: int


class TeamInvitationResponse(BaseModel):
    """A pending email invite addressed to the caller."""

    team_id: UUID
    name: str
    slug: str
    avatar_image_uri: str | None = None
    role: TeamRoleLiteral
    invited_by_display_name: str | None = None
    created_at: datetime


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


ProjectRoleLiteral = Literal["viewer", "commenter", "editor", "admin", "owner"]
GrantScopeLiteral = Literal["tasks", "sessions"]


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    # NULL ⇒ personal; set ⇒ team-owned (collaboration §2). Read-only here —
    # moving a project to a team is P7.
    team_id: UUID | None = None
    # The caller's standing on this project and which areas it covers
    # (collaboration §4). Owners and team members cover both scopes; a grantee
    # gets what the grant says, so a sessions-only viewer's client can hide the
    # board without a second round trip.
    #
    # Defaulted to the *least* privilege on purpose. These are authorization
    # facts about the caller, not columns on the row, so `model_validate(project)`
    # cannot supply them — and a call site that forgets must under-report (the
    # client hides an affordance the user actually has) rather than claim
    # `owner` and render buttons that 403. Build these responses with
    # `api.tasks._project_response`, which always sets both.
    role: ProjectRoleLiteral = "viewer"
    scopes: list[GrantScopeLiteral] = Field(default_factory=list)
    # Task-identifier prefix; None until the project's first task allocates one.
    key: str | None = None
    git_remote_url: str | None = None
    color: str | None = None
    icon: str | None = None
    # Served image-icon URL + who set it ('user' | 'git' | None). Clients render
    # the fallback chain icon_image_uri → emoji icon/color → generated default.
    icon_image_uri: str | None = None
    icon_source: str | None = None
    # DEPRECATED, always False. "No project" is a NULL project_id on the task
    # or session, not a project row; the field is kept one release for clients
    # that still read it.
    is_inbox: bool = False
    is_archived: bool
    archived_at: datetime | None = None
    # Newest session start in this project (recency ordering for the sidebar
    # and the new-session picker). Only the list endpoint knows it; single
    # project responses leave it None.
    last_activity_at: datetime | None = None
    # The caller's manual rank (0-based) from PUT /projects/order, None when
    # they never dragged this project into place. The list endpoint already
    # returns projects in rank order, so clients only need this to tell "has
    # a custom order" from "recency"; single project responses leave it None.
    position: int | None = None
    # Inlined rather than a separate endpoint: the lists are tiny and both the
    # Tasks page and the new-session directory resolver need them alongside the
    # project itself.
    directories: list[ProjectDirectoryResponse] = Field(default_factory=list)
    # Open tasks (not done/cancelled) filed here. Only the agent-facing list
    # (`vicoa project ls`) computes it; every other response leaves it None,
    # same convention as `last_activity_at`.
    task_count: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectSummaryResponse(BaseModel):
    """What deleting the project would file under No project."""

    task_count: int
    session_count: int
    active_session_count: int


class SetProjectDirectoryRequest(BaseModel):
    machine_id: UUID
    local_path: str = Field(..., min_length=1, max_length=4096)


class SetProjectOrderRequest(BaseModel):
    """The caller's full sidebar order, first to last. Replaces the previous
    order wholesale; an empty list resets everything to recency."""

    project_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class ProjectOrderResponse(BaseModel):
    """The order actually stored — ids the caller cannot see are dropped."""

    project_ids: list[UUID]


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
    # None = "No project" (unfiled). Same convention as a session's project_id.
    project_id: UUID | None = None
    # Denormalized like `parent_title`: a terminal listing has no sidebar to
    # translate a project_id into something a person recognises.
    project_name: str | None = None
    # Per-project sequential number and the rendered "VIC-42". Both are None for
    # an unfiled task (identifiers are project-scoped), for a task whose project
    # has no key yet (or that predates the backfill); clients must render such a
    # task without an identifier rather than inventing one.
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
    # Omitted → No project (unfiled: owned by the caller, no identifier).
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
    # NULL ⇒ personal; set ⇒ the team's vocabulary (collaboration §3.3).
    team_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class CreateTaskLabelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str
    # Create in a team's vocabulary instead of the caller's own; needs an
    # active membership of that team.
    team_id: UUID | None = None

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
    # The root this answers, or None when it is one. Threads are one level deep,
    # so this always names a root and no client walks a chain. The list arrives
    # already in thread order — each root followed by its replies.
    parent_comment_id: UUID | None = None
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
    # Reply to this comment. Threads are one level deep: passing a reply's id
    # attaches to that reply's root rather than nesting further.
    parent_comment_id: UUID | None = None


class CreateAgentTaskCommentRequest(CreateTaskCommentRequest):
    """The agent-facing body — the human one plus an authorship channel.

    An API key identifies a *user*, so a comment posted through it is the user's
    unless the caller says otherwise. `vicoa task comment` run inside a Vicoa
    session passes that session's id (it has it as `VICOA_AGENT_INSTANCE_ID`),
    and the server authors the comment as the session's agent profile — the only
    way a comment ever gets `author_type='agent'`. A session with no profile, or
    one belonging to another user, falls back to the user rather than failing:
    losing the byline is a better outcome than losing the comment.
    """

    agent_instance_id: UUID | None = None


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
    # None = "No project" (unfiled), as on TaskResponse. Required here used to
    # 500 the whole search once any unfiled task matched.
    project_id: UUID | None = None
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


# ---------------------------------------------------------------------------
# `#` references (composer) — point the current session at another Vicoa thing
#
# Deliberately NOT the search DTOs above: the palette navigates, so it ranks
# message bodies and carries snippets; `#` *attaches*, so every kind collapses
# to the same four fields the panel draws and the one `token` the message
# carries. One shape per kind would make the client branch three ways for a
# list it renders identically.
# ---------------------------------------------------------------------------

ReferenceKindLiteral = Literal["session", "task", "automation"]


class ReferenceProject(BaseModel):
    """Just enough of a project to draw its icon and name on a picker row —
    the same fields `ProjectIcon` reads on the web (generated initial-square,
    emoji, or the uploaded image behind `/api/projects/{id}/icon`)."""

    id: str
    name: str
    icon: str | None = None
    icon_image_uri: str | None = None
    updated_at: datetime | None = None


class ReferenceCandidate(BaseModel):
    kind: ReferenceKindLiteral
    id: str
    # What the panel row reads.
    label: str
    # What follows "#" in the composer: a slug, or "VIC-42" for an identified
    # task. Never contains whitespace — a token ends at the first space.
    token: str
    # Trailing text on the row's single line: the project's name when the
    # session/task/automation is filed under one, otherwise the folder it runs
    # in (and nothing at all for an unfiled task). One line per row is a
    # product decision — the panel opens over the composer, and a two-line row
    # halves how many candidates fit above the fold.
    meta: str | None = None
    # The project behind `meta`, when there is one. Present only so the row can
    # show the project's icon; `meta` already carries its name.
    project: ReferenceProject | None = None
    # Tasks only, and only when the task really has a key. Rendered after
    # `meta`, so a filed task reads "Vicoa  VIC-42".
    identifier: str | None = None
    status: str | None = None


class ReferenceCandidatesResponse(BaseModel):
    query: str
    # Kind-ordered (sessions, tasks, automations) so the client can draw a
    # group header wherever `kind` changes and still run one keyboard list.
    items: list[ReferenceCandidate]


class ReferenceDetail(BaseModel):
    kind: ReferenceKindLiteral
    id: str
    label: str
    token: str
    # The rendered block appended to the outgoing message. Fetched at pick
    # time so sending never waits on the network.
    context: str


# ============================================================================
# Share links (collaboration §3.4, P4)
# ============================================================================

ShareKindLiteral = Literal["session", "project"]
# What a project link carries. The same two words a project *grant* uses
# (`GrantScopeLiteral`), because they name the same halves of a project.
ShareScopeLiteral = Literal["tasks", "sessions"]
ShareAudienceLiteral = Literal["public", "authenticated"]


def _z(dt: datetime | None) -> str | None:
    """Legacy naive-UTC columns (agent_instances, messages) serialize with an
    explicit Z so a browser does not read them as local time."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.isoformat()
    return dt.isoformat() + "Z"


class ShareBoardFilters(BaseModel):
    """The `tasks` half of a project link's filters. Every list is optional and
    ANDed; an empty/missing list means "no narrowing on that axis"."""

    label_ids: list[UUID] | None = None
    statuses: list[TaskStatusLiteral] | None = None
    assignee_ids: list[UUID] | None = None

    model_config = ConfigDict(extra="forbid")


class ShareSessionsFilters(BaseModel):
    """The `sessions` half of a project link's filters. `statuses`, when given,
    replaces the default (everything but archived); DELETED is never visible."""

    date_from: datetime | None = None
    date_to: datetime | None = None
    machine_ids: list[UUID] | None = None
    agent_types: list[str] | None = None
    statuses: list[AgentStatus] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("statuses")
    @classmethod
    def _never_deleted(cls, v: list[AgentStatus] | None) -> list[AgentStatus] | None:
        if v is not None and AgentStatus.DELETED in v:
            raise ValueError("DELETED sessions are never shareable")
        return v


class ShareProjectFilters(BaseModel):
    """A project link's filters, one entry per scope it carries.

    Keyed by scope rather than flat, because one link can carry both halves of
    a project and "statuses" means different things to each of them.
    """

    sessions: ShareSessionsFilters | None = None
    tasks: ShareBoardFilters | None = None

    model_config = ConfigDict(extra="forbid")


def normalise_share_selection(
    *,
    kind: str,
    scopes: list[str],
    filters: dict | None,
    allow_comments: bool,
) -> tuple[list[str], dict | None]:
    """The kind-dependent half of a link's shape, shared by create and update.

    A session link carries neither scopes nor filters — the session is the
    whole subject. A project link carries at least one scope, and its filters
    are validated per scope, stored in a stable order and trimmed to the
    scopes the link actually carries. Comments live on tasks, so no link
    without that half may allow them.

    PATCH validates the *merged* shape (the stored kind, the patched fields)
    through this same function, so a link can never be edited into a state
    `POST /shares` would have refused. Raises ValueError, which reaches the
    caller as a 422 either way (a Pydantic validator on create, the explicit
    handler on update).
    """
    if kind == "session":
        if filters:
            raise ValueError("a session link has no filters")
        if scopes:
            raise ValueError("a session link has no scopes")
        scopes, filters = [], None
    else:
        # De-duplicate but keep the caller's order out of the stored value:
        # scopes are a set, and a stable order makes rows comparable.
        scopes = [s for s in ("tasks", "sessions") if s in scopes]
        if not scopes:
            raise ValueError("a project link must carry at least one scope")
        if filters is not None:
            # Validate against the per-scope schema; store the normalised
            # form, and drop the half of it the link does not carry.
            parsed = ShareProjectFilters.model_validate(filters)
            filters = {
                scope: getattr(parsed, scope).model_dump(mode="json", exclude_none=True)
                for scope in scopes
                if getattr(parsed, scope) is not None
            } or None
    if allow_comments and "tasks" not in scopes:
        raise ValueError("Comments need a link that carries tasks")
    return scopes, filters


class CreateShareLinkRequest(BaseModel):
    kind: ShareKindLiteral
    agent_instance_id: UUID | None = None
    project_id: UUID | None = None
    # What a project link carries; at least one, in any combination. A session
    # link carries none (the session is the whole subject).
    scopes: list[ShareScopeLiteral] = Field(default_factory=list)
    audience: ShareAudienceLiteral = "public"
    filters: dict | None = None
    # The one write a link can carry. Independent of `audience`: a public
    # board can take comments too — the resolver grants them to a signed-in
    # visitor only, so an anonymous reader of a public link is asked to sign
    # in first, and a comment is always attributed to a real account.
    allow_comments: bool = False
    # What the viewer page may show; both default off (see the ORM model).
    show_owner: bool = False
    show_branch: bool = False
    expires_in_days: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def _check_shape(self):
        if self.kind == "session":
            if self.agent_instance_id is None or self.project_id is not None:
                raise ValueError("kind='session' takes agent_instance_id only")
        elif self.project_id is None or self.agent_instance_id is not None:
            raise ValueError("kind='project' takes project_id only")
        self.scopes, self.filters = normalise_share_selection(  # type: ignore[assignment]
            kind=self.kind,
            scopes=list(self.scopes),
            filters=self.filters,
            allow_comments=self.allow_comments,
        )
        return self


class UpdateShareLinkRequest(BaseModel):
    """Edit a link in place, keeping its token (§3.4).

    Every field is optional and absent means "leave it alone", so a caller
    changing one switch does not have to restate the rest. What it cannot
    touch is the link's identity: the token, the kind and the target are not
    fields here, because the whole point of editing rather than re-minting is
    that a URL already sent out keeps working and keeps pointing at the same
    subject.

    Two fields carry a meaningful ``null`` — ``expires_in_days: null`` means
    "never expires" and ``filters: null`` means "no narrowing" — so the route
    reads `model_fields_set` to tell an explicit null from an omission rather
    than treating both as "unchanged".
    """

    scopes: list[ShareScopeLiteral] | None = None
    audience: ShareAudienceLiteral | None = None
    filters: dict | None = None
    allow_comments: bool | None = None
    show_owner: bool | None = None
    show_branch: bool | None = None
    expires_in_days: int | None = Field(default=None, ge=1, le=365)

    model_config = ConfigDict(extra="forbid")

    def was_set(self, field: str) -> bool:
        """Did the caller name this field at all (null included)?"""
        return field in self.model_fields_set


class ShareLinkResponse(BaseModel):
    id: UUID
    token: str
    kind: ShareKindLiteral
    agent_instance_id: UUID | None = None
    project_id: UUID | None = None
    scopes: list[ShareScopeLiteral] = Field(default_factory=list)
    audience: ShareAudienceLiteral
    filters: dict | None = None
    allow_comments: bool
    show_owner: bool
    show_branch: bool
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_accessed_at: datetime | None = None
    view_count: int
    created_at: datetime
    created_by: PrincipalResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class PublicSessionSummary(BaseModel):
    """A session as a link viewer sees it (old plan D5): transcript metadata
    plus the display subset of `session_config`. Never `home_dir`, the
    machine, or raw `instance_metadata`."""

    id: UUID
    name: str | None = None
    agent_type_name: str
    agent_profile: PrincipalResponse | None = None
    status: AgentStatus
    live_state: LiveState = LiveState.UNKNOWN
    started_at: datetime
    ended_at: datetime | None = None
    updated_at: datetime | None = None
    worktree_name: str | None = None
    # Only the display keys: agent, model, effort, permission/mode.
    session_config: dict | None = None
    message_count: int = 0
    latest_message_at: datetime | None = None

    @field_serializer("started_at", "ended_at", "updated_at", "latest_message_at")
    def _serialize_dt(self, dt: datetime | None, _info):
        return _z(dt)


class PublicMessage(BaseModel):
    id: UUID
    content: str
    sender_type: str
    # Display name only — never an email on a public surface (§10.4).
    sender_user_display_name: str | None = None
    created_at: datetime
    requires_user_input: bool
    message_metadata: dict | None = None

    @field_serializer("created_at")
    def _serialize_dt(self, dt: datetime, _info):
        return _z(dt)


class PublicMessagesPage(BaseModel):
    messages: list[PublicMessage]
    # More rows exist in the direction that was asked for (older for a
    # `before`/initial page, newer for an `after` poll).
    has_more: bool = False


class PublicProjectSummary(BaseModel):
    id: UUID
    name: str
    key: str | None = None
    color: str | None = None
    icon: str | None = None


class PublicShareResponse(BaseModel):
    """The share meta the viewer page renders first (and the OG tags)."""

    id: UUID
    kind: ShareKindLiteral
    # Which halves of the project this link carries; empty for a session link.
    # The viewer page draws its sidebar from this.
    scopes: list[ShareScopeLiteral] = Field(default_factory=list)
    audience: ShareAudienceLiteral
    # Whether THIS visitor may comment: the link allows it and they are
    # signed in. Anonymous visitors of a comments-enabled link get False
    # plus `comments_available=True`, which is the sign-in prompt.
    allow_comments: bool
    comments_available: bool
    filters: dict | None = None
    created_at: datetime
    expires_at: datetime | None = None
    # Only when the link opted in (`show_owner`); otherwise the page says
    # "shared via Vicoa" and nothing about who.
    owner: PrincipalResponse | None = None
    viewer: PrincipalResponse | None = None
    # The signed-in visitor is the link's creator — drives "Open in Vicoa"
    # deep-linking on the page without exposing the owner to anyone else.
    viewer_is_owner: bool = False
    session: PublicSessionSummary | None = None
    project: PublicProjectSummary | None = None


class PublicSessionsPage(BaseModel):
    items: list[PublicSessionSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class PublicBoardResponse(BaseModel):
    project: PublicProjectSummary
    tasks: list[TaskResponse]
    labels: list[TaskLabelResponse]
