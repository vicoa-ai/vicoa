import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from shared.database import (
    AgentInstance,
    AgentStatus,
    UserInstanceAccess,
    APIKey,
    Message,
    MessageAttachment,
    PushToken,
    Team,
    TeamInstanceAccess,
    TeamMembership,
    User,
    UserAgent,
    InstanceAccessLevel,
    TeamRole,
    SenderType,
)
from shared.database.liveness import LiveState, compute_live_state, is_fresh
from shared.database.automation_models import AutomationRun
from shared.hooks import run_user_delete_hooks
from sqlalchemy import case, cast, desc, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, joinedload, subqueryload, aliased, selectinload

# Import Pydantic models for type-safe returns
from backend.models import (
    AgentInstanceResponse,
    AgentInstanceDetail,
    AgentTypeOverview,
    MessageResponse,
    TeamSummary,
    TeamDetailResponse,
    TeamMemberResponse,
    InstanceShareResponse,
)


ACCESS_PRIORITY = {
    InstanceAccessLevel.READ: 1,
    InstanceAccessLevel.WRITE: 2,
}


def _normalize_email(email: str) -> str:
    """Normalize email for case-insensitive comparisons while preserving original casing elsewhere."""
    return email.strip().lower()


def _message_to_response(msg: Message) -> MessageResponse:
    sender = msg.sender_user
    return MessageResponse(
        id=str(msg.id),
        content=msg.content,
        sender_type=msg.sender_type.value,
        sender_user_id=str(msg.sender_user_id) if msg.sender_user_id else None,
        sender_user_email=sender.email if sender else None,
        sender_user_display_name=sender.display_name if sender else None,
        created_at=msg.created_at,
        requires_user_input=msg.requires_user_input,
        message_metadata=msg.message_metadata,
    )


