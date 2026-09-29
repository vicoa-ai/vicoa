"""What a watcher room receives (collaboration §9).

A watcher is someone a session was shared with, following it live over their
own user-scoped connection. Broadcast sites name the room next to the owner's
rooms and hand over the owner's payload; `ConnectionManager` passes it through
`watcher_view` on the way out. Doing the narrowing here, once, rather than at
each site means a new broadcast site cannot forget it — and a payload kind
this module does not know is dropped for watchers, never passed through.

The narrowing is the grantee view the REST rows already get
(`shared.grantee_view`). One addition: with `machine_id` stripped, a client can
no longer derive liveness from the machine's heartbeat, so the frame always
carries the server's `live_state` verdict — computed here from the relay's own
sockets when the site did not supply one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from .. import grantee_view
from ..database.enums import AgentStatus
from ..database.liveness import compute_live_state

_MESSAGE_BODIES = frozenset({"new-message", "message-update"})
_INSTANCE_BODIES = frozenset({"instance-update", "instance-created"})


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _live_state(
    body: dict,
    session_connected: Callable[[str], bool],
    machine_connected: Callable[[str], bool],
) -> str | None:
    try:
        status = AgentStatus(body.get("status"))
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    instance_id = str(body.get("id") or "")
    machine_id = body.get("machine_id")
    return compute_live_state(
        status=status,
        instance_last_heartbeat_at=(
            now
            if instance_id and session_connected(instance_id)
            else _parse_ts(body.get("last_heartbeat_at"))
        ),
        machine_id=machine_id,
        machine_last_heartbeat_at=(
            now if machine_id and machine_connected(str(machine_id)) else None
        ),
        started_at=_parse_ts(body.get("started_at")),
        now=now,
    ).value


def watcher_view(
    payload: dict,
    *,
    session_connected: Callable[[str], bool],
    machine_connected: Callable[[str], bool],
) -> dict | None:
    """The `update` payload a watcher may receive, or None to withhold it.

    Messages pass unchanged — a grantee reads the same transcript over REST,
    and a `new-message` body carries no address or path of its own. Instance
    rows are narrowed to the grantee view and stamped with `live_state`.
    Anything else (machines, spawn requests, …) is the owner's alone.
    """
    body = payload.get("body")
    if not isinstance(body, dict):
        return None
    kind = body.get("t")
    if kind in _MESSAGE_BODIES:
        return payload
    if kind not in _INSTANCE_BODIES:
        return None
    return {
        **payload,
        "body": narrow_instance_body(
            body,
            session_connected=session_connected,
            machine_connected=machine_connected,
        ),
    }


def narrow_instance_body(
    body: dict,
    *,
    session_connected: Callable[[str], bool],
    machine_connected: Callable[[str], bool],
) -> dict:
    """An instance row as someone it is shared with may see it.

    Marked `grantee_view` so a client can tell it from its own rows at a
    glance: the web's own-session list must not treat a session it merely
    watches as one of its own that it somehow missed.
    """
    narrowed = dict(body)
    narrowed["grantee_view"] = True
    if narrowed.get("live_state") is None:
        live_state = _live_state(body, session_connected, machine_connected)
        if live_state is not None:
            narrowed["live_state"] = live_state
    narrowed["home_dir"] = None
    narrowed["machine_id"] = None
    narrowed["has_git_changes"] = False
    narrowed["project"] = grantee_view.project_label(body.get("project"))
    narrowed["instance_metadata"] = grantee_view.grantee_metadata(
        body.get("instance_metadata")
    )
    narrowed["session_config"] = grantee_view.display_session_config(
        body.get("session_config")
    )
    return narrowed
