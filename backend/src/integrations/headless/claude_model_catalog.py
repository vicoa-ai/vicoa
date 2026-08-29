"""Build Claude's live available-model list for the mid-session gear.

Claude Code exposes no ``model/list`` RPC the way codex's app-server does
(``codex_app_server.discover_and_report_models``), so there is nothing to probe
at runtime. The "live" set is therefore the static agent catalog merged with any
custom models the user has configured on this machine — the same merge paseo
does in ``providers/claude/models.ts``: the ``model`` field of
``~/.claude/settings.json`` plus any ``ANTHROPIC_*_MODEL`` environment override
(``ANTHROPIC_MODEL``, ``ANTHROPIC_DEFAULT_SONNET_MODEL``,
``ANTHROPIC_SMALL_FAST_MODEL``, …). The Claude Agent SDK the runner spawns reads
those very sources, so surfacing them keeps the picker honest about what Claude
will actually accept.

Imports the canonical catalog from ``protocol.agent_catalog`` (shipped in the
CLI wheel); the ``shared.agent_catalog`` shim is not shipped to the daemon.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Mapping, Optional

from protocol.agent_catalog import AGENT_CATALOG

logger = logging.getLogger(__name__)

# ANTHROPIC_MODEL, ANTHROPIC_DEFAULT_OPUS_MODEL, ANTHROPIC_SMALL_FAST_MODEL, …
_ANTHROPIC_MODEL_ENV = re.compile(r"^ANTHROPIC_[A-Z0-9_]*MODEL$")


def _catalog_claude_models() -> list[dict[str, str]]:
    """The catalog's Claude models as ``[{id, label}]`` (order preserved)."""
    for agent in AGENT_CATALOG.get("agents", []):
        if agent.get("id") == "claude":
            return [
                {"id": m["id"], "label": str(m.get("label") or m["id"])}
                for m in agent.get("models", [])
                if m.get("id")
            ]
    return []


def _custom_claude_model_ids(home: Path, env: Mapping[str, str]) -> list[str]:
    """User-configured Claude model ids from settings.json + env, in a stable
    order (settings.json first, then env keys sorted). Best-effort: an
    unreadable / malformed settings.json contributes nothing."""
    ids: list[str] = []

    settings_path = home / ".claude" / "settings.json"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            model = data.get("model")
            if isinstance(model, str) and model.strip():
                ids.append(model.strip())
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        logger.info(
            "claude model discovery: could not read %s (%s)", settings_path, exc
        )

    for key in sorted(env):
        if _ANTHROPIC_MODEL_ENV.match(key):
            value = env.get(key)
            if isinstance(value, str) and value.strip():
                ids.append(value.strip())

    return ids


def build_claude_available_models(
    home: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> list[dict[str, str]]:
    """Catalog Claude models + the machine's custom models, de-duped by id.

    Custom ids not already in the catalog are appended as ``{id, label: id}``
    (we have no nicer label for a user-supplied slug). Returns ``[]`` only when
    the catalog somehow has no Claude entry — callers treat empty as "nothing to
    report" and leave the static fallback in place.
    """
    home = home or Path.home()
    env = env if env is not None else os.environ

    models = _catalog_claude_models()
    seen = {m["id"] for m in models}
    for model_id in _custom_claude_model_ids(home, env):
        if model_id not in seen:
            models.append({"id": model_id, "label": model_id})
            seen.add(model_id)
    return models
