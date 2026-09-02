"""Default project-icon seeding from the git remote (identity-unification §4e).

Best-effort, async, untrusted-I/O-aware. On auto-create a project's icon starts
empty; a background pass derives the owner avatar from the git remote for the
hosts we trust (github.com, gitlab.com), fetches it *server-side*, normalizes it
through the same image pipeline as user uploads, stores it in OUR S3, and points
the project at it. Anything unexpected leaves the emoji/generated default in
place — seeding must never break project creation.

Constraints baked in:
  * The outbound fetch only ever targets an allowlisted host's public avatar
    endpoint — not an arbitrary URL — so the SSRF surface is those hosts alone.
  * The S3 object is keyed by ``project_id`` (``storage.project_icon_key``), so a
    project can later move to a team without rekeying (plan §9).
  * ``icon_source`` is stamped ``'git'`` on every attempt (success *or* miss) so
    a failed lookup is never retried on each ``GET /projects``; only a NULL
    ``icon_source`` is eligible, which also means a user upload ('user') is never
    clobbered.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

import httpx

from shared import storage
from shared.database import Project
from shared.database.session import SessionLocal
from shared.images import InvalidImageError, process_image

logger = logging.getLogger(__name__)

# host -> avatar-URL template keyed on {owner}. Only hosts whose public avatar
# endpoint needs no auth and resolves to an image belong here.
_AVATAR_URL = {
    "github.com": "https://github.com/{owner}.png?size=200",
    "gitlab.com": "https://gitlab.com/{owner}.png",
}

# git@host:owner/repo(.git)
_SCP_LIKE = re.compile(r"^[\w.+-]+@([\w.-]+):(.+)$")
# scheme://[user@]host[:port]/owner/repo(.git)
_URL_LIKE = re.compile(r"^[a-z][\w+.-]*://(?:[^@/]+@)?([\w.-]+)(?::\d+)?/(.+)$", re.I)
_OWNER_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Avatars are tiny; anything larger is not one, and bounds the fetch.
MAX_ICON_BYTES = 8 * 1024 * 1024
_FETCH_TIMEOUT_S = 8.0


def _host_and_path(remote: str) -> tuple[str, str] | None:
    remote = remote.strip()
    if not remote:
        return None
    m = _SCP_LIKE.match(remote) or _URL_LIKE.match(remote)
    if m:
        return m.group(1).lower(), m.group(2)
    return None


def owner_avatar_url(git_remote_url: str | None) -> str | None:
    """Public owner-avatar URL for a supported host, or None to skip seeding."""
    if not git_remote_url:
        return None
    parsed = _host_and_path(git_remote_url)
    if parsed is None:
        return None
    host, path = parsed
    template = _AVATAR_URL.get(host)
    if template is None:
        return None
    # path is "owner/repo(.git)" (or deeper for GitLab groups); the first
    # segment is the owner/org whose avatar we want.
    owner = path.strip("/").split("/")[0]
    # `.`/`..` are valid against _OWNER_RE (dots are allowed in real handles) but
    # would be path traversal in the avatar URL — reject them explicitly.
    if not owner or owner in (".", "..") or not _OWNER_RE.fullmatch(owner):
        return None
    return template.format(owner=owner)


def icon_served_url(project_id: UUID | str) -> str:
    """Backend-relative URL clients render (stored in ``projects.icon_image_uri``)."""
    return f"/api/v1/projects/{project_id}/icon"


def seed_project_icon(project_id: UUID) -> None:
    """Background task: seed a project's icon from its git remote (best-effort).

    Runs in its own DB session (invoked via FastAPI ``BackgroundTasks``), re-checks
    eligibility to stay idempotent under concurrent enqueues, and never raises.
    """
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project is None or project.is_inbox:
            return
        # Only NULL icon_source is eligible: 'git' = already attempted, 'user' =
        # uploaded (must win). icon_image_uri set = already have one.
        if project.icon_source is not None or project.icon_image_uri:
            return
        avatar = owner_avatar_url(project.git_remote_url)
        if avatar is None:
            project.icon_source = "git"  # mark attempted so we don't retry
            db.commit()
            return
        try:
            with httpx.Client(
                timeout=_FETCH_TIMEOUT_S, follow_redirects=True
            ) as client:
                resp = client.get(avatar)
            resp.raise_for_status()
            data = resp.content
            if len(data) > MAX_ICON_BYTES:
                raise ValueError(f"avatar too large: {len(data)} bytes")
            processed = process_image(data)
            storage.upload_attachment(
                storage.project_icon_key(str(project_id)),
                processed.data,
                processed.mime_type,
            )
            project.icon_image_uri = icon_served_url(project_id)
            project.icon_source = "git"
        except (httpx.HTTPError, InvalidImageError, ValueError, OSError) as exc:
            logger.info("git icon seed skipped for %s: %s", project_id, exc)
            project.icon_source = "git"  # attempted; leave uri NULL → emoji default
        except Exception:  # noqa: BLE001 — seeding must never break the caller
            logger.warning("git icon seed errored for %s", project_id, exc_info=True)
            project.icon_source = "git"
        db.commit()
