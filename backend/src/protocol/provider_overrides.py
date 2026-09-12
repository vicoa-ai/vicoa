"""User-defined agent providers, from ``~/.vicoa/config.json``.

The section that decouples "add an agent" from "ship a release". Vicoa's agent
identity has always been a static allowlist compiled into
:mod:`protocol.agent_catalog` and mirrored into the web and mobile clients, so a
new agent cost a backend deploy, a daemon release, a web deploy *and* an App
Store review. Anything under ``agents.providers`` here is read by the daemon at
launch instead, so a user can point Vicoa at any ACP-speaking CLI — or at a
second profile of one Vicoa already knows — by editing a file::

    {
      "agents": {
        "providers": {
          "gemini-nightly": {
            "extends": "acp",
            "label": "Gemini Nightly",
            "command": ["gemini-nightly", "--experimental-acp"],
            "env": {"NO_BROWSER": "true"}
          },
          "cursor": { "enabled": false }
        }
      }
    }

Two shapes:

* **A custom provider** — an id not in :data:`GENERIC_ACP_AGENTS`. Must declare
  ``extends`` (``"acp"`` for any spec-compliant ACP server, or a built-in ACP
  agent id to inherit its launch details) and ``label``. ``extends: "acp"``
  additionally requires ``command``, since there is nothing to inherit.
* **An override of a built-in** — the id of an agent Vicoa already ships. Every
  field is optional; only what is given is replaced. Useful for a nightly
  binary, a proxy endpoint, or ``{"enabled": false}`` to hide one.

Deliberately no ``models`` key. An ACP agent reports its real models over the
protocol at ``session/new``, which the wrapper already surfaces to the in-session
model picker; a static list here would only populate the *pre*-launch picker,
and a wrong one is worse than none.

Validation mirrors :mod:`protocol.plugin_manifest`: return a cleaned,
whitelisted dict plus a list of human-readable errors, and never raise. A
malformed entry is dropped with a message rather than taking the daemon down —
this file is hand-edited, so a typo must not cost the user their sessions.
"""

from __future__ import annotations

import re
from typing import Any


#: Provider ids are lowercase slugs. Matches paseo's rule so a config can be
#: moved between the two, and stays safe as a directory / log-file name.
PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")

#: The sentinel ``extends`` value meaning "a spec-compliant ACP server I will
#: give you the command for", as opposed to inheriting a built-in agent.
ACP_SENTINEL = "acp"

_MAX_STR = 200
_MAX_COMMAND_PARTS = 32
_MAX_ENV_VARS = 64
#: A ceiling on how many providers one config may declare. The realistic number
#: is a handful; this only stops a pathological file from bloating every
#: machine-registration payload.
MAX_PROVIDERS = 64


def is_valid_provider_id(value: Any) -> bool:
    """Whether ``value`` is a well-formed provider id."""
    return isinstance(value, str) and bool(PROVIDER_ID_RE.match(value))


def _is_str(v: Any, *, max_len: int = _MAX_STR) -> bool:
    return isinstance(v, str) and 0 < len(v) <= max_len


def _clean_command(raw: Any, provider_id: str, errors: list[str]) -> list[str] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        errors.append(f"provider {provider_id!r}: 'command' must be a non-empty array")
        return None
    if len(raw) > _MAX_COMMAND_PARTS:
        errors.append(
            f"provider {provider_id!r}: 'command' has more than "
            f"{_MAX_COMMAND_PARTS} parts"
        )
        return None
    parts = [p for p in raw if _is_str(p, max_len=500)]
    if len(parts) != len(raw):
        errors.append(f"provider {provider_id!r}: 'command' entries must be strings")
        return None
    return parts


def _clean_env(raw: Any, provider_id: str, errors: list[str]) -> dict[str, str] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"provider {provider_id!r}: 'env' must be an object")
        return None
    if len(raw) > _MAX_ENV_VARS:
        errors.append(
            f"provider {provider_id!r}: 'env' has more than {_MAX_ENV_VARS} keys"
        )
        return None
    env: dict[str, str] = {}
    for key, value in raw.items():
        if not _is_str(key, max_len=128):
            errors.append(f"provider {provider_id!r}: env key {key!r} is not a string")
            continue
        # Values are secrets often enough (API keys) that a long one is normal.
        if not isinstance(value, str) or len(value) > 4096:
            errors.append(
                f"provider {provider_id!r}: env value for {key!r} is not a string"
            )
            continue
        env[key] = value
    return env or None


