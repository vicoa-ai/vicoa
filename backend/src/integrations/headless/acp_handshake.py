"""The ACP handshake, as pure data.

What ``initialize`` sends and how a ``session/new`` answer is read, shared by
the live session wrapper (:mod:`acp_base`) and the provider probe
(:mod:`vicoa.rpc.provider_ops`). One definition, so "Check" in Settings →
Providers tests exactly the handshake a real session will perform — a probe
that passed with a different payload would prove nothing.

No I/O and no imports beyond typing; the probe runs inside the daemon and must
not drag the session wrapper's SDK/WebSocket imports in with it.
"""

from __future__ import annotations

from typing import Any, Dict, List

#: What this client calls itself in ``initialize``.
CLIENT_INFO: Dict[str, str] = {"name": "vicoa", "title": "Vicoa", "version": "1.0.0"}


def initialize_payloads() -> List[Dict[str, Any]]:
    """``initialize`` params to try, most spec-compliant first.

    The v1 payload declares terminal support (fs stays off, so the agent keeps
    its own file tools). Legacy shapes follow for agent builds that predate
    the v1 schema — older OpenCode accepted ``capabilities.supports`` and
    date-style versions. Fresh dicts each call: callers may mutate.
    """
    return [
        {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                # Terminal on, fs off. Terminal is what makes the agent's
                # shell commands *ours*: run in a process group we own, so
                # they die with the session, their output is bounded, and a
                # stuck one can be killed from here. fs stays off — the
                # agent's own file tools are better than anything we would
                # proxy, and turning them on would only add a hop.
                "terminal": True,
            },
            "clientInfo": dict(CLIENT_INFO),
        },
        {
            # Legacy pre-v1 shape (older OpenCode builds).
            "protocolVersion": 1,
            "capabilities": {"supports": ["streaming", "tools", "permissions"]},
            "clientInfo": {"name": "vicoa", "version": "1.0.0"},
        },
        {
            # Backward-compatible fallback for agents that accept date-style versions.
            "protocolVersion": "2024-11-01",
            "capabilities": {"supports": ["streaming", "tools", "permissions"]},
            "clientInfo": {"name": "vicoa", "version": "1.0.0"},
        },
    ]


def is_auth_required_error(error: Exception) -> bool:
    """Spec error code -32000 = Authentication required."""
    text = str(error)
    return "-32000" in text or "authentication required" in text.lower()


def normalize_models(
    available_models: List[Dict[str, Any]],
    config_options: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Normalize an agent's model choices to ``[{id, label}]``.

    Prefers the dedicated ``models.availableModels`` block (gemini, kimi);
    falls back to the ``model`` configOption's ``options`` list (cursor,
    copilot).
    """
    if available_models:
        return [
            {
                "id": str(m.get("modelId")),
                "label": str(m.get("name") or m.get("modelId")),
            }
            for m in available_models
            if isinstance(m, dict) and m.get("modelId")
        ]
    option = next(
        (
            o
            for o in config_options
            if isinstance(o, dict) and str(o.get("category") or "") == "model"
        ),
        None,
    )
    if option:
        out: List[Dict[str, str]] = []
        for o in option.get("options") or []:
            if isinstance(o, dict) and o.get("value") is not None:
                out.append(
                    {
                        "id": str(o.get("value")),
                        "label": str(o.get("name") or o.get("value")),
                    }
                )
        return out
    return []


def session_models(result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Model choices straight out of a ``session/new`` / ``session/load`` result."""
    models = result.get("models")
    available = models.get("availableModels") if isinstance(models, dict) else None
    config_options = result.get("configOptions")
    return normalize_models(
        [m for m in (available or []) if isinstance(m, dict)],
        [o for o in (config_options or []) if isinstance(o, dict)]
        if isinstance(config_options, list)
        else [],
    )


def session_modes(result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Session modes (``modes.availableModes``) as ``[{id, label}]``, the
    agent's current mode (``modes.currentModeId``) first.

    The list is what gets cached per machine (``machine_agent_models.modes``)
    and the clients treat its first entry as the agent's default, so the
    agent's own starting mode leads regardless of how it orders the list.
    """
    modes = result.get("modes")
    if not isinstance(modes, dict):
        return []
    entries = [
        {"id": str(m.get("id")), "label": str(m.get("name") or m.get("id"))}
        for m in (modes.get("availableModes") or [])
        if isinstance(m, dict) and m.get("id")
    ]
    return current_mode_first(entries, modes.get("currentModeId"))


def current_mode_first(
    entries: List[Dict[str, str]], current_id: Any
) -> List[Dict[str, str]]:
    """Reorder ``entries`` so the one with ``current_id`` leads; unchanged when
    it isn't there (or there is no current mode)."""
    if not isinstance(current_id, str) or not current_id:
        return entries
    current = [e for e in entries if e.get("id") == current_id]
    if not current:
        return entries
    return current + [e for e in entries if e.get("id") != current_id]


__all__ = [
    "CLIENT_INFO",
    "current_mode_first",
    "initialize_payloads",
    "is_auth_required_error",
    "normalize_models",
    "session_models",
    "session_modes",
]
