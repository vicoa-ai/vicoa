"""Task timeline — comments, reactions, activity, subscribers (collab §3.5).

Kept out of `task_queries` because that module is already the projects+tasks
CRUD surface and this is a second, differently-shaped concern.

**Scoping.** None of these tables carries `user_id` — a comment's author need
not be the task's owner once sharing lands, so there is no single owning user to
filter on. Every entry point here therefore takes an already-resolved `Task`
that the caller obtained through the user-scoped `task_queries.get_task`, which
is what keeps the house rule intact.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from shared.database import (
    Task,
    TaskActivity,
    TaskComment,
    TaskReaction,
    TaskSubscriber,
    User,
)
from shared.database.agent_profile_models import AgentProfile
from shared.database.reactions import is_emoji

from ..models import (
    MAX_NAMED_REACTORS,
    PrincipalResponse,
    TaskActivityResponse,
    TaskCommentResponse,
    TaskReactionSummary,
    TaskTimelineResponse,
)

logger = logging.getLogger(__name__)

# A principal reference as it appears on a row: ('user' | 'agent', id).
PrincipalRef = tuple[str, UUID]


class CommentNotFoundError(Exception):
    """The comment doesn't exist, isn't on this task, or is already deleted."""


class UnknownReactionError(Exception):
    """The reaction value isn't an emoji."""


class AssigneeNotFoundError(Exception):
    """The assignee isn't one of this user's users/agent profiles."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Principals -------------------------------------------------------------


def resolve_principals(
    db: Session, refs: set[PrincipalRef]
) -> dict[PrincipalRef, PrincipalResponse]:
    """Batch-resolve (type, id) pairs to renderable principals.

    Two queries for a whole page rather than one per row. A reference that no
    longer resolves (deleted user, deleted agent profile) is returned as a
    named-but-idless principal so the thread stays readable instead of showing
    a blank author.
    """
    resolved: dict[PrincipalRef, PrincipalResponse] = {}
    user_ids = {rid for kind, rid in refs if kind == "user"}
    agent_ids = {rid for kind, rid in refs if kind == "agent"}

    if user_ids:
        for user in db.query(User).filter(User.id.in_(user_ids)).all():
            resolved[("user", user.id)] = PrincipalResponse(
                type="user",
                id=user.id,
                # display_name only — an email must never reach a shared or
                # public surface (§10.4), and this serializer feeds both.
                name=user.display_name,
                avatar_image_uri=user.avatar_image_uri,
                emoji=user.avatar_emoji,
                updated_at=user.updated_at,
            )
    if agent_ids:
        for profile in (
            db.query(AgentProfile).filter(AgentProfile.id.in_(agent_ids)).all()
        ):
            resolved[("agent", profile.id)] = PrincipalResponse(
                type="agent",
                id=profile.id,
                name=profile.name,
                avatar_image_uri=profile.avatar_image_uri,
                emoji=profile.emoji,
                updated_at=profile.updated_at,
            )

    for ref in refs:
        if ref not in resolved:
            kind, _ = ref
            resolved[ref] = PrincipalResponse(
                type="user" if kind == "user" else "agent",
                id=None,
                name="Deleted user" if kind == "user" else "Deleted agent",
            )
    return resolved


# --- Reactions --------------------------------------------------------------


def _reaction_summaries(
    db: Session, user_id: UUID, targets: list[tuple[str, UUID]]
) -> dict[tuple[str, UUID], list[TaskReactionSummary]]:
    """Counts per (target, emoji), who reacted, and whether `user_id` did.

    The reactor names come back in the same aggregate rather than as a second
    query per pill: a page can carry dozens of pills, and "who reacted" is a
    hover away on every one of them.
    """
    if not targets:
        return {}
    target_ids = [tid for _, tid in targets]
    rows = db.execute(
        select(
            TaskReaction.target_type,
            TaskReaction.target_id,
            TaskReaction.emoji,
            func.count().label("n"),
            func.bool_or(TaskReaction.user_id == user_id).label("mine"),
            # Oldest first, so the order a tooltip reads in is the order people
            # actually reacted rather than whatever the planner returns.
            func.array_agg(
                aggregate_order_by(TaskReaction.user_id, TaskReaction.created_at)
            ).label("user_ids"),
        )
        .where(TaskReaction.target_id.in_(target_ids))
        .group_by(TaskReaction.target_type, TaskReaction.target_id, TaskReaction.emoji)
    ).all()

    # One principal lookup for every reactor on the page, not one per pill.
    named: set[PrincipalRef] = set()
    for row in rows:
        for reactor_id in row.user_ids[:MAX_NAMED_REACTORS]:
            named.add(("user", reactor_id))
    principals = resolve_principals(db, named) if named else {}

    out: dict[tuple[str, UUID], list[TaskReactionSummary]] = {}
    for target_type, target_id, emoji, count, mine, user_ids in rows:
        out.setdefault((target_type, target_id), []).append(
            TaskReactionSummary(
                emoji=emoji,
                count=int(count),
                reacted=bool(mine),
                reactors=[
                    principals[("user", reactor_id)]
                    for reactor_id in user_ids[:MAX_NAMED_REACTORS]
                ],
            )
        )
    # Most-used first, then by emoji so ties don't shuffle between renders.
    # There is no offered-set order to sort by any more — reactions are open.
    for summaries in out.values():
        summaries.sort(key=lambda s: (-s.count, s.emoji))
    return out


def toggle_reaction(
    db: Session, user_id: UUID, target_type: str, target_id: UUID, emoji: str
) -> bool:
    """Add the reaction, or remove it if it's already there. True = now on."""
    if not is_emoji(emoji):
        raise UnknownReactionError(emoji)
    existing = (
        db.query(TaskReaction)
        .filter(
            TaskReaction.target_type == target_type,
            TaskReaction.target_id == target_id,
            TaskReaction.user_id == user_id,
            TaskReaction.emoji == emoji,
        )
        .first()
    )
    if existing is not None:
        db.delete(existing)
        db.commit()
        return False
    db.add(
        TaskReaction(
            target_type=target_type,
            target_id=target_id,
            user_id=user_id,
            emoji=emoji,
        )
    )
    db.commit()
    return True