def validate_provider(
    provider_id: str, raw: Any, *, builtin_ids: frozenset[str]
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate one ``agents.providers`` entry.

    Returns ``(clean, errors)``; ``clean`` is ``None`` when the entry cannot be
    used at all. ``builtin_ids`` is the set of agent ids this daemon already
    ships, which decides whether ``extends`` / ``label`` are required.
    """
    errors: list[str] = []
    if not is_valid_provider_id(provider_id):
        return None, [
            f"provider id {provider_id!r} must match {PROVIDER_ID_RE.pattern}"
        ]
    if not isinstance(raw, dict):
        return None, [f"provider {provider_id!r} is not a JSON object"]

    is_builtin = provider_id in builtin_ids
    extends = raw.get("extends")
    if extends is not None and not _is_str(extends):
        return None, [f"provider {provider_id!r}: 'extends' must be a string"]
    if not is_builtin:
        if not extends:
            return None, [
                f"provider {provider_id!r} is new, so it must declare 'extends' "
                f"({ACP_SENTINEL!r} or a built-in agent id)"
            ]
        if extends != ACP_SENTINEL and extends not in builtin_ids:
            return None, [
                f"provider {provider_id!r} extends unknown provider {extends!r}"
            ]
        if not _is_str(raw.get("label")):
            return None, [
                f"provider {provider_id!r} is new, so it must declare 'label'"
            ]

    clean: dict[str, Any] = {"id": provider_id}
    if extends:
        clean["extends"] = extends

    for key in ("label", "description", "install_hint"):
        value = raw.get(key)
        if _is_str(value, max_len=500):
            clean[key] = value

    command = _clean_command(raw.get("command"), provider_id, errors)
    if command:
        clean["command"] = command
    # Nothing to inherit a launch command from, so this one is fatal.
    if extends == ACP_SENTINEL and "command" not in clean:
        return None, errors + [
            f"provider {provider_id!r} extends {ACP_SENTINEL!r}, so it must "
            f"declare 'command'"
        ]

    env = _clean_env(raw.get("env"), provider_id, errors)
    if env:
        clean["env"] = env

    if raw.get("enabled") is False:
        clean["enabled"] = False

    timeout = raw.get("initialize_timeout_seconds")
    if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
        if 0 < float(timeout) <= 600:
            clean["initialize_timeout_seconds"] = float(timeout)
        else:
            errors.append(
                f"provider {provider_id!r}: 'initialize_timeout_seconds' must be "
                f"between 0 and 600"
            )

    return clean, errors


def validate_providers(
    raw: Any, *, builtin_ids: frozenset[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Validate the whole ``agents.providers`` map.

    Never raises: a bad entry is dropped with an error message and the rest are
    kept, so one typo in a hand-edited file cannot cost the user every agent.
    """
    if raw is None:
        return {}, []
    if not isinstance(raw, dict):
        return {}, ["'agents.providers' must be an object"]

    clean: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for provider_id, entry in list(raw.items())[:MAX_PROVIDERS]:
        provider, entry_errors = validate_provider(
            str(provider_id), entry, builtin_ids=builtin_ids
        )
        errors.extend(entry_errors)
        if provider is not None:
            clean[str(provider_id)] = provider
    if len(raw) > MAX_PROVIDERS:
        errors.append(
            f"'agents.providers' declares more than {MAX_PROVIDERS} providers; "
            f"the rest were ignored"
        )
    return clean, errors


def read_provider_overrides(
    config: Any, *, builtin_ids: frozenset[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Pull ``agents.providers`` out of a parsed ``~/.vicoa/config.json``."""
    if not isinstance(config, dict):
        return {}, []
    agents = config.get("agents")
    if not isinstance(agents, dict):
        return {}, []
    return validate_providers(agents.get("providers"), builtin_ids=builtin_ids)


__all__ = [
    "ACP_SENTINEL",
    "MAX_PROVIDERS",
    "PROVIDER_ID_RE",
    "is_valid_provider_id",
    "read_provider_overrides",
    "validate_provider",
    "validate_providers",
]