def _team_member_to_response(member: TeamMembership) -> TeamMemberResponse:
    user = member.user
    email = user.email if user else member.invited_email or ""
    display_name = user.display_name if user else None
    return TeamMemberResponse(
        id=str(member.id),
        role=member.role,
        user_id=str(member.user_id) if member.user_id else None,
        email=email,
        display_name=display_name,
        invited=member.user_id is None,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


def _instance_access_to_response(
    access_obj: UserInstanceAccess, *, is_owner: bool = False
) -> InstanceShareResponse:
    user = access_obj.user
    return InstanceShareResponse(
        id=str(access_obj.id),
        email=access_obj.shared_email,
        access=access_obj.access,
        user_id=str(access_obj.user_id) if access_obj.user_id else None,
        display_name=user.display_name if user else None,
        invited=access_obj.user_id is None,
        is_owner=is_owner,
        created_at=access_obj.created_at,
        updated_at=access_obj.updated_at,
    )


def _instance_owner_share_response(instance: AgentInstance) -> InstanceShareResponse:
    owner_user = instance.user
    email = owner_user.email if owner_user else ""
    display_name = owner_user.display_name if owner_user else None
    created_at = (
        instance.started_at if instance.started_at else datetime.now(timezone.utc)
    )
    return InstanceShareResponse(
        id=str(instance.id),
        email=email,
        access=InstanceAccessLevel.WRITE,
        user_id=str(instance.user_id),
        display_name=display_name,
        invited=False,
        is_owner=True,
        created_at=created_at,
        updated_at=created_at,
    )


def _get_team_membership(
    db: Session, team_id: UUID, user_id: UUID
) -> TeamMembership | None:
    return (
        db.query(TeamMembership)
        .options(joinedload(TeamMembership.user))
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        .first()
    )


def _get_team(db: Session, team_id: UUID) -> Team | None:
    return db.query(Team).filter(Team.id == team_id).first()


def _get_user_by_email(db: Session, email: str) -> User | None:
    normalized = _normalize_email(email)
    return db.query(User).filter(func.lower(User.email) == normalized).first()


def _compute_effective_instance_access(
    db: Session, instance: AgentInstance, user_id: UUID
) -> InstanceAccessLevel | None:
    if instance.user_id == user_id:
        return InstanceAccessLevel.WRITE

    access_levels: list[InstanceAccessLevel] = []

    direct_access = (
        db.query(UserInstanceAccess.access)
        .filter(
            UserInstanceAccess.agent_instance_id == instance.id,
            UserInstanceAccess.user_id == user_id,
        )
        .first()
    )
    if direct_access and direct_access.access:
        access_levels.append(direct_access.access)

    team_access_rows = (
        db.query(TeamInstanceAccess.access)
        .join(TeamMembership, TeamMembership.team_id == TeamInstanceAccess.team_id)
        .filter(
            TeamInstanceAccess.agent_instance_id == instance.id,
            TeamMembership.user_id == user_id,
        )
        .all()
    )
    for row in team_access_rows:
        if row.access:
            access_levels.append(row.access)

    if not access_levels:
        return None

    return max(access_levels, key=lambda level: ACCESS_PRIORITY[level])


def get_instance_and_access(
    db: Session, instance_id: UUID, user_id: UUID
) -> tuple[AgentInstance | None, InstanceAccessLevel | None]:
    instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()
    if not instance:
        return None, None

    access = _compute_effective_instance_access(db, instance, user_id)
    return instance, access


def _require_instance_access(
    db: Session,
    instance_id: UUID,
    user_id: UUID,
    required: InstanceAccessLevel,
) -> tuple[AgentInstance | None, InstanceAccessLevel | None]:
    instance, access = get_instance_and_access(db, instance_id, user_id)
    if not instance:
        return None, None

    if access is None or ACCESS_PRIORITY[access] < ACCESS_PRIORITY[required]:
        return None, None

    return instance, access


def _get_instance_message_stats(db: Session, instance_ids: list[UUID]) -> dict:
    """
    Efficiently get message statistics for multiple instances.
    Returns a dict mapping instance_id to (latest_message, latest_message_at, message_count)
    """
    if not instance_ids:
        return {}

    # Use a single query with window functions to get both count and latest message
    subquery = (
        db.query(
            Message.agent_instance_id,
            Message.content,
            Message.created_at,
            func.row_number()
            .over(
                partition_by=Message.agent_instance_id,
                order_by=desc(Message.created_at),
            )
            .label("rn"),
            func.count(Message.id)
            .over(partition_by=Message.agent_instance_id)
            .label("msg_count"),
        )
        .filter(Message.agent_instance_id.in_(instance_ids))
        .subquery()
    )

    # Get only the latest message (rn=1) with the count
    results = (
        db.query(
            subquery.c.agent_instance_id,
            subquery.c.content,
            subquery.c.created_at,
            subquery.c.msg_count,
        )
        .filter(subquery.c.rn == 1)
        .all()
    )

    # Convert to dict for easy lookup
    stats = {}
    for row in results:
        stats[row.agent_instance_id] = {
            "latest_message": row.content,
            "latest_message_at": row.created_at,
            "message_count": row.msg_count,
        }

    return stats


def format_agent_instance(
    instance: AgentInstance, message_stats: dict | None = None
) -> AgentInstanceResponse:
    """
    Helper function to format an agent instance consistently.

    Args:
        instance: The AgentInstance to format
        message_stats: Optional pre-computed message statistics mapping instance_id to
            metadata with 'latest_message', 'latest_message_at', and 'message_count'.
    """
    # Get stats for this instance, defaulting to empty values if not found
    stats_map = message_stats or {}
    stats = stats_map.get(instance.id, {})
    latest_message = stats.get("latest_message")
    latest_message_at = stats.get("latest_message_at")
    chat_length = stats.get("message_count", 0)

    metadata = (
        dict(instance.instance_metadata)
        if isinstance(instance.instance_metadata, dict)
        else None
    )

    session_config = (
        dict(instance.session_config)
        if isinstance(instance.session_config, dict)
        else None
    )

    payload = {
        "instance_metadata": metadata,
        "session_config": session_config,
        "id": str(instance.id),
        "agent_type_id": str(instance.user_agent_id) if instance.user_agent_id else "",
        "agent_type_name": instance.user_agent.name
        if instance.user_agent
        else "Unknown",
        "name": instance.name,
        "status": instance.status,
        "started_at": instance.started_at,
        "ended_at": instance.ended_at,
        "latest_message": latest_message,
        "latest_message_at": latest_message_at,
        "chat_length": chat_length,
        "last_heartbeat_at": instance.last_heartbeat_at,
        "project": instance.project,
        "home_dir": instance.home_dir,
        "machine_id": str(instance.machine_id) if instance.machine_id else None,
        "pinned_at": instance.pinned_at,
        "live_state": _live_state_for(instance),
        "rate_limited": instance.rate_limited_until is not None,
        "rate_limit_resets_at": instance.rate_limited_until,
    }

    return AgentInstanceResponse.model_validate(payload)


def _live_state_for(instance: AgentInstance) -> LiveState:
    """Derived liveness for an instance, tolerant of an unloaded machine.

    ``instance.machine`` is a viewonly relationship; list queries joinedload it,
    but if a caller hasn't, fall back to agent-heartbeat-only rather than
    reporting a false "machine offline".
    """
    machine_heartbeat = None
    if instance.machine_id is not None:
        machine = getattr(instance, "machine", None)
        machine_heartbeat = getattr(machine, "last_heartbeat_at", None)

    return compute_live_state(
        status=instance.status,
        instance_last_heartbeat_at=instance.last_heartbeat_at,
        machine_id=instance.machine_id,
        machine_last_heartbeat_at=machine_heartbeat,
        started_at=instance.started_at,
    )


def get_all_agent_types_with_instances(
    db: Session, user_id: UUID
) -> list[AgentTypeOverview]:
    """Get all non-deleted user agents with their instances for a specific user - OPTIMIZED"""
    # Get all non-deleted user agents for this user with instances in a single query
    user_agents = (
        db.query(UserAgent)
        .filter(UserAgent.user_id == user_id, UserAgent.is_deleted.is_(False))
        .options(subqueryload(UserAgent.instances))
        .all()
    )

    # Collect all instance IDs for bulk message stats query (excluding DELETED)
    all_instance_ids = []
    for user_agent in user_agents:
        for instance in user_agent.instances:
            if instance.status != AgentStatus.DELETED:
                all_instance_ids.append(instance.id)

    # Get message stats for ALL instances in a simpler, more efficient query
    message_stats = {}
    if all_instance_ids:
        # Use window functions to get both count and latest message in one query
        # This leverages our new index on (agent_instance_id, created_at)

        # Subquery with row_number to identify the latest message per instance
        latest_msg_cte = (
            db.query(
                Message.agent_instance_id,
                Message.content,
                Message.created_at,
                func.row_number()
                .over(
                    partition_by=Message.agent_instance_id,
                    order_by=desc(Message.created_at),
                )
                .label("rn"),
                func.count(Message.id)
                .over(partition_by=Message.agent_instance_id)
                .label("msg_count"),
            )
            .filter(Message.agent_instance_id.in_(all_instance_ids))
            .subquery()
        )

        # Get only the latest message (rn=1) with counts
        stats_results = (
            db.query(
                latest_msg_cte.c.agent_instance_id,
                latest_msg_cte.c.content,
                latest_msg_cte.c.created_at,
                latest_msg_cte.c.msg_count,
            )
            .filter(latest_msg_cte.c.rn == 1)
            .all()
        )

        for row in stats_results:
            message_stats[row.agent_instance_id] = {
                "count": row.msg_count or 0,
                "latest_at": row.created_at,
                "latest_content": row.content,
            }

    result = []
    for user_agent in user_agents:
        # Filter out DELETED instances
        instances = [i for i in user_agent.instances if i.status != AgentStatus.DELETED]

        # Create a list of instances with their stats
        instances_with_stats = []
        for instance in instances:
            stats = message_stats.get(instance.id, {})
            instances_with_stats.append(
                {
                    "instance": instance,
                    "message_count": stats.get("count", 0),
                    "latest_message_at": stats.get("latest_at"),
                    "latest_message": stats.get("latest_content"),
                }
            )

        # Sort instances: AWAITING_INPUT instances first, then by most recent activity
        def sort_key(item):
            instance = item["instance"]
            latest_at = item["latest_message_at"]

            # If instance is awaiting input, prioritize it
            if instance.status == AgentStatus.AWAITING_INPUT:
                # Sort by when the question was asked (last message time)
                if latest_at:
                    return (0, latest_at)
                else:
                    return (0, instance.started_at)

            # Otherwise sort by last activity
            last_activity = latest_at if latest_at else instance.started_at
            return (1, -last_activity.timestamp())

        sorted_items = sorted(instances_with_stats, key=sort_key)

        # Format instances with optimized data
        formatted_instances = []
        for item in sorted_items:
            instance = item["instance"]
            metadata = (
                instance.instance_metadata
                if isinstance(instance.instance_metadata, dict)
                else {}
            )
            session_config = (
                dict(instance.session_config)
                if isinstance(instance.session_config, dict)
                else None
            )
            payload = {
                "instance_metadata": metadata,
                "session_config": session_config,
                "id": str(instance.id),
                "agent_type_id": str(instance.user_agent_id)
                if instance.user_agent_id
                else "",
                "agent_type_name": instance.user_agent.name
                if instance.user_agent
                else "Unknown",
                "name": instance.name,
                "status": instance.status,
                "started_at": instance.started_at,
                "ended_at": instance.ended_at,
                "latest_message": item["latest_message"],
                "latest_message_at": item["latest_message_at"],
                "chat_length": item["message_count"],
                "last_heartbeat_at": instance.last_heartbeat_at,
                "project": instance.project,
                "machine_id": str(instance.machine_id) if instance.machine_id else None,
            }
            formatted_instances.append(AgentInstanceResponse.model_validate(payload))

        result.append(
            AgentTypeOverview(
                id=str(user_agent.id),
                name=user_agent.name,
                created_at=user_agent.created_at,
                recent_instances=formatted_instances,
                total_instances=len(instances),
                active_instances=sum(
                    1 for i in instances if i.status == AgentStatus.ACTIVE
                ),
            )
        )

    shared_instances, _ = get_all_agent_instances(db, user_id, scope="shared")
    if shared_instances:

        def shared_sort_key(inst: AgentInstanceResponse):
            latest = inst.latest_message_at or inst.started_at
            timestamp = latest.timestamp() if latest else 0
            priority = 0 if inst.status == AgentStatus.AWAITING_INPUT else 1
            return (priority, -timestamp)

        sorted_shared = sorted(shared_instances, key=shared_sort_key)
        total_shared = len(sorted_shared)
        active_shared = sum(
            1 for inst in sorted_shared if inst.status == AgentStatus.ACTIVE
        )

        result.append(
            AgentTypeOverview(
                id="shared-with-me",
                name="Shared with me",
                created_at=datetime.now(timezone.utc),
                recent_instances=sorted_shared,
                total_instances=total_shared,
                active_instances=active_shared,
            )
        )

    return result


CLOSED_STATUSES = frozenset(
    {
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
        AgentStatus.KILLED,
        AgentStatus.DISCONNECTED,
    }
)

# How long past its reset a rate-limited row keeps surfacing to the sweep. The
# projection only advances when new usage arrives, so a session that gets
# limited and then dies (machine offline forever) would otherwise keep a stale
# non-null rate_limited_until and be retried indefinitely. Beyond this age we
# assume it won't recover on its own and drop it from `?rate_limited_only=true`.
# (Belt to the §3 reaper's suspenders — the row still clears if the session ever
# PATCHes fresh under-limit usage.)
_RATE_LIMIT_MAX_AGE = timedelta(hours=24)


def get_all_agent_instances(
    db: Session,
    user_id: UUID,
    limit: int | None = None,
    offset: int = 0,
    scope: str = "me",
    active_only: bool = False,
    rate_limited_only: bool = False,
    caller_instance_id: UUID | str | None = None,
) -> tuple[list[AgentInstanceResponse], int]:
    """Get agent instances for a user based on requested visibility scope.

    ``rate_limited_only`` narrows to sessions currently blocked by a time-window
    rate limit (``rate_limited_until IS NOT NULL``), bounded to the recent past
    by ``_RATE_LIMIT_MAX_AGE`` so a permanently-dead session isn't retried
    forever. Uses the partial index on ``rate_limited_until``.

    ``caller_instance_id`` is the session the request originates from (the CLI
    fills it from ``VICOA_AGENT_INSTANCE_ID`` when it runs inside an agent). If
    that caller is itself an automation-spawned session, the sweep drops *that
    automation's own* sessions — so the auto-continue automation can't
    flag-and-continue its own runs — while leaving other automations' and users'
    rate-limited sessions visible (and continuable). A human/manual caller (no
    id, or an id not tied to an automation) sees everything.
    """

    scope = (scope or "me").lower()
    if scope not in {"me", "shared", "all"}:
        raise ValueError(f"Invalid agent instance scope: {scope}")

    query = (
        db.query(AgentInstance)
        .filter(AgentInstance.status != AgentStatus.DELETED)
        .options(
            joinedload(AgentInstance.user_agent),
            # Derived live_state compares against the machine heartbeat; without
            # this the list would fire one extra query per row.
            joinedload(AgentInstance.machine),
        )
        .order_by(desc(AgentInstance.started_at))
    )

    if active_only:
        query = query.filter(AgentInstance.status.notin_(CLOSED_STATUSES))

    if rate_limited_only:
        cutoff = datetime.now(timezone.utc) - _RATE_LIMIT_MAX_AGE
        query = query.filter(
            AgentInstance.rate_limited_until.isnot(None),
            AgentInstance.rate_limited_until >= cutoff,
        )
        # Self-exclusion: if the caller is itself an automation-spawned session,
        # drop *that automation's own* sessions. The auto-continue automation is
        # a plain spawn automation on the same account, so a run that fires while
        # limited flags its OWN session — which the next run would then continue,
        # a self-reference loop that fans out and burns budget. Scoping to the
        # caller's automation keeps OTHER automations' rate-limited runs (and
        # users' sessions) visible so they can still be continued.
        caller_uuid: UUID | None = None
        if caller_instance_id:
            try:
                caller_uuid = UUID(str(caller_instance_id))
            except (ValueError, TypeError):
                caller_uuid = None
        caller_automation_id = None
        if caller_uuid is not None:
            # One indexed lookup (ix_automation_runs_agent_instance).
            caller_automation_id = (
                db.query(AutomationRun.automation_id)
                .filter(AutomationRun.agent_instance_id == caller_uuid)
                .limit(1)
                .scalar()
            )
        if caller_automation_id is not None:
            own_automation_session = (
                exists()
                .where(AutomationRun.agent_instance_id == AgentInstance.id)
                .where(AutomationRun.automation_id == caller_automation_id)
            )
            query = query.filter(~own_automation_session)

    if scope == "me":
        query = query.filter(AgentInstance.user_id == user_id)
    else:
        direct_access_select = select(UserInstanceAccess.agent_instance_id).where(
            UserInstanceAccess.user_id == user_id
        )
        team_access_select = (
            select(TeamInstanceAccess.agent_instance_id)
            .select_from(TeamInstanceAccess)
            .join(
                TeamMembership,
                TeamMembership.team_id == TeamInstanceAccess.team_id,
            )
            .where(TeamMembership.user_id == user_id)
        )
        shared_instances_select = direct_access_select.union(team_access_select)

        if scope == "shared":
            query = query.filter(
                AgentInstance.user_id != user_id,
                AgentInstance.id.in_(shared_instances_select),
            )
        else:  # scope == "all"
            query = query.filter(
                or_(
                    AgentInstance.user_id == user_id,
                    AgentInstance.id.in_(shared_instances_select),
                )
            )

    total = query.order_by(None).count()

    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    instances = query.all()

    # Get all instance IDs for bulk message stats query
    instance_ids = [instance.id for instance in instances]

    # Get message stats for all instances in one efficient query
    message_stats = _get_instance_message_stats(db, instance_ids)

    # Format instances using helper function with pre-computed stats
    return [
        format_agent_instance(instance, message_stats) for instance in instances
    ], total


def get_user_activity(
    db: Session, user_id: UUID, since: datetime | None = None
) -> dict:
    """Aggregate the user's activity for the profile page.

    Returns ``{daily, total_user_messages, total_messages, total_sessions}``
    scoped to the user's own sessions:
    - ``daily``: UTC ``YYYY-MM-DD`` -> count of user-sent messages that day
      (drives the heatmap/streak). ``since`` (a naive UTC datetime) limits it to
      that day onward for incremental sync.
    - ``total_user_messages`` / ``total_messages``: all-time user-sent vs. all
      (user + agent) message counts, from one grouped pass.
    - ``total_sessions``: all-time session count.

    ``Message.created_at`` is a naive-UTC column, so days are bucketed with
    ``to_char`` directly.
    """
    day_expr = func.to_char(Message.created_at, "YYYY-MM-DD")
    daily_query = (
        db.query(day_expr.label("day"), func.count(Message.id).label("n"))
        .select_from(Message)
        .join(AgentInstance, Message.agent_instance_id == AgentInstance.id)
        .filter(
            AgentInstance.user_id == user_id,
            Message.sender_type == SenderType.USER,
        )
    )
    if since is not None:
        daily_query = daily_query.filter(Message.created_at >= since)
    daily = {row.day: int(row.n) for row in daily_query.group_by(day_expr).all()}

    counts_by_sender = (
        db.query(Message.sender_type, func.count(Message.id))
        .select_from(Message)
        .join(AgentInstance, Message.agent_instance_id == AgentInstance.id)
        .filter(AgentInstance.user_id == user_id)
        .group_by(Message.sender_type)
        .all()
    )
    by_sender = {sender: int(n) for sender, n in counts_by_sender}
    total_user_messages = by_sender.get(SenderType.USER, 0)
    total_messages = sum(by_sender.values())

    total_sessions = (
        db.query(func.count(AgentInstance.id))
        .filter(AgentInstance.user_id == user_id)
        .scalar()
    )

    return {
        "daily": daily,
        "total_user_messages": total_user_messages,
        "total_messages": total_messages,
        "total_sessions": int(total_sessions or 0),
    }


def get_agent_summary(db: Session, user_id: UUID) -> dict:
    """Get lightweight summary of agent counts without fetching detailed instance data"""

    # Single query to get all counts using conditional aggregation (excluding DELETED)
    stats = (
        db.query(
            func.count(AgentInstance.id).label("total"),
            func.count(case((AgentInstance.status == AgentStatus.ACTIVE, 1))).label(
                "active"
            ),
            func.count(case((AgentInstance.status == AgentStatus.COMPLETED, 1))).label(
                "completed"
            ),
        )
        .filter(
            AgentInstance.user_id == user_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .first()
    )

    # Handle the case where stats might be None (though COUNT queries always return a row)
    if stats:
        total_instances = stats.total or 0
        active_instances = stats.active or 0
        completed_instances = stats.completed or 0
    else:
        total_instances = 0
        active_instances = 0
        completed_instances = 0

    # Count by user agent and status (for fleet overview, excluding DELETED)
    # Get instances with their user agents
    agent_type_stats = (
        db.query(
            UserAgent.id,
            UserAgent.name,
            AgentInstance.status,
            func.count(AgentInstance.id).label("count"),
        )
        .join(AgentInstance, AgentInstance.user_agent_id == UserAgent.id)
        .filter(
            UserAgent.user_id == user_id,
            UserAgent.is_deleted.is_(False),
            AgentInstance.status != AgentStatus.DELETED,
        )
        .group_by(UserAgent.id, UserAgent.name, AgentInstance.status)
        .all()
    )

    # Format agent type stats
    agent_types_summary = {}
    for type_id, type_name, status, count in agent_type_stats:
        # Agent types are now stored in lowercase, so no normalization needed
        if type_name not in agent_types_summary:
            agent_types_summary[type_name] = {
                "id": str(type_id),
                "name": type_name,
                "total_instances": 0,
                "active_instances": 0,
            }

        agent_types_summary[type_name]["total_instances"] += count
        if status == AgentStatus.ACTIVE:
            agent_types_summary[type_name]["active_instances"] += count

    return {
        "total_instances": total_instances,
        "active_instances": active_instances,
        "completed_instances": completed_instances,
        "agent_types": list(agent_types_summary.values()),
    }


def get_agent_type_instances(
    db: Session, agent_type_id: UUID, user_id: UUID
) -> list[AgentInstanceResponse] | None:
    """Get all instances for a specific user agent"""

    user_agent = (
        db.query(UserAgent)
        .filter(
            UserAgent.id == agent_type_id,
            UserAgent.user_id == user_id,
            UserAgent.is_deleted.is_(False),
        )
        .first()
    )
    if not user_agent:
        return None

    instances = (
        db.query(AgentInstance)
        .filter(
            AgentInstance.user_agent_id == agent_type_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .options(
            joinedload(AgentInstance.user_agent),
        )
        .order_by(desc(AgentInstance.started_at))
        .all()
    )

    # Get all instance IDs for bulk message stats query
    instance_ids = [instance.id for instance in instances]

    # Get message stats for all instances in one efficient query
    message_stats = _get_instance_message_stats(db, instance_ids)

    # Format instances using helper function with pre-computed stats
    return [format_agent_instance(instance, message_stats) for instance in instances]


def get_agent_instance_detail(
    db: Session,
    instance_id: UUID,
    user_id: UUID,
    message_limit: int | None = None,
    before_message_id: UUID | None = None,
) -> AgentInstanceDetail | None:
    """Get detailed information about a specific agent instance for a specific user with optional message pagination using cursor"""

    instance, access = _require_instance_access(
        db, instance_id, user_id, InstanceAccessLevel.READ
    )
    if not instance or not access:
        return None

    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == instance_id)
        .options(joinedload(AgentInstance.user_agent))
        .first()
    )

    if not instance:
        return None

    # Build message query
    messages_query = (
        db.query(Message)
        .options(joinedload(Message.sender_user))
        .filter(Message.agent_instance_id == instance_id)
    )

    # If cursor provided, get messages before that message
    if before_message_id:
        cursor_message = (
            db.query(Message.created_at).filter(Message.id == before_message_id).first()
        )
        if cursor_message:
            messages_query = messages_query.filter(
                Message.created_at < cursor_message.created_at
            )

    # Order by created_at DESC and apply limit
    messages_query = messages_query.order_by(desc(Message.created_at))
    if message_limit is not None:
        messages_query = messages_query.limit(message_limit)

    messages = messages_query.all()

    # Reverse to get chronological order (oldest first) for display
    messages = list(reversed(messages))

    # Format messages for chat display
    formatted_messages = [_message_to_response(msg) for msg in messages]

    metadata = (
        instance.instance_metadata
        if isinstance(instance.instance_metadata, dict)
        else None
    )

    session_config = (
        dict(instance.session_config)
        if isinstance(instance.session_config, dict)
        else None
    )

    return AgentInstanceDetail(
        id=str(instance.id),
        agent_type_id=str(instance.user_agent_id) if instance.user_agent_id else "",
        agent_type_name=instance.user_agent.name if instance.user_agent else "Unknown",
        name=instance.name,
        status=instance.status,
        started_at=instance.started_at,
        ended_at=instance.ended_at,
        git_diff=instance.git_diff,
        messages=formatted_messages,
        last_read_message_id=str(instance.last_read_message_id)
        if instance.last_read_message_id
        else None,
        last_heartbeat_at=instance.last_heartbeat_at,
        access_level=access,
        is_owner=str(instance.user_id) == str(user_id),
        instance_metadata=metadata,
        session_config=session_config,
        project=instance.project,
        home_dir=instance.home_dir,
        machine_id=str(instance.machine_id) if instance.machine_id else None,
        live_state=_live_state_for(instance),
        rate_limited=instance.rate_limited_until is not None,
        rate_limit_resets_at=instance.rate_limited_until,
    )


_TERMINAL_STATUSES = frozenset(
    {
        AgentStatus.COMPLETED,
        AgentStatus.KILLED,
        AgentStatus.DELETED,
        AgentStatus.FAILED,
        AgentStatus.DISCONNECTED,
    }
)

# String values of terminal statuses — used by SSE generators for status-string comparison.
TERMINAL_STATUS_VALUES: frozenset[str] = frozenset(s.value for s in _TERMINAL_STATUSES)


def _notify_terminate(db: Session, instance_id: UUID) -> None:
    """Fire a best-effort NOTIFY so any listening headless process exits cleanly."""
    try:
        channel = f"message_channel_{instance_id}"
        payload = json.dumps(
            {"event_type": "terminate", "instance_id": str(instance_id)}
        )
        db.execute(text(f'NOTIFY "{channel}", :payload'), {"payload": payload})
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to send terminate NOTIFY for %s: %s", instance_id, exc
        )


