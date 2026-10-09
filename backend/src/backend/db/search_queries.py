"""Workspace search queries — powers the dashboard's cmd+K palette.

Cross-entity substring search over the user's sessions (agent_instances),
tasks, and automations. Matching is LOWER(col) LIKE '%q%' with the pattern
lowered and escaped in Python; ranking is a tiered CASE (exact > prefix >
contains > secondary field > message body) then recency. All queries are
user-scoped. A task also matches by its "VIC-42" identifier, which appears
nowhere in its text.

The session search runs as two queries, not one OR: name/project matches come
from the user's agent_instances rows (a few thousand rows, milliseconds), and
the message-content tier — strictly the lowest rank — only runs for the slots
those didn't fill. Folding the message EXISTS into the same query is what
melted in production: the planner hashed it into a full seq scan of every
user's messages. The message tier instead scans a recency-bounded window (the
newest messages of the most recently active sessions), so its cost is capped
structurally rather than growing with the whole platform's message volume.
"""

import re
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    String,
    and_,
    case,
    cast,
    false,
    func,
    lateral,
    or_,
    select,
    true,
)
from sqlalchemy.orm import Session, joinedload

from shared.database import AgentInstance, Automation, Message, Project, Task
from shared.database.enums import AgentStatus

from .queries import _get_instance_message_stats
from .task_queries import owned_task_filter
from .task_serializers import serialize_tasks

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


# A (lowercased) query shaped like a task identifier, or a prefix of one:
# "vic", "vic-", "vic-3", "vic-38". The key half is bounded like
# `task_identity._IDENTIFIER`; the 1-char floor lets "#v" start narrowing.
_IDENTIFIER_QUERY = re.compile(r"^([a-z][a-z0-9]{0,7})(?:(-)([0-9]{0,9}))?$")


def _identifier_conditions(
    user_id: UUID, lowered: str
) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """``(exact, partial)`` task filters for a query shaped like "vic-38".

    The identifier is what a task is called everywhere else (the board, the
    detail header, `vicoa task ls`), yet it is nowhere in the title, so title
    matching alone can never find `#VIC-38`. ``partial`` also covers the
    keystrokes on the way there ("vic", "vic-", "vic-3"), so the `#` panel
    narrows to that project's tasks instead of going blank until the number is
    complete. Both are ``false()`` for any other query. Shared by the `#`
    picker and the cmd+K search.
    """
    match = _IDENTIFIER_QUERY.match(lowered)
    if match is None:
        return false(), false()
    key, dash, digits = match.group(1).upper(), match.group(2), match.group(3)
    # Keys and digits are alphanumeric, so neither LIKE needs escaping.
    project_key = func.upper(Project.key)
    key_match = project_key == key if dash else project_key.like(f"{key}%")
    in_project = Task.project_id.in_(
        select(Project.id).where(Project.user_id == user_id, key_match)
    )
    if not digits:
        return false(), in_project
    return (
        and_(in_project, Task.number == int(digits)),
        and_(in_project, cast(Task.number, String).like(f"{digits}%")),
    )


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
        .options(joinedload(AgentInstance.agent_type))
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
            .options(joinedload(AgentInstance.agent_type))
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
        "agent_type_name": instance.agent_type.name if instance.agent_type else None,
        "status": instance.status,
        "project": instance.project,
        "machine_id": instance.machine_id,
        "started_at": instance.started_at,
        "latest_message": instance_stats.get("latest_message"),
        "latest_message_at": instance_stats.get("latest_message_at"),
        "match_source": match_source,
        "snippet": snippet,
    }


def search_tasks(db: Session, user_id: UUID, query: str, limit: int) -> list[dict]:
    """Tasks matched by title, description or identifier; open tasks rank above
    closed, except that a full "VIC-42" names one task outright and leads."""
    lowered = query.lower()
    contains = f"%{_escape_like(lowered)}%"
    prefix = f"{_escape_like(lowered)}%"

    title_match = func.lower(Task.title).like(contains, escape="\\")
    description_match = func.lower(func.coalesce(Task.description, "")).like(
        contains, escape="\\"
    )
    # Only once the dash is typed: unlike the `#` panel, this is a text search,
    # and a bare word like "fix" would otherwise pull in every task of a
    # project keyed FIX..., burying the text matches.
    exact_id, partial_id = (
        _identifier_conditions(user_id, lowered)
        if "-" in lowered
        else (false(), false())
    )
    rank = case(
        (exact_id, 0),
        (func.lower(Task.title) == lowered, 0),
        (or_(func.lower(Task.title).like(prefix, escape="\\"), partial_id), 1),
        (title_match, 2),
        else_=3,
    )
    closed_rank = case((Task.status.in_(["done", "cancelled"]), 1), else_=0)

    tasks = (
        db.query(Task)
        .filter(
            owned_task_filter(user_id),
            or_(title_match, description_match, partial_id),
        )
        .order_by(rank, closed_rank, Task.updated_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for task, response in zip(tasks, serialize_tasks(db, tasks)):
        snippet = None
        if lowered in task.title.lower():
            match_source = "title"
        elif task.description and lowered in task.description.lower():
            match_source = "description"
            snippet = extract_snippet(task.description, query)
        else:
            match_source = "identifier"
        results.append(
            {
                "id": task.id,
                "identifier": response.identifier,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "project_id": task.project_id,
                "updated_at": task.updated_at,
                "match_source": match_source,
                "snippet": snippet,
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
