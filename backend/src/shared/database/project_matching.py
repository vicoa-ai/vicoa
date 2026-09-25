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
    un-archives it (running an agent there contradicts "no active work"), it
    ensures a ``project_directories`` row for this machine so subsequent
    path-tier matches hit, and it stamps the git remote onto a project that was
    linked by folder alone so later sessions (other machines, worktrees) can
    match it by identity. It deliberately does **not** adopt the unfiled
    sessions already under that path (``backfill_project_id_for_directory`` is
    the user's link endpoint only): deleting a project unfiles its sessions,
    and the next session in that folder auto-creates a same-named project —
    if that adopted, delete would resurrect the whole history.

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

     Paths are compared in a canonical form (``~`` expanded with the session's
     ``home_dir``, ``\\`` folded to ``/``, no trailing slash) because the two
     sides come from different writers: wrappers report ``~``-collapsed paths,
     but a wrapper whose HOME differs from the daemon's (e2e, containers)
     reports absolute ones, and Windows wrappers report backslashes.

     A session that registers **without a machine** (no daemon on that box yet,
     an older client, a container) can't be matched per-machine, so its path
     is matched against the user's directory rows on *any* machine — the same
     ``~``-relative checkout on two boxes is the same project far more often
     than not. Longest path wins, ties go to the oldest project.

Within each tier the user's **own** projects win, then projects **shared with
them** at ``editor`` or above for sessions (team-owned boards they are a member
of, grants): a member who clones the team's repo on their own laptop lands on
the shared project instead of minting a private twin, and their sessions show
up on the board. A viewer's session never attaches to someone else's project —
attaching is contributing. Auto-create, when nothing matches, always mints a
*personal* project.

Auto-create is skipped for a machine-less session with no remote: such a
project could never get a directory row, so nothing would ever match it again
and the next machine-less session in the same folder would mint another. It
stays unfiled ("No project") instead.

Both the register hooks (servers routers) and the link-a-folder backfill
(backend task_queries) call this one helper so the rule can never drift.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from .models import AgentInstance
from .task_models import Project, ProjectDirectory

logger = logging.getLogger(__name__)

# ``C:`` / ``D:`` — a bare Windows drive after the trailing slash is stripped.
_DRIVE_ROOT = re.compile(r"^[A-Za-z]:$")


def _normalize_path(path: str, home_dir: str | None) -> str:
    """Canonical form of a path for *comparison* (never for storage).

    Folds ``\\`` to ``/`` (Windows wrappers report backslashes), expands a
    leading ``~`` with ``home_dir`` when the caller knows it, and strips the
    trailing slash. Storage keeps whatever the wrapper reported so the UI keeps
    showing ``~/…``.
    """
    p = path.replace("\\", "/")
    if home_dir and (p == "~" or p.startswith("~/")):
        p = home_dir.replace("\\", "/").rstrip("/") + p[1:]
    return p.rstrip("/")


def _basename(path: str) -> str:
    """Last path segment (the project's default display name)."""
    parts = _normalize_path(path, None).split("/")
    return parts[-1] if parts else path


def _path_at_or_under(session_path: str, local_path: str) -> bool:
    """True when ``session_path`` is ``local_path`` itself or a child of it.

    Both sides are expected in canonical form (see :func:`_normalize_path`);
    compared on a path boundary (``/a/b`` must not match ``/a/bc``).
    """
    base = local_path.rstrip("/")
    session = session_path.rstrip("/")
    return session == base or session.startswith(base + "/")


@dataclass(frozen=True)
class _Match:
    project: Project
    # The tier-2 row that matched (None for a tier-1 remote match). Lets the
    # caller tell "linked by folder" from "matched by identity".
    directory: ProjectDirectory | None


def _match_project(
    db: Session,
    user_id: UUID,
    machine_id: UUID | None,
    project_path: str | None,
    git_remote_url: str | None,
    repo_root: str | None,
    home_dir: str | None = None,
) -> _Match | None:
    """The shared matcher — returns the matched project (archived or not), or None.

    Deliberately does not exclude ``is_archived`` rows: activity in an archived
    project must re-match it so the caller can un-archive rather than duplicate.
    """
    # Own personal projects, then the shared ones this user may contribute to.
    # Lazy import: `shared.access` imports this package's models.
    from shared.access import visible_project_select

    own = visible_project_select(user_id, scope="me")
    shared = visible_project_select(
        user_id, scope="shared", grant_scope="sessions", min_role="editor"
    )

    # Tier 1 — canonical git remote (dormant until the daemon reports a remote).
    if git_remote_url:
        for scope in (own, shared):
            matched = (
                db.query(Project)
                .filter(
                    Project.id.in_(scope),
                    Project.git_remote_url == git_remote_url,
                )
                .order_by(Project.created_at.asc())
                .limit(1)
                .first()
            )
            if matched is not None:
                return _Match(matched, None)

    # Tier 2 — cwd OR source repo root under a linked directory. On this
    # machine when the session has one; on any of the user's machines when it
    # doesn't (see the module docstring). The rows are the user's own (a member
    # links their own machine), but the project behind one may be shared — and
    # a since-revoked grant must not keep attaching sessions to it, hence the
    # access filter on the project.
    candidates = [_normalize_path(p, home_dir) for p in (project_path, repo_root) if p]
    if not candidates:
        return None
    query = db.query(ProjectDirectory).filter(
        ProjectDirectory.user_id == user_id,
        or_(
            ProjectDirectory.project_id.in_(own),
            ProjectDirectory.project_id.in_(shared),
        ),
    )
    if machine_id is not None:
        query = query.filter(ProjectDirectory.machine_id == machine_id)
    best: list[ProjectDirectory] = []
    best_len = -1
    for row in query.all():
        local = _normalize_path(row.local_path, home_dir)
        if not any(_path_at_or_under(c, local) for c in candidates):
            continue
        if len(local) > best_len:
            best, best_len = [row], len(local)
        elif len(local) == best_len:
            best.append(row)
    if not best:
        return None
    # Same-length matches can only tie across machines (the machine-less
    # lookup): the oldest project wins, deterministically.
    by_project = {row.project_id: row for row in best}
    project = (
        db.query(Project)
        .filter(Project.id.in_(list(by_project)))
        .order_by(Project.created_at.asc(), Project.id.asc())
        .first()
    )
    assert project is not None  # every row's project exists (FK)
    return _Match(project, by_project[project.id])


def resolve_project_id_for_session(
    db: Session,
    user_id: UUID,
    machine_id: UUID | None,
    project_path: str | None,
    git_remote_url: str | None = None,
    repo_root: str | None = None,
    home_dir: str | None = None,
) -> UUID | None:
    """Best-effort project for a session; ``None`` when nothing is set up for it.

    Read-only — never creates. ``project_path`` is the session's cwd;
    ``repo_root`` is the top-level of the git repository the session runs in (the
    *main* checkout, even for a linked worktree) — reported by the wrapper so a
    worktree can be attributed to the same project as its main checkout.
    """
    match = _match_project(
        db, user_id, machine_id, project_path, git_remote_url, repo_root, home_dir
    )
    return match.project.id if match is not None else None


def _should_skip_autocreate(name_source: str | None, home_dir: str | None) -> bool:
    """True when a session should NOT mint a project (stays at NULL = No project).

    Auto-create names a project after ``repo_root or cwd``; some paths are not
    worth a project of their own: a session whose cwd is the home directory (no
    repo) — reported as ``~`` by wrappers, or absolute — the filesystem root, a
    bare Windows drive, or anything with an empty basename. A real repo always
    has a ``repo_root``, so a git session is never skipped.
    """
    if not name_source:
        return True
    base = _normalize_path(name_source, home_dir)
    if base in ("", "~") or _DRIVE_ROOT.match(base):
        return True
    if home_dir and base == _normalize_path(home_dir, None):
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


def _backfill_remote(
    match: _Match,
    *,
    user_id: UUID,
    git_remote_url: str | None,
    repo_root: str | None,
    home_dir: str | None,
) -> None:
    """Stamp the session's remote onto a project that was linked by folder only.

    A project the user created by hand (or that predates remote reporting) has
    ``git_remote_url`` NULL, so it can only ever be found by path on this one
    machine; a session elsewhere — another box, a worktree registered without a
    machine — misses it and mints a twin with the remote. Once the linked folder
    is known to *be* the repo (the session's ``repo_root`` is the linked path,
    not a parent of it), the remote is that project's identity: record it so
    tier 1 finds the project from then on. Own projects only — a member's
    clone never rewrites the team project's identity.
    """
    project, directory = match.project, match.directory
    if (
        directory is None
        or not git_remote_url
        or project.git_remote_url is not None
        or project.user_id != user_id
        or not repo_root
    ):
        return
    if _normalize_path(directory.local_path, home_dir) != _normalize_path(
        repo_root, home_dir
    ):
        return
    project.git_remote_url = git_remote_url
    logger.info(
        "stamped remote %s on folder-linked project %s (%s)",
        git_remote_url,
        project.id,
        project.name,
    )


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
    Returns ``None`` when the path isn't worth a project (see
    :func:`_should_skip_autocreate`) or when the session has neither a machine
    nor a remote (a project minted then would be unreachable — see the module
    docstring) — the session then falls back to NULL.

    Does not commit — the register handler owns the surrounding transaction.
    """
    name_source = repo_root or project_path
    match = _match_project(
        db, user_id, machine_id, project_path, git_remote_url, repo_root, home_dir
    )
    if match is None:
        if _should_skip_autocreate(name_source, home_dir):
            return None
        if machine_id is None and not git_remote_url:
            logger.info(
                "not auto-creating a project for machine-less session in %s "
                "(user %s): no remote to match it by later",
                name_source,
                user_id,
            )
            return None
        # Re-check under the lock: a concurrent register may have created it
        # while we waited (the lock is held until this request commits).
        _advisory_lock(db, user_id, git_remote_url or name_source or "")
        match = _match_project(
            db, user_id, machine_id, project_path, git_remote_url, repo_root, home_dir
        )
        if match is None:
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
            match = _Match(project, None)

    project = match.project
    # Self-heal: a session is live work — an archived match is no longer stale.
    if project.is_archived:
        project.is_archived = False
        project.archived_at = None

    _backfill_remote(
        match,
        user_id=user_id,
        git_remote_url=git_remote_url,
        repo_root=repo_root,
        home_dir=home_dir,
    )
    # No adoption backfill here — see the module docstring (delete must feel
    # deleted); the user's "save directory" is the adopt affordance.
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
    """Stamp ``project_id`` on unlinked sessions under ``local_path``.

    Called when the user (re)links a project directory — and only then; the
    matcher's auto-create never adopts (see the module docstring) — so sessions
    that ran there *before* the link get attached too (link-after-run must
    still group). Matches either the session's cwd
    (``project``) OR its reported source repo root
    (``instance_metadata->>'repo_root'``), so a linked worktree — whose cwd sits
    outside the repo — is picked up by its repo root.

    Adopts sessions on **this machine** and sessions with **no machine** (they
    registered before a daemon existed on their box; the matcher likewise
    resolves them by path against any machine's links — see the module
    docstring). Paths are compared canonically (``~`` expanded with the
    session's own ``home_dir``, see :func:`_normalize_path`) so a wrapper that
    reported an absolute path still matches a ``~``-relative link.

    Only touches rows with ``project_id IS NULL`` — never steals a session
    already matched to another project. Returns the number of rows updated.
    """
    repo_root_col = AgentInstance.instance_metadata["repo_root"].astext
    # Narrow projection: a user's unfiled history can run to thousands of rows
    # and ``git_diff`` is unbounded — never hydrate whole instances here.
    rows = (
        db.query(
            AgentInstance.id,
            AgentInstance.project,
            AgentInstance.home_dir,
            repo_root_col,
        )
        .filter(
            AgentInstance.user_id == user_id,
            AgentInstance.project_id.is_(None),
            or_(
                AgentInstance.machine_id == machine_id,
                AgentInstance.machine_id.is_(None),
            ),
            or_(AgentInstance.project.isnot(None), repo_root_col.isnot(None)),
        )
        .all()
    )
    adopt: list[UUID] = []
    for instance_id, cwd, home_dir, repo_root in rows:
        local = _normalize_path(local_path, home_dir)
        candidates = [_normalize_path(p, home_dir) for p in (cwd, repo_root) if p]
        if any(_path_at_or_under(c, local) for c in candidates):
            adopt.append(instance_id)
    if not adopt:
        return 0
    db.query(AgentInstance).filter(AgentInstance.id.in_(adopt)).update(
        {AgentInstance.project_id: project_id}, synchronize_session="fetch"
    )
    return len(adopt)


# Public aliases of the two comparison helpers above. The `#` reference picker
# resolves an *automation's* folder to a project — automations carry no
# `project_id` column, so they re-run tier 2 by hand — and it must not drift
# from the rules a session is matched by.
canonical_path = _normalize_path
path_at_or_under = _path_at_or_under
