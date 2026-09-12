"""Machine-local provider management — the ops behind Settings → Providers'
Add / Remove / Check buttons and the ``vicoa provider`` CLI.

A "provider" here is an ACP agent the daemon on *this* machine can launch:
either a built-in row of ``GENERIC_ACP_AGENTS`` or an entry under
``agents.providers`` in ``~/.vicoa/config.json`` (see
:mod:`protocol.provider_overrides`). These functions read and write that file
and never touch the network, so they serve the daemon RPC and the CLI alike —
same posture as :mod:`vicoa.rpc.plugin_ops`.

``provider_add`` writes exactly the hand-editable shape the docs describe, so
an entry added from the catalog and one typed by hand are indistinguishable
afterwards. ``provider_probe`` is the piece track A lacked: it spawns the
agent once and runs the same ``initialize`` → ``session/new`` handshake a
session would (:mod:`integrations.headless.acp_handshake`), reporting where
it stopped and what the agent said. Without it "added" only meant "the id
is in a file".
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional

from integrations.headless.acp_client import ACPClient, ACPError, ACPMethodNotFound
from integrations.headless.acp_handshake import (
    initialize_payloads,
    is_auth_required_error,
    session_models,
    session_modes,
)
from integrations.headless.generic_acp import (
    GENERIC_ACP_AGENTS,
    GenericAgentSpec,
    effective_acp_agents,
    resolve_agent_binary,
)
from protocol.acp_catalog import install_hint_for
from protocol.provider_overrides import (
    ACP_SENTINEL,
    is_valid_provider_id,
    validate_provider,
)

logger = logging.getLogger(__name__)

_BUILTIN_IDS = frozenset(GENERIC_ACP_AGENTS)

#: Default ceiling for one probe. Gemini's spec asks for 180s on a cold start;
#: a probe that takes longer than this is a failure the user needs to see.
DEFAULT_PROBE_TIMEOUT_SECONDS = 60.0
MAX_PROBE_TIMEOUT_SECONDS = 600.0
_STDERR_TAIL_LINES = 20


# ----------------------------------------------------------------------------
# Config file access
# ----------------------------------------------------------------------------


def _read_providers_section() -> dict[str, Any]:
    from vicoa.cli import load_user_config

    agents = load_user_config().get("agents")
    if not isinstance(agents, dict):
        return {}
    providers = agents.get("providers")
    return dict(providers) if isinstance(providers, dict) else {}


def _write_providers_section(providers: dict[str, Any]) -> None:
    """Replace ``agents.providers`` while keeping any sibling ``agents.*`` keys."""
    from vicoa.cli import load_user_config, save_user_config

    agents = load_user_config().get("agents")
    agents = dict(agents) if isinstance(agents, dict) else {}
    agents["providers"] = providers
    save_user_config({"agents": agents})


def _which() -> Callable[[str], Optional[str]]:
    """Binary lookup that sees npm/nvm/volta installs a launchd PATH hides."""
    from vicoa.utils import find_npm_cli

    return find_npm_cli


# ----------------------------------------------------------------------------
# List
# ----------------------------------------------------------------------------


def _describe(
    provider_id: str,
    spec: GenericAgentSpec,
    *,
    source: str,
    enabled: bool,
    which: Callable[[str], Optional[str]],
) -> dict[str, Any]:
    binary = resolve_agent_binary(spec, which=which) if enabled else None
    return {
        "id": provider_id,
        "label": spec.display_name,
        "source": source,
        "enabled": enabled,
        "installed": binary is not None,
        "binary": binary,
        "command": [spec.binaries[0], *spec.acp_args],
        "install_hint": spec.install_hint,
    }


def provider_list() -> dict[str, Any]:
    """Every ACP provider this machine knows, with install state.

    ``source`` is ``"builtin"`` for Vicoa's own table (possibly overridden by
    config), ``"config"`` for an id that exists only in the file. Disabled
    entries are listed with ``enabled: false`` so the UI can offer to
    re-enable them.
    """
    which = _which()
    section = _read_providers_section()
    effective = effective_acp_agents(refresh=True)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for provider_id, spec in effective.items():
        rows.append(
            _describe(
                provider_id,
                spec,
                source="builtin" if provider_id in _BUILTIN_IDS else "config",
                enabled=True,
                which=which,
            )
        )
        seen.add(provider_id)
    # `enabled: false` entries are popped from the effective table; surface
    # them so they can be turned back on without a text editor.
    for provider_id, raw in section.items():
        if provider_id in seen or not isinstance(raw, dict):
            continue
        if raw.get("enabled") is not False:
            continue  # malformed — the daemon log has the reason
        base = GENERIC_ACP_AGENTS.get(provider_id)
        rows.append(
            {
                "id": provider_id,
                "label": str(
                    raw.get("label") or (base.display_name if base else provider_id)
                ),
                "source": "builtin" if provider_id in _BUILTIN_IDS else "config",
                "enabled": False,
                "installed": False,
                "binary": None,
                "command": list(
                    raw.get("command")
                    or ([] if base is None else [base.binaries[0], *base.acp_args])
                ),
                "install_hint": str(
                    raw.get("install_hint") or (base.install_hint if base else "")
                ),
            }
        )
    return {"providers": rows}


# ----------------------------------------------------------------------------
# Add / remove / enable
# ----------------------------------------------------------------------------


def provider_config_from_request(entry: dict[str, Any]) -> dict[str, Any]:
    """Turn an add request into the ``agents.providers[id]`` value.

    Accepts a catalog entry verbatim (``label`` / ``command`` / ``env`` /
    ``description`` / ``install_url``) or the config shape itself (``extends``
    / ``install_hint``). ``install_url`` is folded into ``install_hint`` and
    dropped: the config file stores what to *tell* the user, not a URL the
    UI happens to link.
    """
    config: dict[str, Any] = {}
    extends = entry.get("extends")
    config["extends"] = str(extends) if extends else ACP_SENTINEL
    for key in ("label", "description", "command", "env", "initialize_timeout_seconds"):
        if entry.get(key) not in (None, "", [], {}):
            config[key] = entry[key]
    hint = entry.get("install_hint")
    if not hint and entry.get("install_url"):
        hint = install_hint_for(entry)
    if hint:
        config["install_hint"] = hint
    return config


def provider_add(entry: dict[str, Any], *, overwrite: bool = False) -> dict[str, Any]:
    """Add (or, with ``overwrite``, replace) one provider in the config file.

    ``entry`` must carry ``id``; the rest is validated by
    :func:`protocol.provider_overrides.validate_provider` — the same gate the
    daemon applies when it reads the file, so nothing this writes can be
    rejected later. Returns the row :func:`provider_list` would show, so the
    caller learns at once whether the binary is already there.
    """
    if not isinstance(entry, dict):
        return {"error": "entry must be an object"}
    provider_id = str(entry.get("id") or "").strip()
    if not is_valid_provider_id(provider_id):
        return {"error": "provider id must match ^[a-z][a-z0-9-]*$"}

    section = _read_providers_section()
    if provider_id in section and not overwrite:
        return {"error": f"provider '{provider_id}' is already in your config"}
    if provider_id in _BUILTIN_IDS and "extends" not in entry:
        # Overriding a built-in is a different, rarer thing (a nightly binary,
        # a proxy env). The catalog never does it; a CLI user can pass the
        # config shape explicitly.
        return {
            "error": f"'{provider_id}' is a built-in agent; edit ~/.vicoa/config.json to override it"
        }

    config = provider_config_from_request(entry)
    clean, errors = validate_provider(provider_id, config, builtin_ids=_BUILTIN_IDS)
    if clean is None:
        return {"error": "; ".join(errors) or "invalid provider"}
    clean.pop("id", None)

    section[provider_id] = clean
    _write_providers_section(section)
    spec = effective_acp_agents(refresh=True).get(provider_id)
    if spec is None:  # cannot happen after validate_provider, but never 500
        return {"error": f"provider '{provider_id}' did not load; see the daemon log"}
    row = _describe(provider_id, spec, source="config", enabled=True, which=_which())
    row["warnings"] = errors
    return row


def provider_remove(provider_id: str) -> dict[str, Any]:
    """Delete a provider's entry from the config file.

    For a built-in id this drops the *override* (the agent reverts to
    Vicoa's own definition) — the built-in itself cannot be removed, only
    hidden with ``enabled: false``.
    """
    section = _read_providers_section()
    if provider_id not in section:
        if provider_id in _BUILTIN_IDS:
            return {
                "error": f"'{provider_id}' is built in; disable it instead of removing it"
            }
        return {"error": f"provider '{provider_id}' is not in your config"}
    del section[provider_id]
    _write_providers_section(section)
    effective_acp_agents(refresh=True)
    return {"id": provider_id, "removed": True}


def provider_set_enabled(provider_id: str, enabled: bool) -> dict[str, Any]:
    """Hide or un-hide a provider without losing its definition."""
    section = _read_providers_section()
    raw = section.get(provider_id)
    if raw is None and provider_id not in _BUILTIN_IDS:
        return {"error": f"provider '{provider_id}' is not in your config"}
    raw = dict(raw) if isinstance(raw, dict) else {}
    if enabled:
        raw.pop("enabled", None)
        if not raw and provider_id in _BUILTIN_IDS:
            section.pop(provider_id, None)  # bare `{}` override adds nothing
        else:
            section[provider_id] = raw
    else:
        raw["enabled"] = False
        section[provider_id] = raw
    _write_providers_section(section)
    effective_acp_agents(refresh=True)
    return {"id": provider_id, "enabled": enabled}


# ----------------------------------------------------------------------------
# Probe
# ----------------------------------------------------------------------------


def _refuse_agent_request(
    method: str, _params: dict[str, Any]
) -> Optional[dict[str, Any]]:
    # A probe never prompts and never runs anything for the agent. Anything it
    # asks for before the first prompt is answered "not supported" so it can
    # decide for itself rather than hang on us.
    raise ACPMethodNotFound(method)


def provider_probe(
    provider_id: str,
    *,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    """Launch a provider once and run the session handshake against it.

    Stages, in order — the result names the one it stopped at:

    ``binary``       the launcher is not on this machine (or not on PATH)
    ``spawn``        it is, but the process would not start
    ``initialize``   started, but never answered ``initialize`` (wrong flags,
                     not actually an ACP server, crashed — see ``stderr``)
    ``session_new``  handshake fine, but no session: usually "log in with
                     the agent's own CLI first"
    ``ok``           the agent is usable; ``models`` / ``modes`` are what a
                     session would get

    ``cwd`` defaults to a throwaway directory so the probe can never touch a
    project; some agents care about the directory (trust prompts, project
    config), so a caller may pass a real one.
    """
    spec = effective_acp_agents().get(provider_id)
    if spec is None:
        return {"error": f"unknown provider '{provider_id}'"}

    result: dict[str, Any] = {
        "id": provider_id,
        "label": spec.display_name,
        "ok": False,
        "stage": "binary",
        "installed": False,
        "command": [spec.binaries[0], *spec.acp_args],
    }
    binary = resolve_agent_binary(spec, which=_which())
    if binary is None:
        tried = "', '".join(spec.binaries)
        result["error"] = (
            f"'{tried}' is not installed or not on the daemon's PATH. {spec.install_hint}".strip()
        )
        return result
    result["installed"] = True
    result["binary"] = binary
    command = [binary, *spec.acp_args]
    result["command"] = command

    budget = (
        float(timeout)
        if timeout
        else spec.initialize_timeout_seconds or DEFAULT_PROBE_TIMEOUT_SECONDS
    )
    budget = max(1.0, min(budget, MAX_PROBE_TIMEOUT_SECONDS))

    stderr_tail: deque[str] = deque(maxlen=_STDERR_TAIL_LINES)
    scratch = None
    if not cwd:
        scratch = tempfile.mkdtemp(prefix="vicoa-provider-probe-")
        cwd = scratch
    started = time.monotonic()

    client = ACPClient(
        command=command,
        cwd=cwd,
        env=dict(spec.env),
        on_request=_refuse_agent_request,
        on_error=lambda line: stderr_tail.append(line.rstrip()),
        log_func=lambda msg: logger.debug("[probe %s] %s", provider_id, msg),
    )
    try:
        result["stage"] = "spawn"
        try:
            client.start()
        except Exception as exc:
            result["error"] = f"could not start '{command[0]}': {exc}"
            return result

        result["stage"] = "initialize"
        init_result: Optional[dict[str, Any]] = None
        last_error: Optional[Exception] = None
        for payload in initialize_payloads():
            remaining = budget - (time.monotonic() - started)
            if remaining <= 0:
                break
            try:
                response = client.send_request("initialize", payload, timeout=remaining)
                response.raise_for_error()
                init_result = response.result or {}
                break
            except ACPError as exc:
                last_error = exc
                if client.process is not None and client.process.poll() is not None:
                    break  # it died; retrying a payload will not help
        if init_result is None:
            result["error"] = _explain_failure(
                f"no answer to initialize within {budget:.0f}s"
                if last_error is None or "timed out" in str(last_error).lower()
                else str(last_error),
                client,
                stderr_tail,
            )
            return result
        result["protocol_version"] = init_result.get("protocolVersion")
        agent_info = init_result.get("agentInfo")
        if isinstance(agent_info, dict):
            result["agent"] = {
                k: str(v)
                for k, v in agent_info.items()
                if k in ("name", "title", "version") and v
            }
        auth_methods = [
            str(m.get("id"))
            for m in (init_result.get("authMethods") or [])
            if isinstance(m, dict) and m.get("id")
        ]
        result["auth_methods"] = auth_methods

        result["stage"] = "session_new"
        params = {"cwd": cwd, "mcpServers": []}
        try:
            session = _session_new(
                client, params, budget - (time.monotonic() - started)
            )
        except ACPError as exc:
            if is_auth_required_error(exc) and auth_methods:
                try:
                    remaining = max(1.0, budget - (time.monotonic() - started))
                    auth = client.send_request(
                        "authenticate", {"methodId": auth_methods[0]}, timeout=remaining
                    )
                    auth.raise_for_error()
                    session = _session_new(
                        client, params, budget - (time.monotonic() - started)
                    )
                except ACPError as auth_exc:
                    result["error"] = _explain_failure(
                        f"needs authentication ({', '.join(auth_methods)}); "
                        f"log in with the agent's own CLI on this machine first. {auth_exc}",
                        client,
                        stderr_tail,
                    )
                    return result
            else:
                result["error"] = _explain_failure(str(exc), client, stderr_tail)
                return result

        result["ok"] = True
        result["stage"] = "ok"
        result["session_id"] = session.get("sessionId")
        result["models"] = session_models(session)
        result["modes"] = session_modes(session)
        return result
    finally:
        result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        if stderr_tail:
            result["stderr"] = list(stderr_tail)
        try:
            client.stop()
        except Exception:
            logger.debug("probe %s: stop failed", provider_id, exc_info=True)
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)


def _session_new(
    client: ACPClient, params: dict[str, Any], remaining: float
) -> dict[str, Any]:
    response = client.send_request("session/new", params, timeout=max(1.0, remaining))
    response.raise_for_error()
    session = response.result or {}
    if not session.get("sessionId"):
        raise ACPError("session/new response missing sessionId")
    return session


def _explain_failure(message: str, client: ACPClient, stderr_tail: deque[str]) -> str:
    """Attach the exit code and the last meaningful stderr line: that is where
    the real reason usually is ("command not found: acp", "run `x login`")."""
    parts = [message]
    process = client.process
    if (
        process is not None
        and process.poll() is not None
        and "exited with code" not in message
    ):
        parts.append(f"(process exited with code {process.returncode})")
    # Agents that dump JSON to stderr end on a bare `}`; walk back to a line
    # that says something.
    for line in reversed(stderr_tail):
        if sum(ch.isalnum() for ch in line) >= 3:
            parts.append(f"stderr: {line.strip()}")
            break
    return " ".join(parts)


def config_path() -> Path:
    from vicoa.cli import get_user_config_path

    return Path(get_user_config_path())


__all__ = [
    "DEFAULT_PROBE_TIMEOUT_SECONDS",
    "config_path",
    "provider_add",
    "provider_config_from_request",
    "provider_list",
    "provider_probe",
    "provider_remove",
    "provider_set_enabled",
]