def update_instance_status(
    db: Session, instance_id: UUID, user_id: UUID, new_status: AgentStatus
) -> AgentInstanceResponse | None:
    """Update an agent instance status for a specific user"""

    # Check if instance exists and belongs to user
    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == instance_id, AgentInstance.user_id == user_id)
        .first()
    )
    if not instance:
        return None

    # Do not allow updating DELETED instances - they should stay deleted
    if instance.status == AgentStatus.DELETED:
        return None

    # Update status
    instance.status = new_status

    # Set ended_at if completing
    if new_status == AgentStatus.COMPLETED:
        instance.ended_at = datetime.now(timezone.utc)

    # Signal any listening headless process to terminate.
    if new_status in _TERMINAL_STATUSES:
        _notify_terminate(db, instance_id)

    db.commit()

    # Re-query with relationships to ensure they're loaded for format_agent_instance
    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == instance_id)
        .options(
            joinedload(AgentInstance.user_agent),
        )
        .first()
    )

    if not instance:
        return None

    # Get message stats for this single instance
    message_stats = _get_instance_message_stats(db, [instance.id])

    return format_agent_instance(instance, message_stats)


def mark_instance_completed(
    db: Session, instance_id: UUID, user_id: UUID
) -> AgentInstanceResponse | None:
    """Mark an agent instance as completed for a specific user"""
    # Use the generic update_instance_status function
    return update_instance_status(db, instance_id, user_id, AgentStatus.COMPLETED)


