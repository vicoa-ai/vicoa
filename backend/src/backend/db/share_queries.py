"""Share links: owner-side management and the public (token-authorized) reads.

Collaboration §3.4 / §10. Two halves, deliberately in one module so the rule
that binds them is visible in one place:

* the **owner** half runs under a signed-in user and the normal role ladder —
  creating, listing and revoking links is `admin` on the target, the same
  floor as the per-email session shares;
* the **public** half runs under a `ShareGrant` from `shared.access.resolve_share`
  and nothing else. It never widens: a grant reaches exactly the sessions /
  tasks its kind and filters describe, and every id a caller supplies is
  re-checked against that set (a session id under a project link, an
  attachment's session, a task's project) — a leaked or guessed id on its own
  buys nothing.

Serialization here is the *public* shape (`PublicSessionSummary`,
`PublicMessage`): display names, never emails; the `session_config` display
subset, never `home_dir`, the machine, or raw `instance_metadata` (D5).
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import desc, false, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from shared import access
from shared.database import (
    AgentInstance,
    AgentStatus,
    Message,
    MessageAttachment,
    Project,
    ShareLink,
    Task,
    TaskLabel,
    User,
)
from shared.database.agent_profile_models import AgentProfile
from shared.database.session import SessionLocal

from ..models import (
    PrincipalResponse,
    PublicBoardResponse,
    PublicMessage,
    PublicMessagesPage,
    PublicProjectSummary,
    PublicSessionSummary,
    PublicSessionsPage,
    PublicShareResponse,
    ShareLinkResponse,
    TaskLabelResponse,
    TaskResponse,
    TaskTimelineResponse,
)
from .queries import _get_instance_message_stats, _live_state_for
from .task_queries import _project_vocabulary_filter
from .task_serializers import serialize_tasks

logger = logging.getLogger(__name__)


class ShareTargetNotFoundError(LookupError):
    """The session / project / link is invisible to this caller (→ 404)."""


# The `session_config` keys a viewer may see (old plan D5): what ran, with
# which model and effort, under which permission mode. Nothing operational.
_PUBLIC_SESSION_CONFIG_KEYS = (
    "agent",
    "model",
    "thinking_effort",
    "reasoning_effort",
    "permission_mode",
    "opencode_mode",
)

MAX_PUBLIC_MESSAGE_PAGE = 200
MAX_PUBLIC_SESSION_PAGE = 100


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- principals ----------------------------------------------------------------


def _user_principal(user: User | None) -> PrincipalResponse:
    if user is None:
        return PrincipalResponse(type="user", id=None, name="Deleted user")
    return PrincipalResponse(
        type="user",
        id=user.id,
        name=user.display_name,
        avatar_image_uri=user.avatar_image_uri,
        emoji=user.avatar_emoji,
        updated_at=user.updated_at,
    )


def _agent_profile_principal(profile: AgentProfile | None) -> PrincipalResponse | None:
    if profile is None:
        return None
    return PrincipalResponse(
        type="agent",
        id=profile.id,
        name=profile.name,
        avatar_image_uri=profile.avatar_image_uri,
        emoji=profile.emoji,
        updated_at=profile.updated_at,
    )


# --- the owner on a public page --------------------------------------------------

# How the link's creator reads on a public page that does not name them. No id,
# so nothing on the page correlates back to an account; no avatar, so the
# client draws its generic glyph — the honest picture of "someone".
ANONYMOUS_OWNER_NAME = "Owner"


def _public_principal(
    principal: PrincipalResponse, link: ShareLink
) -> PrincipalResponse:
    """The owner as a public page may show them (§10.4).

    A link that hides the owner (`show_owner=False`) hides them *everywhere* —
    as a task's assignee, a comment's author, an activity's actor, a reactor —
    not only in the sidebar card; otherwise "don't show my name" would remove
    the card and leave the name on every row under it. A link that shows the
    owner keeps their name and avatar, but an account with no display name
    still reads "Owner" rather than the "Unknown" a client falls back to.
    Everyone else passes through: a visitor who comments through the link
    chose to do so as themselves.
    """
    if (
        principal.type != "user"
        or principal.id is None
        or principal.id != link.created_by_user_id
    ):
        return principal
    if not link.show_owner:
        return PrincipalResponse(type="user", id=None, name=ANONYMOUS_OWNER_NAME)
    if not (principal.name or "").strip():
        return principal.model_copy(update={"name": ANONYMOUS_OWNER_NAME})
    return principal


def _public_reactors(
    reactors: list[PrincipalResponse], link: ShareLink
) -> list[PrincipalResponse]:
    return [_public_principal(r, link) for r in reactors]


def public_tasks(
    db: Session, grant: access.ShareGrant, tasks: list[Task]
) -> list[TaskResponse]:
    """`serialize_tasks` with the owner rule applied to each assignee."""
    rows = serialize_tasks(db, tasks)
    for row in rows:
        if row.assignee is None:
            continue
        shown = _public_principal(row.assignee, grant.link)
        if shown is not row.assignee:
            row.assignee = shown
            # The bare id would say what the principal no longer does.
            row.assignee_id = shown.id
    return rows


def public_timeline(
    timeline: TaskTimelineResponse, grant: access.ShareGrant
) -> TaskTimelineResponse:
    """A built timeline with the owner rule applied to every principal in it."""
    link = grant.link
    for comment in timeline.comments:
        comment.author = _public_principal(comment.author, link)
        for reaction in comment.reactions:
            reaction.reactors = _public_reactors(reaction.reactors, link)
    for row in timeline.activity:
        if row.actor is not None:
            row.actor = _public_principal(row.actor, link)
    for reaction in timeline.reactions:
        reaction.reactors = _public_reactors(reaction.reactors, link)
    return timeline


# --- owner side ----------------------------------------------------------------


def _require_target_admin(
    db: Session,
    user_id: UUID,
    *,
    kind: str,
    agent_instance_id: UUID | None,
    project_id: UUID | None,
    scopes: Sequence[str] = (),
) -> None:
    """`admin` on the link's target, over every scope the link would expose.

    Invisible ⇒ ShareTargetNotFoundError (404); visible but below admin ⇒
    AccessDenied (403 via the app handler). A link carrying `sessions` needs
    standing over sessions, one carrying `tasks` needs it over tasks, and one
    carrying both needs both — a tasks-only admin cannot publish the
    transcripts they themselves cannot see.
    """
    if kind == "session":
        instance = (
            db.get(AgentInstance, agent_instance_id)
            if agent_instance_id is not None
            else None
        )
        if instance is None or instance.status == AgentStatus.DELETED:
            raise ShareTargetNotFoundError("Agent instance not found")
        role = access.instance_role(db, user_id, instance)
        if role is None:
            raise ShareTargetNotFoundError("Agent instance not found")
        access.require(role, "admin")
        return

    project = db.get(Project, project_id) if project_id is not None else None
    if project is None or project.is_inbox:
        raise ShareTargetNotFoundError("Project not found")
    for scope in scopes:
        role = access.project_role(
            db,
            user_id,
            project,
            grant_scope=scope,  # type: ignore[arg-type]  # validated by the request model
        )
        if role is None:
            raise ShareTargetNotFoundError("Project not found")
        access.require(role, "admin")


def _link_response(link: ShareLink) -> ShareLinkResponse:
    return ShareLinkResponse(
        id=link.id,
        token=link.token,
        kind=link.kind,  # type: ignore[arg-type]
        agent_instance_id=link.agent_instance_id,
        project_id=link.project_id,
        scopes=list(link.scopes or []),  # type: ignore[arg-type]
        audience=link.audience,  # type: ignore[arg-type]
        filters=link.filters,
        allow_comments=link.allow_comments,
        show_owner=link.show_owner,
        show_branch=link.show_branch,
        expires_at=link.expires_at,
        revoked_at=link.revoked_at,
        last_accessed_at=link.last_accessed_at,
        view_count=link.view_count,
        created_at=link.created_at,
        created_by=_user_principal(link.created_by),
    )


def create_share_link(
    db: Session,
    user: User,
    *,
    kind: str,
    agent_instance_id: UUID | None,
    project_id: UUID | None,
    scopes: Sequence[str],
    audience: str,
    filters: dict | None,
    allow_comments: bool,
    show_owner: bool = False,
    show_branch: bool = False,
    expires_in_days: int | None,
) -> ShareLinkResponse:
    """Mint a link. The request model has already validated shape/filters;
    this checks standing and writes. Commits."""
    _require_target_admin(
        db,
        user.id,
        kind=kind,
        agent_instance_id=agent_instance_id,
        project_id=project_id,
        scopes=scopes,
    )
    link = ShareLink(
        token=secrets.token_urlsafe(32),
        created_by_user_id=user.id,
        kind=kind,
        agent_instance_id=agent_instance_id,
        project_id=project_id,
        scopes=list(scopes),
        audience=audience,
        filters=filters or None,
        allow_comments=allow_comments,
        show_owner=show_owner,
        show_branch=show_branch,
        expires_at=(
            _utcnow() + timedelta(days=expires_in_days)
            if expires_in_days is not None
            else None
        ),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    link.created_by = user
    return _link_response(link)


def list_share_links(
    db: Session,
    user_id: UUID,
    *,
    agent_instance_id: UUID | None = None,
    project_id: UUID | None = None,
) -> list[ShareLinkResponse]:
    """Live (unrevoked) links on one target, newest first. Admin on the
    target — the Link tab shows every admin's links, not just the caller's.
    Revoked rows stay in the table for audit but are not listed."""
    if (agent_instance_id is None) == (project_id is None):
        raise ValueError("Pass exactly one of agent_instance_id / project_id")
    if agent_instance_id is not None:
        _require_target_admin(
            db,
            user_id,
            kind="session",
            agent_instance_id=agent_instance_id,
            project_id=None,
        )
        target = ShareLink.agent_instance_id == agent_instance_id
    else:
        # Listing needs standing on the project, not on a particular scope, so
        # a sessions-only admin still sees that tasks links exist.
        project = db.get(Project, project_id)
        if project is None or project.is_inbox:
            raise ShareTargetNotFoundError("Project not found")
        role = access.project_role(db, user_id, project)
        if role is None:
            raise ShareTargetNotFoundError("Project not found")
        access.require(role, "admin")
        target = ShareLink.project_id == project_id
    rows = (
        db.query(ShareLink)
        .options(joinedload(ShareLink.created_by))
        .filter(target, ShareLink.revoked_at.is_(None))
        .order_by(desc(ShareLink.created_at))
        .all()
    )
    return [_link_response(row) for row in rows]


def revoke_share_link(db: Session, user_id: UUID, link_id: UUID) -> None:
    """Revoke: sets `revoked_at`, keeps the row. Idempotent. Admin on the
    target (the creator is necessarily at least that, but standing can be
    withdrawn — then so is the right to manage the link). Commits."""
    link = db.get(ShareLink, link_id)
    if link is None:
        raise ShareTargetNotFoundError("Share link not found")
    try:
        _require_target_admin(
            db,
            user_id,
            kind=link.kind,
            agent_instance_id=link.agent_instance_id,
            project_id=link.project_id,
        )
    except ShareTargetNotFoundError:
        # The target is gone or invisible to this caller — so is the link.
        raise ShareTargetNotFoundError("Share link not found") from None
    if link.revoked_at is None:
        link.revoked_at = _utcnow()
        db.commit()


# --- public side: what a grant reaches ---------------------------------------


def visible_instances_select(grant: access.ShareGrant):
    """Sessions this grant covers, as a SELECT of ids.

    A session link → the one. A project link carrying `sessions` → the
    project's sessions narrowed by that scope's filters, never DELETED, and —
    unless the link names statuses explicitly — never archived (COMPLETED)
    either (§10.9). Evaluated at view time, so a link keeps matching sessions
    that start later. A project link without the scope → none: it shares the
    tasks, not the transcripts.
    """
    if grant.kind == "session":
        return select(AgentInstance.id).where(
            AgentInstance.id == grant.instance_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
    if not grant.covers("sessions"):
        return select(AgentInstance.id).where(false())

    f = grant.scope_filters("sessions")
    conds = [
        AgentInstance.project_id == grant.project_id,
        AgentInstance.status != AgentStatus.DELETED,
    ]
    statuses = f.get("statuses")
    if statuses:
        conds.append(AgentInstance.status.in_([AgentStatus(s) for s in statuses]))
    else:
        conds.append(AgentInstance.status != AgentStatus.COMPLETED)
    if f.get("date_from"):
        conds.append(AgentInstance.started_at >= _naive_utc(f["date_from"]))
    if f.get("date_to"):
        conds.append(AgentInstance.started_at <= _naive_utc(f["date_to"]))
    if f.get("machine_ids"):
        conds.append(AgentInstance.machine_id.in_([UUID(m) for m in f["machine_ids"]]))
    if f.get("agent_types"):
        from shared.database.models import AgentType

        wanted = [str(a).strip().lower() for a in f["agent_types"]]
        conds.append(
            AgentInstance.agent_type_id.in_(
                select(AgentType.id).where(func.lower(AgentType.name).in_(wanted))
            )
        )
    return select(AgentInstance.id).where(*conds)


def _naive_utc(value: str | datetime) -> datetime:
    """`agent_instances.started_at` is a naive-UTC column; compare like for like."""
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def covered_instance(
    db: Session, grant: access.ShareGrant, instance_id: UUID
) -> AgentInstance | None:
    """The session, iff the grant reaches it. Re-checked on every call that
    takes a session id, even under a `session` link (defence in depth)."""
    return (
        db.query(AgentInstance)
        .options(
            joinedload(AgentInstance.agent_type), joinedload(AgentInstance.machine)
        )
        .filter(
            AgentInstance.id == instance_id,
            AgentInstance.id.in_(visible_instances_select(grant)),
        )
        .first()
    )


def _visible_tasks_query(db: Session, grant: access.ShareGrant):
    """Tasks this grant reaches: the project's, narrowed by the `tasks`
    filters — nothing at all unless the link carries that scope."""
    if not grant.covers("tasks"):
        return db.query(Task).filter(false())
    f = grant.scope_filters("tasks")
    query = db.query(Task).filter(Task.project_id == grant.project_id)
    if f.get("statuses"):
        query = query.filter(Task.status.in_(list(f["statuses"])))
    if f.get("assignee_ids"):
        query = query.filter(Task.assignee_id.in_([UUID(a) for a in f["assignee_ids"]]))
    if f.get("label_ids"):
        label_ids = [UUID(x) for x in f["label_ids"]]
        query = query.filter(Task.labels.any(TaskLabel.id.in_(label_ids)))
    return query


def covered_task(db: Session, grant: access.ShareGrant, task_id: UUID) -> Task | None:
    return _visible_tasks_query(db, grant).filter(Task.id == task_id).first()


# --- public side: serialization -------------------------------------------------


def _public_session_config(instance: AgentInstance) -> dict | None:
    cfg = instance.session_config
    if not isinstance(cfg, dict):
        return None
    out = {k: cfg[k] for k in _PUBLIC_SESSION_CONFIG_KEYS if cfg.get(k) is not None}
    return out or None


def _public_session(
    instance: AgentInstance,
    stats: dict,
    profiles: dict[UUID, AgentProfile],
    *,
    show_branch: bool = False,
) -> PublicSessionSummary:
    meta = (
        instance.instance_metadata
        if isinstance(instance.instance_metadata, dict)
        else {}
    )
    s = stats.get(instance.id, {})
    profile = (
        profiles.get(instance.agent_profile_id)
        if instance.agent_profile_id is not None
        else None
    )
    return PublicSessionSummary(
        id=instance.id,
        name=instance.name,
        agent_type_name=instance.agent_type.name if instance.agent_type else "Unknown",
        agent_profile=_agent_profile_principal(profile),
        status=instance.status,
        live_state=_live_state_for(instance),
        started_at=instance.started_at,
        ended_at=instance.ended_at,
        updated_at=instance.updated_at,
        worktree_name=(
            str(meta["worktree_name"])
            if show_branch and meta.get("worktree_name")
            else None
        ),
        session_config=_public_session_config(instance),
        message_count=int(s.get("message_count", 0) or 0),
        latest_message_at=s.get("latest_message_at"),
    )


def _profiles_for(
    db: Session, instances: list[AgentInstance]
) -> dict[UUID, AgentProfile]:
    ids = {i.agent_profile_id for i in instances if i.agent_profile_id is not None}
    if not ids:
        return {}
    rows = db.query(AgentProfile).filter(AgentProfile.id.in_(ids)).all()
    return {p.id: p for p in rows}


def public_session_summary(
    db: Session, grant: access.ShareGrant, instance: AgentInstance
) -> PublicSessionSummary:
    stats = _get_instance_message_stats(db, [instance.id])
    return _public_session(
        instance,
        stats,
        _profiles_for(db, [instance]),
        show_branch=grant.link.show_branch,
    )


def _public_project(project: Project) -> PublicProjectSummary:
    return PublicProjectSummary(
        id=project.id,
        name=project.name,
        key=project.key,
        color=project.color,
        icon=project.icon,
    )


def _public_message(msg: Message) -> PublicMessage:
    sender = msg.sender_user
    return PublicMessage(
        id=msg.id,
        content=msg.content,
        sender_type=msg.sender_type.value,
        sender_user_display_name=sender.display_name if sender else None,
        created_at=msg.created_at,
        requires_user_input=msg.requires_user_input,
        message_metadata=msg.message_metadata,
    )


# --- public side: reads ---------------------------------------------------------


def public_share(
    db: Session, grant: access.ShareGrant, viewer: User | None
) -> PublicShareResponse:
    """The page's first fetch: what this link is, who shared it, its target."""
    link = grant.link
    owner = db.get(User, link.created_by_user_id)
    session = None
    project = None
    if grant.kind == "session":
        instance = covered_instance(db, grant, grant.instance_id)  # type: ignore[arg-type]
        if instance is None:
            raise ShareTargetNotFoundError("Share not found")
        session = public_session_summary(db, grant, instance)
    else:
        row = db.get(Project, grant.project_id)
        if row is None:
            raise ShareTargetNotFoundError("Share not found")
        project = _public_project(row)
    return PublicShareResponse(
        id=link.id,
        kind=grant.kind,  # type: ignore[arg-type]
        scopes=sorted(grant.scopes),  # type: ignore[arg-type]
        audience=grant.audience,  # type: ignore[arg-type]
        allow_comments=grant.allow_comments,
        comments_available=bool(link.allow_comments),
        filters=grant.filters or None,
        created_at=link.created_at,
        expires_at=link.expires_at,
        owner=_user_principal(owner) if link.show_owner else None,
        viewer=_user_principal(viewer) if viewer is not None else None,
        viewer_is_owner=viewer is not None and viewer.id == link.created_by_user_id,
        session=session,
        project=project,
    )


