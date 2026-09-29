"""Tell the relay when someone's access changed (collaboration §9).

Every write that gives or takes away access — a project grant, a session
share, a team membership that carries team grants — calls `notify_access_changed`
with the people it affects, *inside* its transaction. The notification is
registered with `after_commit`, so it goes out only if the change actually
lands, and the query layer is the one place it has to be remembered rather
than every route that happens to reach it.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.database.collab_models import TeamMember
from shared.websocket.in_tx import after_commit

from ..broadcast_bridge import post_access_changed


def team_member_ids(db: Session, team_id: UUID | None) -> set[UUID]:
    """Every active member of a team — who a team grant reaches."""
    if team_id is None:
        return set()
    return {
        row[0]
        for row in db.execute(
            select(TeamMember.user_id).where(
                TeamMember.team_id == team_id,
                TeamMember.status == "active",
                TeamMember.user_id.is_not(None),
            )
        )
    }


def principal_user_ids(
    db: Session, principal_type: str, principal_id: UUID | None
) -> set[UUID]:
    """The accounts a grant to this principal reaches. A pending email grant
    (no principal yet) reaches nobody who could be connected."""
    if principal_id is None:
        return set()
    if principal_type == "team":
        return team_member_ids(db, principal_id)
    return {principal_id}


def notify_access_changed(
    db: Session,
    user_ids: Iterable[UUID | None],
    *,
    project_id: UUID | None = None,
    instance_id: UUID | None = None,
) -> None:
    """Register the relay notification for the current transaction.

    Call before the commit that makes the change: the ids are resolved now,
    and the POST fires on that commit (never on a rollback).
    """
    ids = sorted({str(u) for u in user_ids if u is not None})
    if not ids:
        return
    project = str(project_id) if project_id else None
    instance = str(instance_id) if instance_id else None
    after_commit(
        db,
        lambda: post_access_changed(ids, project_id=project, instance_id=instance),
    )