def delete_user_account(db: Session, user_id: UUID) -> None:
    """Delete a user account and all associated data in the correct order"""
    logger = logging.getLogger(__name__)

    # Start a transaction
    try:
        # Run overlay teardown first (billing: cancel any Stripe subscription and
        # delete subscription / billing-event rows before the user row). No-op in
        # the open-source build where the billing overlay is absent. See
        # plans/todos/oss-cut-manifest.md (A4 weld #4).
        run_user_delete_hooks(db, user_id)

        # Delete in order of foreign key dependencies
        # Get all agent instances for this user to delete their related data
        all_instances = (
            db.query(AgentInstance.id, AgentInstance.status)
            .filter(AgentInstance.user_id == user_id)
            .all()
        )
        instance_ids = [row.id for row in all_instances]

        # Phase 2b: tell any still-listening headless wrapper / daemon to
        # exit cleanly before we wipe its instance row. NOTIFY is
        # transactional, so listeners only receive "terminate" if this
        # delete actually commits. Skipping instances that are already in
        # a terminal status avoids redundant signals — those listeners
        # already shut down when they entered that status (see
        # update_instance_status).
        # See plans/bugs/p0-agent-jwt-no-db-validation.md (Phase 2b).
        for row in all_instances:
            if row.status not in _TERMINAL_STATUSES:
                _notify_terminate(db, row.id)

        if instance_ids:
            # Delete messages for user's instances
            db.query(Message).filter(
                Message.agent_instance_id.in_(instance_ids)
            ).delete(synchronize_session=False)

        # 3. Delete AgentInstances (depends on UserAgent and User)
        db.query(AgentInstance).filter(AgentInstance.user_id == user_id).delete(
            synchronize_session=False
        )

        # 4. Delete UserAgents (depends on User)
        db.query(UserAgent).filter(UserAgent.user_id == user_id).delete(
            synchronize_session=False
        )

        # 5. Delete APIKeys (depends on User)
        db.query(APIKey).filter(APIKey.user_id == user_id).delete(
            synchronize_session=False
        )

        # 6. Delete PushTokens (depends on User)
        db.query(PushToken).filter(PushToken.user_id == user_id).delete(
            synchronize_session=False
        )

        # (Billing rows — subscriptions / billing_events — were removed above by
        # the user-delete hook when the billing overlay is present.)

        # 7. Finally, delete the User
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)

        # Commit the transaction
        db.commit()
        logger.info(f"Successfully deleted user {user_id} and all associated data")

        # Phase 2b extension: tell the `server` process to close every live
        # WS connection owned by this user with 4401 "credential_revoked", so
        # the daemon (and any other WS clients) drop within milliseconds —
        # instead of waiting for the next REST heartbeat to bounce off
        # Phase 1's FK handler. Fire-and-forget HTTP POST: the DB delete has
        # already committed, so a bridge failure only delays the WS teardown
        # (PR #45's reactive bouncer still catches the next REST write). See
        # plans/bugs/p0-agent-jwt-no-db-validation.md (Phase 2b extension).
        try:
            from backend.broadcast_bridge import post_close_user

            post_close_user(str(user_id))
        except Exception:
            # Bridge failure must not surface as a delete failure; the user is
            # already gone from the DB. post_close_user logs its own metric.
            logger.exception(
                "post_close_user raised after delete_user_account commit (user=%s)",
                user_id,
            )

    except Exception as e:
        # Rollback on any error
        db.rollback()
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        raise