def public_sessions(
    db: Session, grant: access.ShareGrant, *, limit: int, offset: int
) -> PublicSessionsPage:
    """The project-sessions list, newest first."""
    limit = max(1, min(limit, MAX_PUBLIC_SESSION_PAGE))
    query = (
        db.query(AgentInstance)
        .options(
            joinedload(AgentInstance.agent_type), joinedload(AgentInstance.machine)
        )
        .filter(AgentInstance.id.in_(visible_instances_select(grant)))
        .order_by(desc(AgentInstance.started_at))
    )
    total = query.order_by(None).count()
    rows = query.offset(offset).limit(limit).all()
    stats = _get_instance_message_stats(db, [r.id for r in rows])
    profiles = _profiles_for(db, rows)
    return PublicSessionsPage(
        items=[
            _public_session(r, stats, profiles, show_branch=grant.link.show_branch)
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(rows) < total,
    )


def public_messages(
    db: Session,
    grant: access.ShareGrant,
    instance_id: UUID,
    *,
    after: UUID | None,
    before: UUID | None,
    limit: int,
) -> PublicMessagesPage | None:
    """A page of one covered session's transcript, oldest-first.

    Three shapes, one endpoint: no cursor → the newest `limit` rows (first
    paint); `before=` → the `limit` rows older than that message (scroll-up);
    `after=` → everything newer than that message, capped (the 5 s poll — the
    watermark is what makes a steady-state poll a near-empty page, §9).
    Cursors are scoped to the instance so a cursor from another session is
    simply unknown. None when the session is not covered.
    """
    if covered_instance(db, grant, instance_id) is None:
        return None
    limit = max(1, min(limit, MAX_PUBLIC_MESSAGE_PAGE))
    base = (
        db.query(Message)
        .options(joinedload(Message.sender_user))
        .filter(Message.agent_instance_id == instance_id)
    )

    def cursor_of(message_id: UUID):
        return (
            db.query(Message.created_at, Message.id)
            .filter(Message.id == message_id, Message.agent_instance_id == instance_id)
            .first()
        )

    if after is not None:
        cursor = cursor_of(after)
        if cursor is None:
            return PublicMessagesPage(messages=[], has_more=False)
        rows = (
            base.filter(
                or_(
                    Message.created_at > cursor.created_at,
                    (Message.created_at == cursor.created_at)
                    & (Message.id > cursor.id),
                )
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        return PublicMessagesPage(
            messages=[_public_message(m) for m in rows[:limit]], has_more=has_more
        )

    query = base
    if before is not None:
        cursor = cursor_of(before)
        if cursor is None:
            return PublicMessagesPage(messages=[], has_more=False)
        query = query.filter(
            or_(
                Message.created_at < cursor.created_at,
                (Message.created_at == cursor.created_at) & (Message.id < cursor.id),
            )
        )
    rows = (
        query.order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    page = list(reversed(rows[:limit]))
    return PublicMessagesPage(
        messages=[_public_message(m) for m in page], has_more=has_more
    )


def public_attachment(
    db: Session, grant: access.ShareGrant, attachment_id: UUID
) -> MessageAttachment | None:
    """The attachment, iff its session is covered by the grant."""
    attachment = db.get(MessageAttachment, attachment_id)
    if attachment is None:
        return None
    if covered_instance(db, grant, attachment.agent_instance_id) is None:
        return None
    return attachment


def public_board(db: Session, grant: access.ShareGrant) -> PublicBoardResponse:
    """The board: the project, its visible tasks, and the label vocabulary the
    cards reference (so chips render with their colours)."""
    project = db.get(Project, grant.project_id)
    if project is None or not grant.covers("tasks"):
        raise ShareTargetNotFoundError("Share not found")
    tasks = (
        _visible_tasks_query(db, grant)
        .order_by(Task.position.asc(), Task.created_at.asc())
        .all()
    )
    labels = (
        db.query(TaskLabel)
        .filter(_project_vocabulary_filter(project))
        .order_by(TaskLabel.name.asc())
        .all()
    )
    return PublicBoardResponse(
        project=_public_project(project),
        tasks=public_tasks(db, grant, tasks),
        labels=[TaskLabelResponse.model_validate(label) for label in labels],
    )


# --- view accounting -------------------------------------------------------------

# (link id, client key) → last time we counted it. `view_count` is a "how
# many people opened this" number, not a request meter, so one client is one
# view per window no matter how often it polls. Per process, unbounded only by
# the sweep below.
_VIEW_WINDOW_SECONDS = 600
_recent_views: dict[tuple[UUID, str], float] = {}
_recent_views_lock = threading.Lock()


def should_count_view(link_id: UUID, client_key: str) -> bool:
    now = time.monotonic()
    key = (link_id, client_key)
    with _recent_views_lock:
        last = _recent_views.get(key)
        if last is not None and now - last < _VIEW_WINDOW_SECONDS:
            return False
        _recent_views[key] = now
        if len(_recent_views) > 20_000:
            stale = [
                k for k, t in _recent_views.items() if now - t >= _VIEW_WINDOW_SECONDS
            ]
            for k in stale:
                del _recent_views[k]
    return True


def record_share_view(link_id: UUID) -> None:
    """Bump `view_count` / `last_accessed_at`. Runs as a background task with
    its own session: the request's `get_db` session is closed by then, and a
    failure here must never surface on the page."""
    try:
        with SessionLocal() as db:
            db.execute(
                update(ShareLink)
                .where(ShareLink.id == link_id)
                .values(view_count=ShareLink.view_count + 1, last_accessed_at=_utcnow())
            )
            db.commit()
    except Exception:
        logger.exception("share view accounting failed for %s", link_id)
