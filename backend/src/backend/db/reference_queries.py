"""`#` reference lookups — the composer's Vicoa-entity picker.

`@` browses the filesystem; `#` browses the workspace: the user's live
sessions, their tasks and their automations. Two calls back it.

* :func:`list_reference_candidates` fills the panel. Title-only matching, one
  query per kind, and an *empty* query is answered with "what is live and
  recent" rather than a blank panel — `#` on its own has to be useful.
* :func:`get_reference` expands one pick into the block of text that actually
  reaches the agent. The client fetches it at **pick** time, not at send time,
  so sending never waits on the network and a dead reference degrades to its
  token instead of blocking the message.

Owner-scoped throughout, like the cmd+K search this sits beside: `#` reaches
your own workspace, never a collaborator's board. There is no new table here —
a reference is a pointer to a row that already exists, and the session ↔ task
half of it rides the `agent_instances.task_id` column the tasks plan already
added (see `link_instance_to_task`).
"""

import re
from collections import defaultdict
from uuid import UUID

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload

from shared.database import AgentInstance, Automation, Project, Task
from shared.database.enums import AgentStatus
from shared.database.project_matching import canonical_path, path_at_or_under
from shared.database.task_models import ProjectDirectory

from .queries import CLOSED_STATUSES, _get_instance_message_stats
from .search_queries import _escape_like
from .task_serializers import serialize_task, serialize_tasks

# A task is "closed" for ranking/default-list purposes in exactly the words the
# board uses. Kept local rather than imported so this module doesn't depend on
# the task API's literals moving.
CLOSED_TASK_STATUSES = ("done", "cancelled")

# Per-kind cap in the panel. The three groups share one keyboard list, so the
# ceiling that matters is the total (3 x this) staying scannable without a
# scroll marathon.
GROUP_LIMIT = 8

# Payload caps for an expanded reference. A reference is context the user asked
# for, not a transcript dump: enough to work from, bounded so five of them
# can't blow the agent's first turn.
MAX_DESCRIPTION_CHARS = 2000
MAX_PROMPT_CHARS = 2000
MAX_LAST_MESSAGE_CHARS = 500

# Token slugs stay short enough to read inline mid-sentence.
MAX_TOKEN_CHARS = 32

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify_token(label: str, fallback: str) -> str:
    """The space-free text that follows `#` in the composer.

    Whitespace in a token would break the "token ends at the first space" rule
    every mention parser here shares, so a multi-word title becomes
    `fix-the-diff-editor`. Purely cosmetic: what the message carries is the
    slug, what the reference *resolves* by is the id the client kept beside it.
    """
    slug = _SLUG_STRIP.sub("-", label.lower()).strip("-")
    if not slug:
        return fallback
    return slug[:MAX_TOKEN_CHARS].rstrip("-") or fallback


