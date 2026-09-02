"""Session ↔ project auto-match (and auto-create).

Connects an ``agent_instance`` to the formal ``projects`` entity. Two entry
points share one matcher:

  * ``resolve_project_id_for_session`` — read-only. Finds an existing project
    for a checkout, or ``None``. Used by the link-a-folder backfill, where
    minting a project would be wrong.
  * ``resolve_or_create_project_id_for_session`` — match-or-create. The register
    hooks call this so the *first* session in any new dir/repo materializes a
    real ``projects`` row (orca-style), rather than leaving the sidebar to
    derive a phantom basename-only group forever (project-identity-unification
    plan §4a). It also **self-heals**: activity in an archived project
    un-archives it (running an agent there contradicts "no active work"), and it
    ensures a ``project_directories`` row for this machine so subsequent
    path-tier matches hit.

The matcher intentionally does **not** filter out archived projects: a session
in a repo the user archived must re-match (and un-archive) that project, never
mint a duplicate.

Match order (identity strength, high → low):

  1. **git remote** — the session's canonical remote URL == ``projects``.
     ``git_remote_url``. This is the tier that lets one project span machines
     (laptop + cloud + worktrees of the same repo collapse into one project),
     and it is the only tier that can attribute a *worktree* by identity rather
     than by where its files happen to live. Dormant until the daemon reports a
     remote (``git_remote_url is None`` at the call site).
  2. **working directory / source repo root** — the session's cwd, or the repo
     root of the worktree it runs in, sits at/under a ``project_directories``
     row's ``local_path`` on the *same machine*. Longest ``local_path`` wins.
     ``repo_root`` is what rescues a linked worktree: its checkout lives OUTSIDE
     the repo (``~/vicoa/workspaces/...``) so its cwd never nests under the
     linked main checkout, but its repo root does. Works for non-git folders
     too (repo_root simply absent), so a remote is never required.

Both the register hooks (servers routers) and the link-a-folder backfill
(backend task_queries) call this one helper so the rule can never drift.
"""

from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from .models import AgentInstance
from .task_models import Project, ProjectDirectory

logger = logging.getLogger(__name__)


def _basename(path: str) -> str:
    """Last path segment (the project's default display name)."""
    parts = path.rstrip("/").split("/")
    return parts[-1] if parts else path


def _path_at_or_under(session_path: str, local_path: str) -> bool:
    """True when ``session_path`` is ``local_path`` itself or a child of it.

    Compared on a path boundary (``/a/b`` must not match ``/a/bc``) and tolerant
    of a trailing slash on either side.
    """
    base = local_path.rstrip("/")
    return (
        session_path == base
        or session_path == base + "/"
        or session_path.startswith(base + "/")
    )


def _match_project(
    db: Session,
    user_id: UUID,
    machine_id: UUID | None,
    project_path: str | None,
    git_remote_url: str | None,
    repo_root: str | None,
) -> Project | None:
    """The shared matcher — returns the matched project (archived or not), or None.

    Deliberately does not exclude ``is_archived`` rows: activity in an archived
    project must re-match it so the caller can un-archive rather than duplicate.
    """
    # Tier 1 — canonical git remote (dormant until the daemon reports a remote).
    if git_remote_url:
        matched = (
            db.query(Project)
            .filter(
                Project.user_id == user_id,
                Project.git_remote_url == git_remote_url,
                Project.is_inbox.is_(False),
            )
            .order_by(Project.created_at.asc())
            .limit(1)
            .first()
        )
        if matched is not None:
            return matched

    # Tier 2 — cwd OR source repo root under a linked directory on this machine.
    candidates = [p for p in (project_path, repo_root) if p]
    if candidates and machine_id is not None:
        rows = (
            db.query(ProjectDirectory)
            .filter(
                ProjectDirectory.user_id == user_id,
                ProjectDirectory.machine_id == machine_id,
            )
            .all()
        )
        best: ProjectDirectory | None = None
        for row in rows:
            if any(_path_at_or_under(c, row.local_path) for c in candidates):
                if best is None or len(row.local_path) > len(best.local_path):
                    best = row
        if best is not None:
            return db.get(Project, best.project_id)

    return None


def resolve_project_id_for_session(
    db: Session,
    user_id: UUID,
    machine_id: UUID | None,
    project_path: str | None,
    git_remote_url: str | None = None,
    repo_root: str | None = None,
) -> UUID | None:
    """Best-effort project for a session; ``None`` when nothing is set up for it.

    Read-only — never creates. ``project_path`` is the session's cwd;
    ``repo_root`` is the top-level of the git repository the session runs in (the
    *main* checkout, even for a linked worktree) — reported by the wrapper so a
    worktree can be attributed to the same project as its main checkout.
    """
    project = _match_project(
        db, user_id, machine_id, project_path, git_remote_url, repo_root
    )
    return project.id if project is not None else None


