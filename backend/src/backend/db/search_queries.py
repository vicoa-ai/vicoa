"""Workspace search queries — powers the dashboard's cmd+K palette.

Cross-entity substring search over the user's sessions (agent_instances),
tasks, and automations. Matching is LOWER(col) LIKE '%q%' with the pattern
lowered and escaped in Python; ranking is a tiered CASE (exact > prefix >
contains > secondary field > message body) then recency. All queries are
user-scoped.

The session search runs as two queries, not one OR: name/project matches come
from the user's agent_instances rows (a few thousand rows, milliseconds), and
the message-content tier — strictly the lowest rank — only runs for the slots
those didn't fill. Folding the message EXISTS into the same query is what
melted in production: the planner hashed it into a full seq scan of every
user's messages. The message tier instead scans a recency-bounded window (the
newest messages of the most recently active sessions), so its cost is capped
structurally rather than growing with the whole platform's message volume.
"""

from uuid import UUID

from sqlalchemy import case, func, lateral, or_, select, true
from sqlalchemy.orm import Session, joinedload

from shared.database import AgentInstance, Automation, Message, Task
from shared.database.enums import AgentStatus

from .queries import _get_instance_message_stats

# Snippet window: characters of context kept before/after the first hit.
SNIPPET_BEFORE = 40
SNIPPET_AFTER = 80

# The message tier never scans the whole messages table: it looks only at the
# newest messages of the most recently active sessions, with the LIKE applied
# outside the per-session limit, so the scanned set is structurally capped at
# FALLBACK_RECENT_INSTANCES sessions times FALLBACK_MESSAGES_PER_INSTANCE
# messages each — independent of how common the search term is.
FALLBACK_RECENT_INSTANCES = 50
FALLBACK_MESSAGES_PER_INSTANCE = 200


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def extract_snippet(text: str, query: str) -> str:
    """A single-line window of text around the first case-insensitive hit."""
    flattened = " ".join(text.split())
    idx = flattened.lower().find(query.lower())
    if idx < 0:
        end = SNIPPET_BEFORE + SNIPPET_AFTER
        return flattened[:end] + ("…" if len(flattened) > end else "")
    start = max(0, idx - SNIPPET_BEFORE)
    end = min(len(flattened), idx + len(query) + SNIPPET_AFTER)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(flattened) else ""
    return prefix + flattened[start:end] + suffix


