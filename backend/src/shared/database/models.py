from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import (
    DeclarativeBase,  # type: ignore[attr-defined]
    Mapped,  # type: ignore[attr-defined]
    mapped_column,  # type: ignore[attr-defined]
    relationship,
    validates,
)

from .enums import AgentStatus, SenderType, InstanceAccessLevel, TeamRole
from .utils import is_valid_git_diff


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True
    )  # Matches Supabase auth.users.id
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Notification preferences
    push_notifications_enabled: Mapped[bool] = mapped_column(default=True)
    email_notifications_enabled: Mapped[bool] = mapped_column(default=False)
    sms_notifications_enabled: Mapped[bool] = mapped_column(default=False)
    phone_number: Mapped[str | None] = mapped_column(
        String(20), default=None
    )  # E.164 format
    notification_email: Mapped[str | None] = mapped_column(
        String(255), default=None
    )  # Defaults to email if not set

    # Relationships
    agent_instances: Mapped[list["AgentInstance"]] = relationship(
        "AgentInstance", back_populates="user"
    )
    api_keys: Mapped[list["APIKey"]] = relationship("APIKey", back_populates="user")
    user_agents: Mapped[list["UserAgent"]] = relationship(
        "UserAgent", back_populates="user"
    )
    push_tokens: Mapped[list["PushToken"]] = relationship(
        "PushToken", back_populates="user"
    )
    instance_accesses: Mapped[list["UserInstanceAccess"]] = relationship(
        "UserInstanceAccess",
        back_populates="user",
        foreign_keys="UserInstanceAccess.user_id",
    )
    team_memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership",
        back_populates="user",
        foreign_keys="TeamMembership.user_id",
    )

    # NOTE: ``User.subscription`` / ``User.billing_events`` are attached at
    # import time by the closed billing overlay (``cloud.billing.models`` via
    # ``backref``) when it is present. The open core declares no billing
    # relationships — see plans/todos/oss-cut-manifest.md (A4 weld #2).