def _should_skip_autocreate(name_source: str | None, home_dir: str | None) -> bool:
    """True when a session should NOT mint a project (routes to Inbox/NULL).

    Auto-create names a project after ``repo_root or cwd``; some paths are not
    worth a project of their own: a session whose cwd is the home directory (no
    repo), the filesystem root, or anything with an empty basename. A real repo
    always has a ``repo_root``, so a git session is never skipped.
    """
    if not name_source:
        return True
    base = name_source.rstrip("/")
    if base in ("", "/"):
        return True
    if home_dir and base == home_dir.rstrip("/"):
        return True
    return not _basename(base)


def _ensure_directory_row(
    db: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    machine_id: UUID | None,
    local_path: str | None,
) -> None:
    """Insert a ``project_directories`` row for this machine if absent.

    Insert-only: never overwrites an existing (project, machine) link, so a
    session in ``/repo/subdir`` can't narrow a link the user made to ``/repo``.
    """
    if machine_id is None or not local_path:
        return
    exists = (
        db.query(ProjectDirectory.id)
        .filter(
            ProjectDirectory.project_id == project_id,
            ProjectDirectory.machine_id == machine_id,
        )
        .first()
    )
    if exists is not None:
        return
    db.add(
        ProjectDirectory(
            user_id=user_id,
            project_id=project_id,
            machine_id=machine_id,
            local_path=local_path.rstrip("/") or local_path,
        )
    )
    db.flush()


def _advisory_lock(db: Session, user_id: UUID, key_source: str) -> None:
    """Serialize concurrent auto-creates for the same (user, repo) checkout.

    Two sessions registering in a fresh repo at the same instant would otherwise
    each miss the match and mint a duplicate project. A transaction-scoped
    Postgres advisory lock keyed on (user, remote-or-path) makes the loser block
    until the winner commits, so its post-lock re-match finds the new project.
    No-op on non-Postgres backends (single-threaded tests never race).
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    digest = hashlib.sha256(f"{user_id}:{key_source}".encode()).digest()
    # A signed 64-bit key for pg_advisory_xact_lock(bigint).
    key = int.from_bytes(digest[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def resolve_or_create_project_id_for_session(
    db: Session,
    user_id: UUID,
    machine_id: UUID | None,
    project_path: str | None,
    git_remote_url: str | None = None,
    repo_root: str | None = None,
    home_dir: str | None = None,
) -> UUID | None:
    """Match a session to a project, creating one if none exists (plan §4a).

    Unlike :func:`resolve_project_id_for_session`, this materializes a real
    project the first time a session runs in an unseen dir/repo, self-heals an
    archived match back to active, and ensures a directory row for this machine.
    Returns ``None`` only when the path isn't worth a project (see
    :func:`_should_skip_autocreate`) — the session then falls back to NULL.

    Does not commit — the register handler owns the surrounding transaction.
    """
    name_source = repo_root or project_path
    project = _match_project(
        db, user_id, machine_id, project_path, git_remote_url, repo_root
    )
    if project is None:
        if _should_skip_autocreate(name_source, home_dir):
            return None
        # Re-check under the lock: a concurrent register may have created it
        # while we waited (the lock is held until this request commits).
        _advisory_lock(db, user_id, git_remote_url or name_source or "")
        project = _match_project(
            db, user_id, machine_id, project_path, git_remote_url, repo_root
        )
        if project is None:
            assert name_source is not None  # guarded by _should_skip_autocreate
            project = Project(
                user_id=user_id,
                name=_basename(name_source),
                git_remote_url=git_remote_url,
            )
            db.add(project)
            db.flush()
            logger.info(
                "auto-created project %s (%s) for user %s",
                project.id,
                project.name,
                user_id,
            )

    # Self-heal: a session is live work — an archived match is no longer stale.
    if project.is_archived:
        project.is_archived = False
        project.archived_at = None

    _ensure_directory_row(
        db,
        user_id=user_id,
        project_id=project.id,
        machine_id=machine_id,
        local_path=name_source,
    )
    return project.id


def backfill_project_id_for_directory(
    db: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    machine_id: UUID,
    local_path: str,
) -> int:
    """Stamp ``project_id`` on this machine's unlinked sessions under ``local_path``.

    Called when a project directory is (re)linked so sessions that ran there
    *before* the link get attached too (link-after-run must still group). Matches
    either the session's cwd (``project``) OR its reported source repo root
    (``instance_metadata->>'repo_root'``), so a linked worktree — whose cwd sits
    outside the repo — is picked up by its repo root. Only touches rows with
    ``project_id IS NULL`` — never steals a session already matched to another
    project. Returns the number of rows updated.
    """
    base = local_path.rstrip("/")
    repo_root_col = AgentInstance.instance_metadata["repo_root"].astext
    rows = (
        db.query(AgentInstance)
        .filter(
            AgentInstance.user_id == user_id,
            AgentInstance.machine_id == machine_id,
            AgentInstance.project_id.is_(None),
            or_(
                AgentInstance.project == base,
                AgentInstance.project == base + "/",
                AgentInstance.project.startswith(base + "/", autoescape=True),
                repo_root_col == base,
                repo_root_col.startswith(base + "/", autoescape=True),
            ),
        )
        .all()
    )
    for inst in rows:
        inst.project_id = project_id
    return len(rows)