def _truncate(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    flattened = text.strip()
    if len(flattened) <= limit:
        return flattened
    return flattened[:limit].rstrip() + "…"


def _short_id(value: UUID) -> str:
    return str(value)[:8]


# ---------------------------------------------------------------------------
# Candidates (the panel)
# ---------------------------------------------------------------------------


def _session_candidates(
    db: Session,
    user_id: UUID,
    lowered: str,
    limit: int,
    exclude_session_id: UUID | None,
) -> list[dict]:
    """Sessions that are still running — "another *active* session".

    Closed runs are excluded outright rather than ranked last: an account
    accumulates thousands of them, and a finished session is not something you
    hand the current one as live context.
    """
    query = (
        db.query(AgentInstance)
        .options(joinedload(AgentInstance.agent_type))
        .filter(
            AgentInstance.user_id == user_id,
            AgentInstance.status != AgentStatus.DELETED,
            AgentInstance.status.notin_(CLOSED_STATUSES),
        )
    )
    if exclude_session_id is not None:
        query = query.filter(AgentInstance.id != exclude_session_id)

    if lowered:
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
        query = query.filter(or_(name_match, project_match)).order_by(
            rank, AgentInstance.updated_at.desc()
        )
    else:
        query = query.order_by(AgentInstance.updated_at.desc())

    rows = query.limit(limit).all()
    return [
        {
            "kind": "session",
            "id": str(instance.id),
            "label": instance.name or f"Session {_short_id(instance.id)}",
            "token": slugify_token(
                instance.name or "", f"session-{_short_id(instance.id)}"
            ),
            "project_id": instance.project_id,
            # The row is one line, and its trailing slot names *where* the run
            # lives. `_attach_projects` upgrades this to the project's name
            # when the session is filed under one; the raw path is what's left
            # for a checkout no project is set up for.
            "meta": instance.project,
            "status": str(instance.status.value),
        }
        for instance in rows
    ]


def _task_candidates(
    db: Session, user_id: UUID, lowered: str, limit: int
) -> list[dict]:
    """Tasks matched by title.

    An empty query lists only *open* tasks — `#` with nothing typed should read
    as "what am I working on". A typed query widens to the whole backlog with
    done/cancelled ranked last, so "how did we do VIC-12" still resolves.
    """
    query = db.query(Task).filter(Task.user_id == user_id)
    closed_rank = case((Task.status.in_(CLOSED_TASK_STATUSES), 1), else_=0)

    if lowered:
        contains = f"%{_escape_like(lowered)}%"
        prefix = f"{_escape_like(lowered)}%"
        title_match = func.lower(Task.title).like(contains, escape="\\")
        rank = case(
            (func.lower(Task.title) == lowered, 0),
            (func.lower(Task.title).like(prefix, escape="\\"), 1),
            else_=2,
        )
        query = query.filter(title_match).order_by(
            closed_rank, rank, Task.updated_at.desc()
        )
    else:
        query = query.filter(Task.status.notin_(CLOSED_TASK_STATUSES)).order_by(
            Task.updated_at.desc()
        )

    tasks = query.limit(limit).all()
    return [
        {
            "kind": "task",
            "id": str(response.id),
            "label": response.title,
            # `VIC-42` when the task has one: shorter than any slug, and it is
            # what `vicoa task get` and the web route already accept.
            "token": response.identifier
            or slugify_token(response.title, f"task-{_short_id(response.id)}"),
            "project_id": task.project_id,
            # Filled from the project by `_attach_projects`; an unfiled task
            # simply has no trailing text.
            "meta": None,
            # Only the real key, never the slug fallback: a trailing
            # "fix-the-drift" would just repeat the title it sits next to.
            "identifier": response.identifier,
            "status": response.status,
        }
        for task, response in zip(tasks, serialize_tasks(db, tasks))
    ]


def _automation_candidates(
    db: Session, user_id: UUID, lowered: str, limit: int
) -> list[dict]:
    """Automations matched by title; an empty query lists the enabled ones."""
    query = db.query(Automation).filter(Automation.user_id == user_id)
    if lowered:
        contains = f"%{_escape_like(lowered)}%"
        prefix = f"{_escape_like(lowered)}%"
        title_match = func.lower(Automation.title).like(contains, escape="\\")
        rank = case(
            (func.lower(Automation.title) == lowered, 0),
            (func.lower(Automation.title).like(prefix, escape="\\"), 1),
            else_=2,
        )
        query = query.filter(title_match).order_by(
            Automation.enabled.desc(), rank, Automation.updated_at.desc()
        )
    else:
        query = query.filter(Automation.enabled.is_(True)).order_by(
            Automation.updated_at.desc()
        )

    rows = query.limit(limit).all()
    project_ids = _automation_project_ids(db, user_id, rows)
    return [
        {
            "kind": "automation",
            "id": str(automation.id),
            "label": automation.title,
            "token": slugify_token(
                automation.title, f"automation-{_short_id(automation.id)}"
            ),
            "project_id": project_ids.get(automation.id),
            # Folder, not schedule: it is the field that disambiguates, and the
            # schedule is in the expanded block the agent reads anyway.
            "meta": automation.directory,
            "status": "enabled" if automation.enabled else "paused",
        }
        for automation in rows
    ]


def _automation_project_ids(
    db: Session, user_id: UUID, automations: list[Automation]
) -> dict[UUID, UUID]:
    """Folder → project for each automation, in one query.

    An automation has no ``project_id`` column (a session gets one stamped at
    registration; an automation is only a recipe for one), so this re-runs the
    matcher's tier 2 by hand: the automation's directory at or under a
    ``project_directories`` row on the same machine, longest path winning.
    Deliberately *not* ``resolve_project_id_for_session`` per row — that is
    several queries each, and this endpoint answers a keystroke.
    """
    if not automations:
        return {}
    rows = db.query(
        ProjectDirectory.project_id,
        ProjectDirectory.machine_id,
        ProjectDirectory.local_path,
    ).filter(ProjectDirectory.user_id == user_id)
    by_machine: dict[UUID, list[tuple[str, UUID]]] = defaultdict(list)
    for project_id, machine_id, local_path in rows:
        by_machine[machine_id].append((canonical_path(local_path, None), project_id))
    if not by_machine:
        return {}

    matched: dict[UUID, UUID] = {}
    for automation in automations:
        directory = canonical_path(automation.directory, None)
        best: tuple[str, UUID] | None = None
        for local_path, project_id in by_machine.get(automation.machine_id, ()):
            if not path_at_or_under(directory, local_path):
                continue
            if best is None or len(local_path) > len(best[0]):
                best = (local_path, project_id)
        if best is not None:
            matched[automation.id] = best[1]
    return matched


def _attach_projects(db: Session, items: list[dict]) -> None:
    """Resolve every row's ``project_id`` into the payload the icon needs.

    One query for the whole panel, whatever the mix of kinds. Where a project
    resolved, its name replaces the fallback ``meta`` — a session reads
    "Vicoa", not "~/projects/vicoa", once it is filed under one.
    """
    ids = {item["project_id"] for item in items if item.get("project_id")}
    projects: dict[UUID, dict] = {}
    if ids:
        for row in db.query(
            Project.id,
            Project.name,
            Project.icon,
            Project.icon_image_uri,
            Project.updated_at,
        ).filter(Project.id.in_(ids)):
            projects[row.id] = {
                "id": str(row.id),
                "name": row.name,
                "icon": row.icon,
                "icon_image_uri": row.icon_image_uri,
                "updated_at": row.updated_at,
            }
    for item in items:
        project = projects.get(item.pop("project_id", None))
        item["project"] = project
        if project is not None:
            item["meta"] = project["name"]


def list_reference_candidates(
    db: Session,
    user_id: UUID,
    *,
    query: str,
    limit: int = GROUP_LIMIT,
    exclude_session_id: UUID | None = None,
) -> list[dict]:
    """One flat, kind-ordered list — sessions, then tasks, then automations.

    Flat because the panel is a single keyboard list; the client draws a group
    header wherever `kind` changes, which keeps arrow-key navigation trivial.
    """
    lowered = query.strip().lower()
    items = [
        *_session_candidates(db, user_id, lowered, limit, exclude_session_id),
        *_task_candidates(db, user_id, lowered, limit),
        *_automation_candidates(db, user_id, lowered, limit),
    ]
    _attach_projects(db, items)
    return items


# ---------------------------------------------------------------------------
# Expansion (what the agent actually reads)
# ---------------------------------------------------------------------------

_DEFAULT_TIME = "09:00"


def schedule_summary(automation: Automation) -> str:
    """One-line human schedule, e.g. ``daily 09:00``.

    Mirrors `vicoa automation ls`' column so the same automation reads the same
    way in the CLI and in a reference block.
    """
    if automation.schedule_kind == "once":
        return "once"
    freq = automation.frequency
    if not isinstance(freq, dict):
        return "recurring"
    kind = freq.get("kind")
    time = freq.get("time", _DEFAULT_TIME)
    if kind == "hourly":
        return f"hourly :{int(freq.get('minute', 0)):02d}"
    if kind == "daily":
        return f"daily {time}"
    if kind == "weekdays":
        return f"weekdays {time}"
    if kind == "weekly":
        days = ",".join(str(d) for d in (freq.get("weekdays") or []))
        return f"weekly [{days}] {time}"
    if kind == "custom":
        return f"custom {freq.get('unit', '')}".strip()
    return "recurring"


def _facts(pairs: list[tuple[str, str | None]]) -> str:
    return " · ".join(f"{k}: {v}" for k, v in pairs if v)


def _expand_session(db: Session, user_id: UUID, ref_id: UUID) -> dict | None:
    instance = (
        db.query(AgentInstance)
        .options(joinedload(AgentInstance.agent_type))
        .filter(
            AgentInstance.id == ref_id,
            AgentInstance.user_id == user_id,
            AgentInstance.status != AgentStatus.DELETED,
        )
        .first()
    )
    if instance is None:
        return None

    stats = _get_instance_message_stats(db, [instance.id]).get(instance.id, {})
    label = instance.name or f"Session {_short_id(instance.id)}"
    lines = [
        f'Session "{label}"',
        _facts(
            [
                ("agent", instance.agent_type.name if instance.agent_type else None),
                ("status", str(instance.status.value)),
                ("folder", instance.project),
                ("worktree", (instance.instance_metadata or {}).get("worktree_name")),
                ("id", str(instance.id)),
            ]
        ),
        f"Full transcript: `vicoa session get {_short_id(instance.id)}`",
    ]
    last = _truncate(stats.get("latest_message"), MAX_LAST_MESSAGE_CHARS)
    if last:
        lines.append(f"Last message: {last}")
    return {
        "kind": "session",
        "id": str(instance.id),
        "label": label,
        "token": slugify_token(
            instance.name or "", f"session-{_short_id(instance.id)}"
        ),
        "context": "\n".join(line for line in lines if line),
    }


def _expand_task(db: Session, user_id: UUID, ref_id: UUID) -> dict | None:
    task = db.query(Task).filter(Task.id == ref_id, Task.user_id == user_id).first()
    if task is None:
        return None
    response = serialize_task(db, task)
    heading = (
        f"Task {response.identifier}: {response.title}"
        if response.identifier
        else f'Task "{response.title}"'
    )
    lines = [
        heading,
        _facts(
            [
                ("status", response.status),
                ("priority", response.priority),
                ("project", response.project_name),
                ("id", str(response.id)),
            ]
        ),
        f"Live record: `vicoa task get {response.identifier or response.id}`",
    ]
    description = _truncate(response.description, MAX_DESCRIPTION_CHARS)
    if description:
        lines.append(f"Description:\n{description}")
    return {
        "kind": "task",
        "id": str(response.id),
        "label": response.title,
        "token": response.identifier
        or slugify_token(response.title, f"task-{_short_id(response.id)}"),
        "context": "\n".join(line for line in lines if line),
    }


def _expand_automation(db: Session, user_id: UUID, ref_id: UUID) -> dict | None:
    automation = (
        db.query(Automation)
        .filter(Automation.id == ref_id, Automation.user_id == user_id)
        .first()
    )
    if automation is None:
        return None
    lines = [
        f'Automation "{automation.title}"',
        _facts(
            [
                ("schedule", schedule_summary(automation)),
                ("state", "enabled" if automation.enabled else "paused"),
                (
                    "next run",
                    automation.next_run_at.isoformat()
                    if automation.next_run_at
                    else None,
                ),
                ("folder", automation.directory),
                ("id", str(automation.id)),
            ]
        ),
        f"Run history: `vicoa automation runs {_short_id(automation.id)}`",
    ]
    prompt = _truncate(automation.prompt, MAX_PROMPT_CHARS)
    if prompt:
        lines.append(f"Prompt:\n{prompt}")
    return {
        "kind": "automation",
        "id": str(automation.id),
        "label": automation.title,
        "token": slugify_token(
            automation.title, f"automation-{_short_id(automation.id)}"
        ),
        "context": "\n".join(line for line in lines if line),
    }


_EXPANDERS = {
    "session": _expand_session,
    "task": _expand_task,
    "automation": _expand_automation,
}


def get_reference(db: Session, user_id: UUID, kind: str, ref_id: UUID) -> dict | None:
    """One pick, rendered. ``None`` when it isn't the caller's (or is gone)."""
    expand = _EXPANDERS.get(kind)
    if expand is None:
        return None
    return expand(db, user_id, ref_id)