def delete_agent_instance(db: Session, instance_id: UUID, user_id: UUID) -> bool:
    """Soft delete an agent instance for a specific user"""

    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == instance_id, AgentInstance.user_id == user_id)
        .first()
    )

    if not instance:
        return False

    # Signal any listening headless process to terminate before wiping messages.
    _notify_terminate(db, instance_id)

    # Delete related messages to save space
    db.query(Message).filter(Message.agent_instance_id == instance_id).delete()

    # Soft delete: mark as DELETED instead of actually deleting
    instance.status = AgentStatus.DELETED
    db.commit()

    return True


def update_agent_instance_name(
    db: Session, instance_id: UUID, user_id: UUID, name: str
) -> AgentInstanceResponse | None:
    """Update the name of an agent instance for a specific user"""

    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == instance_id, AgentInstance.user_id == user_id)
        .options(
            joinedload(AgentInstance.user_agent),
        )
        .first()
    )

    if not instance:
        return None

    instance.name = name
    db.commit()
    db.refresh(instance)

    # Get message stats for this single instance
    message_stats = _get_instance_message_stats(db, [instance.id])

    # Return the updated instance in the standard format
    return format_agent_instance(instance, message_stats)


def update_agent_instance_pinned(
    db: Session, instance_id: UUID, user_id: UUID, pinned: bool
) -> AgentInstanceResponse | None:
    """Pin or unpin an agent instance for a specific user.

    Re-pinning an already-pinned instance preserves the original timestamp,
    so the shared pin order remains stable across redundant client requests.
    """

    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == instance_id, AgentInstance.user_id == user_id)
        .options(joinedload(AgentInstance.user_agent))
        .first()
    )

    if not instance:
        return None

    if pinned and instance.pinned_at is None:
        instance.pinned_at = datetime.now(timezone.utc)
    elif not pinned:
        instance.pinned_at = None

    db.commit()
    db.refresh(instance)

    message_stats = _get_instance_message_stats(db, [instance.id])
    return format_agent_instance(instance, message_stats)


def link_instance_to_task(
    db: Session, instance_id: UUID, user_id: UUID, task_id: UUID | None
) -> AgentInstanceResponse | None:
    """Stamp (or clear) agent_instances.task_id — the §8b late link.

    The before_flush listener in shared.database.tasks re-evaluates the
    linked task's status on this commit, so a task linked to an already-
    ACTIVE instance moves to in_progress here. None = instance or task
    not found / not the user's.
    """
    from .task_queries import get_task

    instance = (
        db.query(AgentInstance)
        .filter(AgentInstance.id == instance_id, AgentInstance.user_id == user_id)
        .options(joinedload(AgentInstance.user_agent))
        .first()
    )
    if instance is None:
        return None
    if task_id is not None and get_task(db, user_id, task_id) is None:
        return None

    instance.task_id = task_id
    db.commit()
    db.refresh(instance)

    message_stats = _get_instance_message_stats(db, [instance.id])
    return format_agent_instance(instance, message_stats)


