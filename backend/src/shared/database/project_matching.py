"""Session ↔ project auto-match.

Connects an ``agent_instance`` to the formal ``projects`` entity WITHOUT
creating one: given a session's machine, working directory, and (when the
wrapper reports them) the git remote and source-repo root, find an existing
project the user already set up for that checkout. No match ⇒ NULL (the sidebar
keeps deriving its top-level group from the ``project`` path string until a
project is linked; NULL is *not* the Inbox — Inbox is a task concept).

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

from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import AgentInstance
from .task_models import Project, ProjectDirectory


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


def resolve_project_id_for_session(
    db: Session,
    user_id: UUID,
    machine_id: UUID | None,
    project_path: str | None,
    git_remote_url: str | None = None,
    repo_root: str | None = None,
) -> UUID | None:
    """Best-effort project for a session; ``None`` when nothing is set up for it.

    ``project_path`` is the session's cwd; ``repo_root`` is the top-level of the
    git repository the session runs in (the *main* checkout, even for a linked
    worktree) — reported by the wrapper so a worktree can be attributed to the
    same project as its main checkout.
    """
    # Tier 1 — canonical git remote (dormant until the daemon reports a remote).
    if git_remote_url:
        matched = (
            db.query(Project.id)
            .filter(
                Project.user_id == user_id,
                Project.git_remote_url == git_remote_url,
                Project.is_inbox.is_(False),
            )
            .order_by(Project.created_at.asc())
            .limit(1)
            .scalar()
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
            return best.project_id

    return None


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