# --- Subscribers ------------------------------------------------------------


def subscribe(db: Session, task_id: UUID, user_id: UUID, reason: str) -> None:
    """Idempotent auto-subscribe. The first reason wins — an explicit 'manual'
    is never downgraded by a later automatic one."""
    existing = (
        db.query(TaskSubscriber)
        .filter(TaskSubscriber.task_id == task_id, TaskSubscriber.user_id == user_id)
        .first()
    )
    if existing is not None:
        return
    db.add(TaskSubscriber(task_id=task_id, user_id=user_id, reason=reason))


# --- Comments ---------------------------------------------------------------


def create_comment(db: Session, task: Task, user_id: UUID, body: str) -> TaskComment:
    comment = TaskComment(
        task_id=task.id,
        project_id=task.project_id,
        author_type="user",
        author_id=user_id,
        body=body,
    )
    db.add(comment)
    subscribe(db, task.id, user_id, "commenter")
    db.commit()
    return comment


def _own_comment(db: Session, task: Task, comment_id: UUID, user_id: UUID):
    comment = (
        db.query(TaskComment)
        .filter(TaskComment.id == comment_id, TaskComment.task_id == task.id)
        .first()
    )
    if comment is None or comment.deleted_at is not None:
        raise CommentNotFoundError("Comment not found")
    # Editing and deleting are the author's alone — the task owner does not
    # inherit the right to rewrite someone else's words.
    if comment.author_type != "user" or comment.author_id != user_id:
        raise CommentNotFoundError("Comment not found")
    return comment


def update_comment(
    db: Session, task: Task, comment_id: UUID, user_id: UUID, body: str
) -> TaskComment:
    comment = _own_comment(db, task, comment_id, user_id)
    comment.body = body
    comment.edited_at = _utcnow()
    db.commit()
    return comment


def delete_comment(db: Session, task: Task, comment_id: UUID, user_id: UUID) -> None:
    """Soft delete: the row stays so the thread keeps its shape and reactions
    and cross-references don't dangle; the text stops being served."""
    comment = _own_comment(db, task, comment_id, user_id)
    comment.deleted_at = _utcnow()
    db.commit()


# --- Timeline ---------------------------------------------------------------


def build_timeline(db: Session, task: Task, user_id: UUID) -> TaskTimelineResponse:
    """Everything the task-detail timeline renders, in one round trip."""
    comments = (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task.id)
        .order_by(TaskComment.created_at.asc())
        .all()
    )
    activity = (
        db.query(TaskActivity)
        .filter(TaskActivity.task_id == task.id)
        .order_by(TaskActivity.created_at.asc())
        .all()
    )

    refs: set[PrincipalRef] = {(c.author_type, c.author_id) for c in comments}
    refs |= {
        (str(a.actor_type), a.actor_id)
        for a in activity
        if a.actor_type in ("user", "agent") and a.actor_id is not None
    }
    principals = resolve_principals(db, refs)
    reactions = _reaction_summaries(
        db, user_id, [("comment", c.id) for c in comments] + [("task", task.id)]
    )

    return TaskTimelineResponse(
        reactions=reactions.get(("task", task.id), []),
        comments=[
            TaskCommentResponse(
                id=c.id,
                task_id=c.task_id,
                author=principals[(c.author_type, c.author_id)],
                body=None if c.deleted_at else c.body,
                kind="system" if c.kind == "system" else "comment",
                reactions=reactions.get(("comment", c.id), []),
                created_at=c.created_at,
                edited_at=c.edited_at,
                deleted_at=c.deleted_at,
            )
            for c in comments
        ],
        activity=[
            TaskActivityResponse(
                id=a.id,
                actor=(
                    principals.get((str(a.actor_type), a.actor_id))
                    if a.actor_id is not None
                    else (
                        PrincipalResponse(type="system", name="Vicoa")
                        if a.actor_type == "system"
                        else None
                    )
                ),
                action=a.action,
                details=a.details or {},
                created_at=a.created_at,
            )
            for a in activity
        ],
    )