def list_task_instances(
    db: Session, user_id: UUID, task_id: UUID
) -> list[AgentInstanceResponse]:
    """Sessions (agent instances) linked to a task, most recent first.

    Powers the Tasks dialog's linked-sessions strip: the reverse of the §8b
    late link that stamps ``agent_instances.task_id``. Scoped to the owning
    user and skips soft-deleted rows; an unknown or foreign task simply yields
    an empty list.
    """
    instances = (
        db.query(AgentInstance)
        .filter(
            AgentInstance.task_id == task_id,
            AgentInstance.user_id == user_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .options(
            joinedload(AgentInstance.user_agent),
            # live_state compares against the machine heartbeat; joinedload it
            # here so each row doesn't fire an extra query.
            joinedload(AgentInstance.machine),
        )
        .order_by(desc(AgentInstance.started_at))
        .all()
    )
    if not instances:
        return []

    message_stats = _get_instance_message_stats(db, [i.id for i in instances])
    return [format_agent_instance(i, message_stats) for i in instances]


def get_message_by_id(db: Session, message_id: UUID, user_id: UUID) -> dict | None:
    """
    Get a single message by ID with user authorization check.
    Returns the message data if authorized, None if not found or unauthorized.
    """
    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        return None

    instance, access = _require_instance_access(
        db, message.agent_instance_id, user_id, InstanceAccessLevel.READ
    )

    if not instance or not access:
        return None

    # Get sender information if it's a user message
    sender_user = None
    if message.sender_user_id:
        sender_user = db.query(User).filter(User.id == message.sender_user_id).first()

    return _message_to_dict(message, sender_user)


def get_instance_messages(
    db: Session,
    instance_id: UUID,
    user_id: UUID,
    limit: int = 50,
    before_message_id: UUID | None = None,
) -> list[MessageResponse] | None:
    """
    Get paginated messages for an agent instance using cursor-based pagination.
    Returns list of messages if authorized, None if not found or unauthorized.
    """
    # Verify instance belongs to user
    instance, access = _require_instance_access(
        db, instance_id, user_id, InstanceAccessLevel.READ
    )

    if not instance or not access:
        return None

    # Build message query
    messages_query = (
        db.query(Message)
        .options(joinedload(Message.sender_user))
        .filter(Message.agent_instance_id == instance_id)
    )

    # If cursor provided, get messages before that message
    if before_message_id:
        cursor_message = (
            db.query(Message.created_at).filter(Message.id == before_message_id).first()
        )
        if cursor_message:
            messages_query = messages_query.filter(
                Message.created_at < cursor_message.created_at
            )

    # Order by created_at DESC and apply limit
    messages = messages_query.order_by(desc(Message.created_at)).limit(limit).all()

    # Reverse to get chronological order
    messages = list(reversed(messages))

    # Convert to MessageResponse objects
    return [_message_to_response(msg) for msg in messages]


CATCHUP_MAX_MESSAGES = 500


def _message_to_dict(msg: Message, sender_user: User | None) -> dict:
    """Shared dict shape for SSE message events (matches get_message_by_id)."""
    return {
        "id": str(msg.id),
        "agent_instance_id": str(msg.agent_instance_id),
        "sender_type": msg.sender_type.value,
        "sender_user_id": str(msg.sender_user_id) if msg.sender_user_id else None,
        "sender_user_email": sender_user.email if sender_user else None,
        "sender_user_display_name": sender_user.display_name if sender_user else None,
        "content": msg.content,
        "created_at": msg.created_at.isoformat() + "Z",
        "requires_user_input": msg.requires_user_input,
        "message_metadata": msg.message_metadata,
    }


def get_messages_after_id(
    db: Session,
    instance_id: UUID,
    user_id: UUID,
    after_message_id: UUID | None,
    limit: int = CATCHUP_MAX_MESSAGES,
) -> list[dict]:
    """Return messages newer than after_message_id for SSE delivery.

    Uses (created_at, id) cursor ordering to handle same-millisecond writes.
    Returns plain dicts so the SSE generator can json.dumps() them directly.
    Bounded by ``limit`` to prevent flooding on a chatty catch-up.

    When ``after_message_id`` is None (brand-new session, no prior messages),
    all messages for the instance are returned — same dict shape, ready to yield.

    Returns an empty list when the cursor message is not found in this instance,
    when the user lacks access, or when no messages are newer than the cursor.
    """
    instance, access = _require_instance_access(
        db, instance_id, user_id, InstanceAccessLevel.READ
    )
    if not instance or not access:
        return []

    if after_message_id is None:
        messages = (
            db.query(Message)
            .options(joinedload(Message.sender_user))
            .filter(Message.agent_instance_id == instance_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
            .all()
        )
        return [_message_to_dict(msg, msg.sender_user) for msg in messages]

    # Cursor lookup is scoped to this instance: a stale or cross-instance cursor
    # must not leak rows from another conversation.
    cursor = (
        db.query(Message.created_at, Message.id)
        .filter(
            Message.id == after_message_id,
            Message.agent_instance_id == instance_id,
        )
        .first()
    )
    if not cursor:
        return []

    cursor_ts, cursor_id = cursor.created_at, cursor.id

    messages = (
        db.query(Message)
        .options(joinedload(Message.sender_user))
        .filter(Message.agent_instance_id == instance_id)
        .filter(
            or_(
                Message.created_at > cursor_ts,
                (Message.created_at == cursor_ts) & (Message.id > cursor_id),
            )
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit)
        .all()
    )

    return [_message_to_dict(msg, msg.sender_user) for msg in messages]


def get_latest_message_id(
    db: Session,
    instance_id: UUID,
    user_id: UUID,
) -> UUID | None:
    """Return the ID of the most recent message for instance_id, or None.

    Used by SSE generators to initialise the cursor when the client connects
    without a prior ``last_message_id`` so new messages can be tracked.
    Returns None when the user lacks access or there are no messages yet.
    """
    instance, access = _require_instance_access(
        db, instance_id, user_id, InstanceAccessLevel.READ
    )
    if not instance or not access:
        return None
    row = (
        db.query(Message.id)
        .filter(Message.agent_instance_id == instance_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .first()
    )
    return row[0] if row else None


def get_instance_status(db: Session, instance_id: UUID, user_id: UUID) -> str | None:
    """Return the current status string for an instance, or None if not found / no access.

    Used by SSE generators to detect terminal states after a wake with no new messages.
    """
    instance, access = _require_instance_access(
        db, instance_id, user_id, InstanceAccessLevel.READ
    )
    if not instance or not access:
        return None
    s = instance.status
    return s.value if hasattr(s, "value") else str(s)


def get_instance_git_diff(db: Session, instance_id: UUID, user_id: UUID) -> dict | None:
    """
    Get the git diff for an agent instance with user authorization check.
    Returns the git diff data if authorized, None if not found or unauthorized.
    """
    instance, access = _require_instance_access(
        db, instance_id, user_id, InstanceAccessLevel.READ
    )

    if not instance or not access:
        return None

    return {"instance_id": str(instance.id), "git_diff": instance.git_diff}


def create_user_message_with_access(
    db: Session,
    instance_id: UUID,
    user_id: UUID,
    content: str,
    mark_as_read: bool = False,
) -> Message:
    """Create a user-authored message after validating write access.

    Returns the ORM `Message` so the caller can build both the API response
    and the realtime `update` envelope from the same row before committing
    (websocket-migration §4 Phase 3).
    """

    instance, access = get_instance_and_access(db, instance_id, user_id)
    if not instance:
        raise ValueError("Agent instance not found")

    if access != InstanceAccessLevel.WRITE:
        raise ValueError("Agent instance not found")

    message = Message(
        agent_instance_id=instance.id,
        sender_type=SenderType.USER,
        sender_user_id=user_id,
        content=content,
        requires_user_input=False,
    )
    db.add(message)
    db.flush()
    db.refresh(message)

    # Only claim the session is working if something is actually there to work.
    #
    # This used to be unconditional, which meant sending a message to a dead
    # session flipped it back to ACTIVE — so the user's own message is what made
    # the corpse render a "working" spinner, forever. A terminal session is only
    # revived when its agent is still heartbeating (e.g. the user archived a
    # live session and then wrote to it); otherwise it stays terminal and the
    # client surfaces it as stopped rather than busy.
    if instance.status not in _TERMINAL_STATUSES or is_fresh(
        instance.last_heartbeat_at
    ):
        instance.status = AgentStatus.ACTIVE
    if mark_as_read:
        instance.last_read_message_id = message.id

    try:
        from servers.shared.db.queries import trigger_webhook_for_user_response

        trigger_webhook_for_user_response(
            db=db,
            agent_instance_id=str(instance.id),
            user_message_content=content,
            user_message_id=str(message.id),
            user_id=str(user_id),
        )
    except (
        Exception
    ) as exc:  # pragma: no cover - webhook failures shouldn't block messaging
        logging.getLogger(__name__).exception(
            "Failed to trigger webhook for user response: %s", exc
        )

    return message


def cancel_user_message(db: Session, message_id: UUID) -> bool:
    """Stamp `message_metadata["queue"]` as cancelled, unless already consumed.

    Server-side `jsonb_set` so concurrent writers never clobber each other's
    metadata keys outside `queue`. Skips the update (via the WHERE clause)
    when `queue.status` is already `"consumed"` — a race between the user
    cancelling a queued message and the agent picking it up must leave the
    consumption as the terminal state (mirror image of
    `servers.shared.db.queries.mark_message_consumed`'s cancelled guard).
    Only USER-sent messages may be cancelled.

    `message_metadata` defaults to Python `None`, and this JSONB column does
    not set `none_as_null=True`, so "no metadata yet" is stored as the JSON
    scalar `null`, not SQL NULL — `coalesce()` alone does not catch that.
    `jsonb_typeof(...) == "object"` is the guard that works for both SQL NULL
    and JSON null (and any other non-object shape), falling back to `{}`
    before `jsonb_set` writes the `queue` key. Copied verbatim (guard swapped)
    from `mark_message_consumed`, which verified this against a real Postgres
    instance — do not reintroduce `coalesce()` here.

    Returns True iff a row was updated (the message existed, was USER-sent,
    and was not already consumed).
    """
    now = datetime.now(timezone.utc).isoformat()
    stmt = (
        update(Message)
        .where(
            Message.id == message_id,
            Message.sender_type == SenderType.USER,
            Message.message_metadata[("queue", "status")].astext.is_distinct_from(
                "consumed"
            ),
        )
        .values(
            message_metadata=func.jsonb_set(
                case(
                    (
                        func.jsonb_typeof(Message.message_metadata) == "object",
                        Message.message_metadata,
                    ),
                    else_=cast({}, JSONB),
                ),
                "{queue}",
                cast({"status": "cancelled", "cancelled_at": now}, JSONB),
            )
        )
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount > 0


# ============================================================================
# Message attachment queries
# ============================================================================


def create_attachment(
    db: Session,
    *,
    attachment_id: UUID,
    user_id: UUID,
    instance_id: UUID,
    s3_key: str,
    mime_type: str,
    size_bytes: int,
    width: int | None,
    height: int | None,
    original_filename: str | None,
) -> MessageAttachment:
    """Record an uploaded attachment, pending attachment to a message at send time.

    Requires WRITE access to the instance (uploaders are about to send a
    message there). Raises ValueError when the instance is missing or the
    user lacks access — indistinguishable on purpose, like message sends.
    """
    instance, _ = _require_instance_access(
        db, instance_id, user_id, InstanceAccessLevel.WRITE
    )
    if not instance:
        raise ValueError("Agent instance not found")

    attachment = MessageAttachment(
        id=attachment_id,
        user_id=user_id,
        agent_instance_id=instance_id,
        s3_key=s3_key,
        mime_type=mime_type,
        size_bytes=size_bytes,
        width=width,
        height=height,
        original_filename=original_filename,
    )
    db.add(attachment)
    db.flush()
    return attachment


def get_attachment_for_user(
    db: Session, attachment_id: UUID, user_id: UUID
) -> MessageAttachment | None:
    """Fetch an attachment the user may view: their own upload, or any
    upload in an instance they have (at least read) access to."""
    attachment = (
        db.query(MessageAttachment)
        .filter(MessageAttachment.id == attachment_id)
        .first()
    )
    if not attachment:
        return None
    if attachment.user_id == user_id:
        return attachment
    _, access = get_instance_and_access(db, attachment.agent_instance_id, user_id)
    if access is None:
        return None
    return attachment


def bind_attachments_to_message(
    db: Session,
    *,
    attachment_ids: list[UUID],
    user_id: UUID,
    message: Message,
) -> list[dict]:
    """Bind the user's uploaded attachments to a just-created message and
    stamp the denormalized display copy into message_metadata["attachments"]
    (pre-commit, so the realtime envelope and API response carry it).

    Raises ValueError if any id is missing, foreign, for another instance,
    or already bound to a message.
    """
    rows = (
        db.query(MessageAttachment)
        .filter(
            MessageAttachment.id.in_(attachment_ids),
            MessageAttachment.user_id == user_id,
            MessageAttachment.agent_instance_id == message.agent_instance_id,
            MessageAttachment.message_id.is_(None),
        )
        .all()
    )
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(set(attachment_ids)):
        raise ValueError("Attachment not found or already attached")

    attachments_meta: list[dict] = []
    for attachment_id in attachment_ids:
        row = by_id[attachment_id]
        row.message_id = message.id
        attachments_meta.append(
            {
                "id": str(row.id),
                "mime_type": row.mime_type,
                "size_bytes": row.size_bytes,
                "width": row.width,
                "height": row.height,
                "filename": row.original_filename,
            }
        )

    message.message_metadata = {
        **(message.message_metadata or {}),
        "attachments": attachments_meta,
    }
    db.flush()
    return attachments_meta


# ============================================================================
# Team queries
# ============================================================================


def get_instance_shares(
    db: Session, instance_id: UUID, user_id: UUID
) -> list[InstanceShareResponse]:
    instance = (
        db.query(AgentInstance)
        .options(joinedload(AgentInstance.user))
        .filter(AgentInstance.id == instance_id)
        .first()
    )

    if not instance:
        raise ValueError("Agent instance not found")

    if instance.user_id != user_id:
        raise PermissionError("Only the owner can manage access")

    shares = (
        db.query(UserInstanceAccess)
        .options(joinedload(UserInstanceAccess.user))
        .filter(UserInstanceAccess.agent_instance_id == instance_id)
        .order_by(UserInstanceAccess.created_at.asc())
        .all()
    )

    results: list[InstanceShareResponse] = []
    results.append(_instance_owner_share_response(instance))

    for share in shares:
        results.append(_instance_access_to_response(share))

    return results


def add_instance_share(
    db: Session,
    instance_id: UUID,
    user_id: UUID,
    email: str,
    access_level: InstanceAccessLevel,
) -> InstanceShareResponse:
    instance = (
        db.query(AgentInstance)
        .options(joinedload(AgentInstance.user))
        .filter(AgentInstance.id == instance_id)
        .first()
    )

    if not instance:
        raise ValueError("Agent instance not found")

    if instance.user_id != user_id:
        raise PermissionError("Only the owner can manage access")

    normalized_email = _normalize_email(email)
    owner_email = instance.user.email if instance.user else None
    if owner_email and _normalize_email(owner_email) == normalized_email:
        raise ValueError("Owner already has full access")

    existing = (
        db.query(UserInstanceAccess)
        .filter(
            UserInstanceAccess.agent_instance_id == instance_id,
            func.lower(UserInstanceAccess.shared_email) == normalized_email,
        )
        .first()
    )

    if existing:
        raise ValueError("This email already has access to the session")

    target_user = _get_user_by_email(db, email)

    share = UserInstanceAccess(
        agent_instance_id=instance_id,
        shared_email=email.strip(),
        user_id=target_user.id if target_user else None,
        access=access_level,
        granted_by_user_id=user_id,
    )
    db.add(share)
    db.flush()
    if target_user:
        share.user = target_user

    return _instance_access_to_response(share)


def remove_instance_share(
    db: Session, instance_id: UUID, user_id: UUID, access_id: UUID
) -> None:
    instance = db.query(AgentInstance).filter(AgentInstance.id == instance_id).first()

    if not instance:
        raise ValueError("Agent instance not found")

    if instance.user_id != user_id:
        raise PermissionError("Only the owner can manage access")

    share = (
        db.query(UserInstanceAccess)
        .filter(
            UserInstanceAccess.id == access_id,
            UserInstanceAccess.agent_instance_id == instance_id,
        )
        .first()
    )

    if not share:
        raise ValueError("Share not found")

    db.delete(share)


def get_user_teams(db: Session, user_id: UUID) -> list[TeamSummary]:
    """Return summary information for teams the user belongs to."""

    membership_alias = aliased(TeamMembership)
    member_count_subq = (
        db.query(
            TeamMembership.team_id.label("team_id"),
            func.count(TeamMembership.id).label("member_count"),
        )
        .group_by(TeamMembership.team_id)
        .subquery()
    )

    results = (
        db.query(
            Team,
            membership_alias.role.label("user_role"),
            member_count_subq.c.member_count,
        )
        .join(membership_alias, membership_alias.team_id == Team.id)
        .join(member_count_subq, member_count_subq.c.team_id == Team.id)
        .filter(membership_alias.user_id == user_id)
        .all()
    )

    summaries: list[TeamSummary] = []
    for team, user_role, member_count in results:
        summaries.append(
            TeamSummary(
                id=str(team.id),
                name=team.name,
                created_at=team.created_at,
                updated_at=team.updated_at,
                role=user_role,
                member_count=member_count or 0,
            )
        )

    return summaries


def get_team_detail(
    db: Session, team_id: UUID, user_id: UUID
) -> TeamDetailResponse | None:
    """Return detailed team info with membership list if user belongs to the team."""

    membership = _get_team_membership(db, team_id, user_id)
    if not membership:
        return None

    team = (
        db.query(Team)
        .options(
            selectinload(Team.memberships).options(joinedload(TeamMembership.user))
        )
        .filter(Team.id == team_id)
        .first()
    )

    if not team:
        return None

    members = sorted(team.memberships, key=lambda m: m.created_at)
    member_responses = [_team_member_to_response(member) for member in members]

    return TeamDetailResponse(
        id=str(team.id),
        name=team.name,
        created_at=team.created_at,
        updated_at=team.updated_at,
        role=membership.role,
        members=member_responses,
    )


def create_team(db: Session, owner: User, name: str) -> TeamDetailResponse:
    """Create a new team and assign the owner membership."""

    team = Team(name=name)
    db.add(team)
    db.flush()

    owner_membership = TeamMembership(
        team_id=team.id,
        user_id=owner.id,
        invited_email=owner.email,
        role=TeamRole.OWNER,
    )
    db.add(owner_membership)
    db.flush()

    db.refresh(team)
    db.refresh(owner_membership)

    return get_team_detail(db, team.id, owner.id)  # type: ignore[arg-type]


def update_team(
    db: Session, team_id: UUID, acting_user_id: UUID, name: str
) -> TeamSummary | None:
    """Rename a team if the acting user is an owner or admin."""

    membership = _get_team_membership(db, team_id, acting_user_id)
    if not membership:
        return None

    if membership.role not in (TeamRole.OWNER, TeamRole.ADMIN):
        raise PermissionError("Only owners or admins can update team details")

    team = _get_team(db, team_id)
    if not team:
        return None

    team.name = name
    db.flush()

    member_count = (
        db.query(func.count(TeamMembership.id))
        .filter(TeamMembership.team_id == team_id)
        .scalar()
        or 0
    )

    return TeamSummary(
        id=str(team.id),
        name=team.name,
        created_at=team.created_at,
        updated_at=team.updated_at,
        role=membership.role,
        member_count=member_count,
    )


def delete_team(db: Session, team_id: UUID, acting_user_id: UUID) -> bool:
    """Delete a team when the acting user is the owner."""

    membership = _get_team_membership(db, team_id, acting_user_id)
    if not membership:
        return False

    if membership.role != TeamRole.OWNER:
        raise PermissionError("Only the team owner can delete the team")

    team = _get_team(db, team_id)
    if not team:
        return False

    db.delete(team)
    return True


def add_team_member(
    db: Session,
    team_id: UUID,
    acting_user_id: UUID,
    email: str,
    role: TeamRole | None = None,
) -> TeamMemberResponse:
    """Add a member to the team by email. Allows placeholder entries when the user does not exist yet."""

    membership = _get_team_membership(db, team_id, acting_user_id)
    if not membership:
        raise PermissionError("Team not found or access denied")

    if membership.role not in (TeamRole.OWNER, TeamRole.ADMIN):
        raise PermissionError("Only owners or admins can add members")

    desired_role = role or TeamRole.MEMBER
    if desired_role == TeamRole.OWNER:
        raise ValueError("Cannot assign OWNER role when adding a member")
    if desired_role == TeamRole.ADMIN and membership.role != TeamRole.OWNER:
        raise PermissionError(
            "Only owners can assign the admin role when inviting members"
        )

    normalized_email = _normalize_email(email)
    existing_user = _get_user_by_email(db, email)

    filters = [func.lower(TeamMembership.invited_email) == normalized_email]
    if existing_user:
        filters.append(TeamMembership.user_id == existing_user.id)

    existing_membership = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id)
        .filter(or_(*filters))
        .first()
    )
    if existing_membership:
        raise ValueError("Member with this email is already part of the team")

    membership_entry = TeamMembership(
        team_id=team_id,
        user_id=existing_user.id if existing_user else None,
        invited_email=email.strip(),
        role=desired_role,
    )
    db.add(membership_entry)
    db.flush()
    db.refresh(membership_entry)

    if existing_user:
        membership_entry.user = existing_user

    return _team_member_to_response(membership_entry)


def update_team_member_role(
    db: Session,
    team_id: UUID,
    membership_id: UUID,
    acting_user_id: UUID,
    new_role: TeamRole,
) -> TeamMemberResponse | None:
    """Update a member's role. Restricted to team owners."""

    acting_membership = _get_team_membership(db, team_id, acting_user_id)
    if not acting_membership:
        return None

    if acting_membership.role != TeamRole.OWNER:
        raise PermissionError("Only the team owner can change member roles")

    target_membership = (
        db.query(TeamMembership)
        .options(joinedload(TeamMembership.user))
        .filter(TeamMembership.id == membership_id, TeamMembership.team_id == team_id)
        .first()
    )

    if not target_membership:
        return None

    if target_membership.role == TeamRole.OWNER:
        raise ValueError("Cannot modify the owner role")

    if new_role == TeamRole.OWNER:
        raise ValueError("Cannot promote another member to owner through this endpoint")

    target_membership.role = new_role
    db.flush()
    db.refresh(target_membership)

    return _team_member_to_response(target_membership)


def remove_team_member(
    db: Session,
    team_id: UUID,
    membership_id: UUID,
    acting_user_id: UUID,
) -> bool:
    """Remove a member from the team respecting role restrictions."""

    acting_membership = _get_team_membership(db, team_id, acting_user_id)
    if not acting_membership:
        raise PermissionError("Team not found or access denied")

    if acting_membership.role not in (TeamRole.OWNER, TeamRole.ADMIN):
        raise PermissionError("Only owners or admins can remove members")

    target_membership = (
        db.query(TeamMembership)
        .filter(TeamMembership.id == membership_id, TeamMembership.team_id == team_id)
        .first()
    )

    if not target_membership:
        return False

    if target_membership.role == TeamRole.OWNER:
        raise ValueError("Cannot remove the team owner")

    if (
        acting_membership.role == TeamRole.ADMIN
        and target_membership.role == TeamRole.ADMIN
        and target_membership.user_id != acting_user_id
    ):
        raise PermissionError("Admins can only remove members or themselves")

    db.delete(target_membership)
    return True
