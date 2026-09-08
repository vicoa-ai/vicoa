"""User-avatar seeding from the identity provider (collaboration P0).

The sibling of :mod:`shared.project_icons`, and deliberately the same shape: a
best-effort background pass that fetches an avatar *server-side* from an
allowlisted host, normalizes it through the same image pipeline as user uploads,
stores it in OUR S3, and points the user row at a URL we serve.

Constraints baked in:
  * The OAuth ``avatar_url`` claim is attacker-influenced in principle (it is
    whatever the IdP put in ``user_metadata``), so it is *not* fetched as given:
    only ``https`` on an allowlisted avatar host is followed, and redirects are
    off. The SSRF surface is those hosts alone.
  * The S3 object is keyed by ``user_id`` (``storage.user_avatar_key``) with no
    extension; the Content-Type comes from the stored object.
  * ``avatar_source`` is stamped ``'oauth'`` on every attempt (success *or*
    miss), so a failed lookup is never retried; only a NULL ``avatar_source`` is
    eligible, which also means a user upload ('user') is never clobbered.
  * We re-host rather than store the IdP URL: an <img> pointed at the IdP's CDN
    would leak a viewer's IP to Google on every shared surface, and those URLs
    rot when the identity changes.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from shared import storage
from shared.database.models import User
from shared.database.session import SessionLocal
from shared.images import InvalidImageError, process_image

logger = logging.getLogger(__name__)

# Hosts whose public avatar URLs we are willing to fetch. Google and Apple are
# the two providers Vicoa ships; Apple returns no avatar at all, so in practice
# this is Google, plus the hosts a self-hosted deployment gets for free by
# pointing its own Supabase project at GitHub/GitLab.
_ALLOWED_AVATAR_HOSTS = frozenset(
    {
        "lh3.googleusercontent.com",
        "lh4.googleusercontent.com",
        "lh5.googleusercontent.com",
        "lh6.googleusercontent.com",
        "avatars.githubusercontent.com",
        "secure.gravatar.com",
    }
)

# Avatars are tiny; anything larger is not one, and bounds the fetch.
MAX_AVATAR_BYTES = 8 * 1024 * 1024
_FETCH_TIMEOUT_S = 8.0


def allowed_avatar_url(raw: str | None) -> str | None:
    """The claim's URL if it is one we will fetch server-side, else None."""
    if not raw:
        return None
    try:
        parts = urlsplit(raw.strip())
    except ValueError:
        return None
    if parts.scheme != "https":
        return None
    # hostname lowercases and strips any :port / userinfo, so an
    # "https://lh3.googleusercontent.com@evil.example/" style URL cannot match.
    if parts.hostname not in _ALLOWED_AVATAR_HOSTS:
        return None
    return raw.strip()


def avatar_served_url(user_id: UUID | str) -> str:
    """Backend-relative URL clients render (stored in ``users.avatar_image_uri``)."""
    return f"/api/v1/users/{user_id}/avatar"


def seed_user_avatar(user_id: UUID, avatar_url: str | None) -> None:
    """Background task: seed a new user's avatar from their IdP (best-effort).

    Runs in its own DB session (invoked via FastAPI ``BackgroundTasks``),
    re-checks eligibility to stay idempotent under concurrent enqueues, and
    never raises.
    """
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            return
        # Only NULL avatar_source is eligible: 'oauth' = already attempted,
        # 'user' = uploaded / explicitly cleared (must win).
        if user.avatar_source is not None or user.avatar_image_uri:
            return
        url = allowed_avatar_url(avatar_url)
        if url is None:
            user.avatar_source = "oauth"  # mark attempted so we don't retry
            db.commit()
            return
        try:
            # follow_redirects stays off: a redirect is how an allowlisted host
            # would otherwise become an arbitrary one.
            with httpx.Client(
                timeout=_FETCH_TIMEOUT_S, follow_redirects=False
            ) as client:
                resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
            if len(data) > MAX_AVATAR_BYTES:
                raise ValueError(f"avatar too large: {len(data)} bytes")
            processed = process_image(data)
            storage.upload_attachment(
                storage.user_avatar_key(str(user_id)),
                processed.data,
                processed.mime_type,
            )
            user.avatar_image_uri = avatar_served_url(user_id)
            user.avatar_source = "oauth"
        except (httpx.HTTPError, InvalidImageError, ValueError, OSError) as exc:
            logger.info("oauth avatar seed skipped for %s: %s", user_id, exc)
            user.avatar_source = "oauth"  # attempted; leave uri NULL → initials
        except Exception:  # noqa: BLE001 — seeding must never break signup
            logger.warning("oauth avatar seed errored for %s", user_id, exc_info=True)
            user.avatar_source = "oauth"
        db.commit()