def _message_tier_recent(
    db: Session,
    user_id: UUID,
    contains: str,
    exclude_ids: set[UUID],
    limit: int,
) -> list[tuple[UUID, str]]:
    """Recency-bounded message matches. The LIKE filter sits OUTSIDE the
    lateral limit, so the scanned set is structurally capped at
    FALLBACK_RECENT_INSTANCES sessions times each one's
    FALLBACK_MESSAGES_PER_INSTANCE newest messages (~30ms on the heaviest
    production account), instead of "scan until enough matches"."""
    recent = (
        select(AgentInstance.id)
        .where(
            AgentInstance.user_id == user_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .order_by(AgentInstance.updated_at.desc())
        .limit(FALLBACK_RECENT_INSTANCES)
        .subquery("recent_instances")
    )
    per_instance = lateral(
        select(
            Message.agent_instance_id.label("instance_id"),
            Message.content.label("content"),
            Message.created_at.label("created_at"),
        )
        .where(Message.agent_instance_id == recent.c.id)
        .order_by(Message.created_at.desc())
        .limit(FALLBACK_MESSAGES_PER_INSTANCE)
    )
    rows = db.execute(
        select(per_instance.c.instance_id, per_instance.c.content)
        .select_from(recent.join(per_instance, true()))
        .where(func.lower(per_instance.c.content).like(contains, escape="\\"))
        .order_by(per_instance.c.created_at.desc())
    ).all()
    hits: list[tuple[UUID, str]] = []
    seen: set[UUID] = set(exclude_ids)
    for row in rows:
        if row.instance_id in seen:
            continue
        seen.add(row.instance_id)
        hits.append((row.instance_id, row.content))
        if len(hits) >= limit:
            break
    return hits


def search_sessions(db: Session, user_id: UUID, query: str, limit: int) -> list[dict]:
    """Sessions matched by name, project path, or message content."""
    lowered = query.lower()
    contains = f"%{_escape_like(lowered)}%"
    prefix = f"{_escape_like(lowered)}%"

    name_match = func.lower(AgentInstance.name).like(contains, escape="\\")
    project_match = func.lower(AgentInstance.project).like(contains, escape="\\")
    rank = case(
        (func.lower(AgentInstance.name) == lowered, 0),
        (func.lower(AgentInstance.name).like(prefix, escape="\\"), 1),
        (name_match, 2),
        else_=3,
    )

    instances = (
        db.query(AgentInstance)
        .options(joinedload(AgentInstance.user_agent))
        .filter(
            AgentInstance.user_id == user_id,
            AgentInstance.status != AgentStatus.DELETED,
            or_(name_match, project_match),
        )
        .order_by(rank, AgentInstance.updated_at.desc())
        .limit(limit)
        .all()
    )

    # Message tier — strictly below every name/project tier, so it only runs
    # for the slots those left open, and its hits carry their matched content
    # (no second scan to recover snippets).
    matched_ids = {instance.id for instance in instances}
    remaining = limit - len(instances)
    message_hits: list[tuple[UUID, str]] = []
    if remaining > 0:
        message_hits = _message_tier_recent(
            db, user_id, contains, matched_ids, remaining
        )
    if message_hits:
        by_id = {
            instance.id: instance
            for instance in db.query(AgentInstance)
            .options(joinedload(AgentInstance.user_agent))
            .filter(AgentInstance.id.in_([hit_id for hit_id, _ in message_hits]))
            .all()
        }
    else:
        by_id = {}

    instance_ids = [instance.id for instance in instances] + [
        hit_id for hit_id, _ in message_hits
    ]
    stats = _get_instance_message_stats(db, instance_ids)

    results = []
    for instance in instances:
        name = instance.name or ""
        match_source = "name" if lowered in name.lower() else "project"
        results.append(
            _session_row(instance, stats, match_source=match_source, snippet=None)
        )
    for hit_id, content in message_hits:
        instance = by_id.get(hit_id)
        if instance is None:
            continue
        results.append(
            _session_row(
                instance,
                stats,
                match_source="message",
                snippet=extract_snippet(content, query),
            )
        )
    return results


def _session_row(
    instance: AgentInstance, stats: dict, *, match_source: str, snippet: str | None
) -> dict:
    instance_stats = stats.get(instance.id, {})
    return {
        "id": str(instance.id),
        "name": instance.name,
        "agent_type_name": instance.user_agent.name if instance.user_agent else None,
        "status": instance.status,
        "project": instance.project,
        "started_at": instance.started_at,
        "latest_message": instance_stats.get("latest_message"),
        "latest_message_at": instance_stats.get("latest_message_at"),
        "match_source": match_source,
        "snippet": snippet,
    }


def search_tasks(db: Session, user_id: UUID, query: str, limit: int) -> list[dict]:
    """Tasks matched by title or description; open tasks rank above closed."""
    lowered = query.lower()
    contains = f"%{_escape_like(lowered)}%"
    prefix = f"{_escape_like(lowered)}%"

    title_match = func.lower(Task.title).like(contains, escape="\\")
    description_match = func.lower(func.coalesce(Task.description, "")).like(
        contains, escape="\\"
    )
    rank = case(
        (func.lower(Task.title) == lowered, 0),
        (func.lower(Task.title).like(prefix, escape="\\"), 1),
        (title_match, 2),
        else_=3,
    )
    closed_rank = case((Task.status.in_(["done", "cancelled"]), 1), else_=0)

    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, or_(title_match, description_match))
        .order_by(rank, closed_rank, Task.updated_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for task in tasks:
        matched_title = lowered in task.title.lower()
        results.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "project_id": task.project_id,
                "updated_at": task.updated_at,
                "match_source": "title" if matched_title else "description",
                "snippet": extract_snippet(task.description, query)
                if not matched_title and task.description
                else None,
            }
        )
    return results


def search_automations(
    db: Session, user_id: UUID, query: str, limit: int
) -> list[dict]:
    """Automations matched by title or prompt."""
    lowered = query.lower()
    contains = f"%{_escape_like(lowered)}%"
    prefix = f"{_escape_like(lowered)}%"

    title_match = func.lower(Automation.title).like(contains, escape="\\")
    prompt_match = func.lower(Automation.prompt).like(contains, escape="\\")
    rank = case(
        (func.lower(Automation.title) == lowered, 0),
        (func.lower(Automation.title).like(prefix, escape="\\"), 1),
        (title_match, 2),
        else_=3,
    )

    automations = (
        db.query(Automation)
        .filter(Automation.user_id == user_id, or_(title_match, prompt_match))
        .order_by(rank, Automation.updated_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for automation in automations:
        matched_title = lowered in automation.title.lower()
        results.append(
            {
                "id": automation.id,
                "title": automation.title,
                "enabled": automation.enabled,
                "schedule_kind": automation.schedule_kind,
                "next_run_at": automation.next_run_at,
                "match_source": "title" if matched_title else "prompt",
                "snippet": extract_snippet(automation.prompt, query)
                if not matched_title
                else None,
            }
        )
    return results