class UserAgent(Base):
    __tablename__ = "user_agents"
    __table_args__ = (
        # Partial unique index: only enforce uniqueness for non-deleted agents
        Index(
            "uq_user_agents_user_id_name",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = FALSE"),
        ),
        Index("ix_user_agents_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    name: Mapped[str] = mapped_column(String(255))
    webhook_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    webhook_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    is_deleted: Mapped[bool] = mapped_column(default=False)  # Soft delete flag
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_agents")
    instances: Mapped[list["AgentInstance"]] = relationship(
        "AgentInstance", back_populates="user_agent"
    )


class AgentInstance(Base):
    __tablename__ = "agent_instances"
    __table_args__ = (
        Index("idx_agent_instances_user_agent_id", "user_agent_id"),
        Index("idx_agent_instances_user_status", "user_id", "status"),
        Index("ix_agent_instances_user_updated", "user_id", "updated_at"),
        Index("ix_agent_instances_machine_id", "machine_id"),
        Index("ix_agent_instances_task", "task_id"),
        # Partial index so the rate-limit sweep/filter only ever scans the
        # currently-blocked rows (typically a handful) instead of the table.
        Index(
            "ix_agent_instances_rate_limited_until",
            "rate_limited_until",
            postgresql_where=text("rate_limited_until IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_agents.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    status: Mapped[AgentStatus] = mapped_column(default=AgentStatus.ACTIVE)
    started_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(default=None)
    git_diff: Mapped[str | None] = mapped_column(Text, default=None)
    name: Mapped[str | None] = mapped_column(String(255), default=None)
    pinned_at: Mapped[datetime | None] = mapped_column(default=None)
    # Project identifier - can be a local directory path or remote git repository URL
    # Currently used for directory paths, but designed to support git repos in the future
    project: Mapped[str | None] = mapped_column(Text, default=None)
    # Home directory path for expanding tilde (~) in project paths
    home_dir: Mapped[str | None] = mapped_column(Text, default=None)
    # Machine this session was spawned on (machine-management D7). SET NULL so
    # removing a machine degrades its sessions to "machine removed" rather than
    # cascading the delete. Stamped at registration from the daemon state file.
    machine_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("machines.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    # Backpointer to the task this run works on (tasks-and-projects plan §2).
    # use_alter because tasks is defined in task_models.py and created after
    # this table; SET NULL so deleting a task degrades its runs, not deletes.
    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "tasks.id",
            use_alter=True,
            name="fk_agent_instances_task_id",
            ondelete="SET NULL",
        ),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    # Server-projected from instance_metadata.usage on each usage PATCH: the
    # binding reset instant across maxed time-window rate limits, or NULL when
    # not blocked. Deliberately a nullable timestamp rather than an AgentStatus
    # value — rate-limit is an orthogonal, transient, auto-recovering axis that
    # must not overwrite the idle/active lifecycle. Set and cleared by the same
    # projection (usage back under 100% -> NULL). See
    # plans/todos/auto-continue-rate-limited-sessions.md.
    rate_limited_until: Mapped[datetime | None] = mapped_column(default=None)
    instance_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    # User-visible spawn-time configuration (agent, model, effort, permission/mode).
    # Mirrors SessionConfig.toJson() in mobile. Kept separate from
    # instance_metadata (operational state) so display-only config has its own
    # surface. See plans/session-config-storage.md §3.1.
    session_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    last_read_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "messages.id",
            use_alter=True,
            name="fk_agent_instances_last_read_message",
            ondelete="SET NULL",
        ),
        type_=PostgresUUID(as_uuid=True),
        default=None,
    )
    # Monotonic last-modified marker for WebSocket catch-up watermarks and the
    # mutable-entity merge rule (websocket-migration plan §2.6).
    # server_default lets the DB fill the column when an older code revision
    # (whose model lacks this field) inserts a row during a deploy gap.
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    # Relationships
    user_agent: Mapped["UserAgent"] = relationship(
        "UserAgent", back_populates="instances"
    )
    user: Mapped["User"] = relationship("User", back_populates="agent_instances")
    # Host this session runs on. Read-only here — it exists so derived liveness
    # can compare the machine's heartbeat against the instance's without a
    # second round trip. List queries should joinedload it (see
    # shared/database/liveness.py).
    machine: Mapped["Machine | None"] = relationship("Machine", viewonly=True)
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="instance",
        order_by="Message.created_at",
        foreign_keys="Message.agent_instance_id",
    )
    last_read_message: Mapped["Message | None"] = relationship(
        "Message",
        foreign_keys=[last_read_message_id],
        post_update=True,
        passive_deletes=True,
    )
    user_instance_accesses: Mapped[list["UserInstanceAccess"]] = relationship(
        "UserInstanceAccess", back_populates="agent_instance"
    )
    team_instance_accesses: Mapped[list["TeamInstanceAccess"]] = relationship(
        "TeamInstanceAccess", back_populates="agent_instance"
    )

    @validates("git_diff")
    def validate_git_diff(self, key, value):
        """Validate git diff at the database level.

        Raises ValueError if the git diff is invalid.
        """
        if value is None or value == "":
            return value

        if not is_valid_git_diff(value):
            raise ValueError("Invalid git diff format. Must be a valid unified diff.")

        return value


class APIKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        # Every agent request looks its key up by hash to honour revocation
        # (shared/auth/agent_tokens.py) — the hottest lookup on that server.
        Index("ix_api_keys_api_key_hash", "api_key_hash"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    name: Mapped[str] = mapped_column(String(255))
    api_key_hash: Mapped[str] = mapped_column(String(128))
    api_key: Mapped[str] = mapped_column(
        Text
    )  # Store the actual JWT for user viewing, not good for security
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")


class PushToken(Base):
    __tablename__ = "push_tokens"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    token: Mapped[str] = mapped_column(String(255), unique=True)
    platform: Mapped[str] = mapped_column(String(50))  # 'ios' or 'android'
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="push_tokens")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_instance_created", "agent_instance_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    agent_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    sender_type: Mapped[SenderType] = mapped_column()
    sender_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    requires_user_input: Mapped[bool] = mapped_column(default=False)
    message_metadata: Mapped[dict | None] = mapped_column(JSONB, default=None)

    # Relationships
    instance: Mapped["AgentInstance"] = relationship(
        "AgentInstance",
        back_populates="messages",
        foreign_keys=[agent_instance_id],
    )
    sender_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[sender_user_id]
    )


class MessageAttachment(Base):
    """An uploaded file (image or otherwise) bound to a chat message.

    Rows are created at upload time with ``message_id`` NULL and bound to a
    message when the user sends it; never-sent uploads stay unbound (cleanup
    is a follow-up). The bytes live in S3 at ``s3_key``; a denormalized
    copy of the display fields is stamped into the message's
    ``message_metadata["attachments"]`` so realtime/history payloads carry it
    without joining this table.
    """

    __tablename__ = "message_attachments"
    __table_args__ = (
        Index("idx_message_attachments_message", "message_id"),
        Index("idx_message_attachments_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    agent_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    s3_key: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column()
    # Pixel dimensions are populated for images only; general files leave them
    # NULL (they have no meaningful width/height).
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    original_filename: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )


class UserInstanceAccess(Base):
    __tablename__ = "user_instance_access"
    __table_args__ = (
        Index("ix_user_instance_access_instance", "agent_instance_id"),
        Index(
            "uq_user_instance_access_instance_email",
            "agent_instance_id",
            "shared_email",
            unique=True,
        ),
        Index(
            "uq_user_instance_access_instance_user",
            "agent_instance_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    agent_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    shared_email: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    access: Mapped[InstanceAccessLevel] = mapped_column()
    granted_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent_instance: Mapped["AgentInstance"] = relationship(
        "AgentInstance", back_populates="user_instance_accesses"
    )
    user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="instance_accesses",
    )
    granted_by_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[granted_by_user_id],
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    instance_accesses: Mapped[list["TeamInstanceAccess"]] = relationship(
        "TeamInstanceAccess",
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        Index("ix_team_memberships_team_id", "team_id"),
        Index(
            "uq_team_memberships_team_user",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_team_memberships_team_email",
            "team_id",
            "invited_email",
            unique=True,
            postgresql_where=text("invited_email IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    invited_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[TeamRole] = mapped_column(default=TeamRole.MEMBER)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    team: Mapped["Team"] = relationship("Team", back_populates="memberships")
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="team_memberships",
        foreign_keys=[user_id],
    )


class TeamInstanceAccess(Base):
    __tablename__ = "team_instance_access"
    __table_args__ = (
        Index("ix_team_instance_access_team_id", "team_id"),
        Index(
            "uq_team_instance_access_team_instance",
            "team_id",
            "agent_instance_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    agent_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    access: Mapped[InstanceAccessLevel] = mapped_column()
    granted_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    team: Mapped["Team"] = relationship("Team", back_populates="instance_accesses")
    agent_instance: Mapped["AgentInstance"] = relationship(
        "AgentInstance", back_populates="team_instance_accesses"
    )
    granted_by_user: Mapped["User"] = relationship(
        "User", foreign_keys=[granted_by_user_id]
    )


class Machine(Base):
    __tablename__ = "machines"
    __table_args__ = (
        Index("ix_machines_user_id", "user_id"),
        Index("ix_machines_user_updated", "user_id", "updated_at"),
        # One machine row per (user, physical host). Partial so legacy rows
        # with a NULL hardware_id are exempt. Backs the register dedup that
        # keeps machine identity stable across re-auth / key rotation.
        Index(
            "uq_machines_user_hardware",
            "user_id",
            "hardware_id",
            unique=True,
            postgresql_where=text("hardware_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
    hostname: Mapped[str | None] = mapped_column(String(255), default=None)
    platform: Mapped[str | None] = mapped_column(String(255), default=None)
    home_dir: Mapped[str | None] = mapped_column(String(1024), default=None)
    # Stable per-host token (SHA-256 of the OS hardware id) the CLI sends on
    # register. Scoped by user_id via the partial unique index below, it is the
    # identity anchor that survives re-auth / key rotation (which change the
    # client-derived machine_id). Nullable: legacy daemons and hosts with no
    # readable hardware id omit it, and the endpoint falls back to machine_id.
    hardware_id: Mapped[str | None] = mapped_column(String(64), default=None)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    machine_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, default=None
    )

    # passive_deletes lets the DB-level ON DELETE CASCADE remove spawn_requests
    # when a machine is hard-deleted (machine-management D6), instead of
    # SQLAlchemy trying to NULL their non-nullable machine_id.
    spawn_requests: Mapped[list["MachineSpawnRequest"]] = relationship(
        "MachineSpawnRequest", back_populates="machine", passive_deletes=True
    )


class MachineSpawnRequest(Base):
    __tablename__ = "machine_spawn_requests"
    __table_args__ = (
        Index("ix_spawn_requests_machine_status", "machine_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    machine_id: Mapped[UUID] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), type_=PostgresUUID(as_uuid=True)
    )
    directory: Mapped[str] = mapped_column(Text)
    agent: Mapped[str] = mapped_column(String(64), default="claude")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    message: Mapped[str | None] = mapped_column(Text, default=None)
    agent_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_instances.id", ondelete="SET NULL"),
        type_=PostgresUUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    claimed_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    request_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, default=None
    )

    machine: Mapped[Machine] = relationship("Machine", back_populates="spawn_requests")
    agent_instance: Mapped[AgentInstance | None] = relationship(
        "AgentInstance", foreign_keys=[agent_instance_id]
    )


class MachineAgentModels(Base):
    """Per-machine, per-agent cache of an ACP agent's available model list.

    Written write-on-change from the ``available_models`` a headless wrapper
    reports onto ``agent_instances.session_config`` on session/new (see
    ``update_agent_instance_endpoint``). Lets the new-session picker show a
    machine's REAL model list before a session is started — the catalog only
    ships static defaults, and the live list is account/version/config-specific.
    """

    __tablename__ = "machine_agent_models"
    __table_args__ = (Index("ix_machine_agent_models_user", "user_id"),)

    machine_id: Mapped[UUID] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    # Catalog agent id: 'cursor' | 'gemini' | 'copilot' | 'kimi' | 'opencode' ...
    agent_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
    )
    # [{"id": ..., "label": ...}] exactly as the agent's ACP session reported.
    models: Mapped[list] = mapped_column(JSONB)
    # sha256 of the normalized model list — gates write-on-change.
    models_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SlashCommands(Base):
    __tablename__ = "slash_commands"
    __table_args__ = (Index("ix_slash_commands_user_agent", "user_id", "agent_type"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    agent_type: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )  # 'claude' or 'codex'
    commands: Mapped[dict] = mapped_column(
        JSONB
    )  # {"cmd-name": {"description": "..."}}
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    user: Mapped["User"] = relationship("User")


class FileMentions(Base):
    __tablename__ = "file_mentions"
    __table_args__ = (
        Index("ix_file_mentions_user_project", "user_id", "project_path"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        type_=PostgresUUID(as_uuid=True),
        primary_key=True,
    )
    project_path: Mapped[str] = mapped_column(
        String(500), primary_key=True
    )  # Absolute path to project directory
    files: Mapped[list] = mapped_column(
        JSONB
    )  # Array of relative file paths: ["src/main.py", "README.md", ...]
    file_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    user: Mapped["User"] = relationship("User")
