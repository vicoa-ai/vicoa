"""The Pi-family agent table.

``omp`` is a fork of ``pi``: the RPC envelope, the event stream and the
message shapes are the same, and the deltas are small and enumerable. So this
module is the *only* place the two agents differ — everything downstream reads
a :class:`PiFamilySpec` field instead of branching on an agent id. Adding a
third fork should be a table row, not a new wrapper (the same posture
``generic_acp.py`` takes for the five ACP agents).

Every value below was probed against the installed CLIs (pi 0.85.0, omp
18.1.10) and cross-checked against their shipped TypeScript RPC definitions
(``modes/rpc/rpc-types.ts``), not inferred from documentation.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional, Tuple


@dataclass(frozen=True)
class PiFamilySpec:
    """Static description of one Pi-family agent CLI."""

    catalog_id: str  # id in protocol/agent_catalog.py ("pi" | "omp")
    display_name: str  # agent_type shown in the dashboard
    binaries: Tuple[str, ...]  # PATH candidates, first match wins

    # -- transport / handshake -------------------------------------------
    #: ``--mode`` value. Both support ``rpc``; omp also has ``rpc-ui`` but the
    #: dialog frames we care about (``select``/``input``/``confirm``) already
    #: arrive in plain ``rpc``, so there is no reason to opt into the richer
    #: surface.
    protocol_mode: str = "rpc"
    #: omp announces itself with an unsolicited ``{"type":"ready",...}`` frame
    #: before anything else; pi answers requests straight away and never sends
    #: one. Waiting for a frame pi will not send would hang bring-up.
    expects_ready_frame: bool = False
    #: Protocol version to negotiate once ready. omp's v2 adds ``rpc_chunk``
    #: reassembly for frames over 1 MiB (see ``transport.py``). pi has no
    #: ``negotiate_protocol`` command at all.
    negotiate_protocol_version: Optional[int] = None

    # -- RPC surface deltas ----------------------------------------------
    #: Slash-command listing RPC. pi: ``get_commands``; omp renamed it.
    commands_rpc: str = "get_commands"
    #: ``agent_end`` is "one low-level run finished" for both agents and may be
    #: followed by a retry, a compaction, or a queued continuation. pi emits a
    #: separate ``agent_settled`` once the whole prompt is done; omp instead
    #: stamps ``isTerminal`` on ``agent_end``. Either way the runner also keeps
    #: a short settle grace (see ``session.py``) so a version that drops the
    #: signal can't wedge a turn.
    settle_event: Optional[str] = None

    # -- capabilities -----------------------------------------------------
    supports_host_tools: bool = False
    supports_subagents: bool = False
    #: omp: ``branch``/``get_branch_messages``; pi: ``fork``/``get_fork_messages``.
    #: Declared here for Vicoa's own (not yet built) agent-agnostic rewind
    #: control — nothing in this wrapper acts on it yet.
    supports_branching: bool = False
    supports_handoff: bool = False
    supports_compaction: bool = True

    # -- launch flags ------------------------------------------------------
    model_arg: Optional[str] = "--model"
    thinking_arg: Optional[str] = "--thinking"
    #: Thinking levels the CLI accepts. Vicoa's catalog enum is a subset of
    #: this on purpose; anything outside is dropped at the launch boundary
    #: rather than passed through and rejected at startup.
    thinking_levels: Tuple[str, ...] = (
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    )
    #: Approval flag + the Vicoa ``permission_mode`` -> flag-value mapping.
    #: ``None`` means the agent has no approval knob (pi), in which case the
    #: catalog carries no ``permission_modes`` either.
    approval_mode_arg: Optional[str] = None
    approval_modes: Mapping[str, str] = field(default_factory=dict)
    #: Resume flag. Hidden on omp but real: it *resolves* an existing session
    #: and exits 1 with ``Session "<id>" not found.`` for an unknown one — it
    #: never creates. So the first launch carries no session flag, the id is
    #: read back from ``get_state`` and persisted, and only a later resume
    #: passes it.
    session_arg: Optional[str] = "--session"
    #: Extra argv appended verbatim, before the per-session flags.
    extra_args: Tuple[str, ...] = ()

    # -- environment gates -------------------------------------------------
    #: Minimum CLI version we have actually validated against.
    min_version: Optional[str] = None
    #: Minimum Bun version, when the CLI runs on Bun rather than node. omp
    #: ships a ``#!/usr/bin/env bun`` shebang without bundling Bun and hard
    #: fails at startup below this version, so ``shutil.which`` alone is not a
    #: sufficient install check.
    requires_bun: Optional[str] = None
    install_hint: str = ""
    #: Directories to search when the binary isn't on PATH. ``~`` is expanded.
    extra_dirs: Tuple[str, ...] = ()


PI_FAMILY_AGENTS: Dict[str, PiFamilySpec] = {
    "omp": PiFamilySpec(
        catalog_id="omp",
        display_name="Oh My Pi",
        binaries=("omp",),
        expects_ready_frame=True,
        negotiate_protocol_version=2,
        commands_rpc="get_available_commands",
        settle_event=None,  # omp marks the terminal agent_end with isTerminal
        supports_host_tools=True,
        supports_subagents=True,
        supports_branching=True,
        supports_handoff=True,
        approval_mode_arg="--approval-mode",
        # Vicoa's shared permission_mode slugs -> omp's --approval-mode values.
        # Reusing the existing slugs (rather than minting ask/write/full) keeps
        # the clients' mode picker and the daemon's PERMISSION_MODES validation
        # unchanged; this table owns the translation, the same way
        # codex/permission_translate.py does for Codex.
        approval_modes={
            "default": "always-ask",
            "acceptEdits": "write",
            "bypassPermissions": "yolo",
        },
        # omp adds `auto` on top of pi's levels.
        thinking_levels=(
            "off",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
            "auto",
        ),
        min_version="16.3.9",
        requires_bun="1.3.14",
        install_hint=(
            "Install Oh My Pi: brew install can1357/tap/omp "
            "(or curl -fsSL https://omp.sh/install | sh). The npm package "
            "needs Bun >= 1.3.14 on your PATH."
        ),
    ),
    "pi": PiFamilySpec(
        catalog_id="pi",
        display_name="Pi",
        binaries=("pi",),
        expects_ready_frame=False,
        negotiate_protocol_version=None,
        commands_rpc="get_commands",
        settle_event="agent_settled",
        supports_host_tools=False,  # `set_host_tools` -> "Unknown command"
        supports_subagents=False,
        supports_branching=True,  # `fork` / `get_fork_messages`
        supports_handoff=False,
        approval_mode_arg=None,  # pi has no approval flag at all
        min_version="0.85.0",
        requires_bun=None,  # plain node
        install_hint=("Install Pi: npm install -g @earendil-works/pi-coding-agent"),
    ),
}


def resolve_agent_binary(
    spec: PiFamilySpec,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[str]:
    """Locate an agent's binary, returning the command to run (or ``None``).

    Same contract as ``generic_acp.resolve_agent_binary`` — checks ``which``
    (PATH / npm locations) first, then the spec's ``extra_dirs`` — so spawn
    resolution and the daemon's install detection can share one implementation
    and never disagree. ``which`` resolves at call time (not bound as a default
    argument) so tests can monkeypatch ``spec.shutil.which``.
    """
    if which is None:
        which = shutil.which
    for candidate in spec.binaries:
        if which(candidate):
            return candidate
    for directory in spec.extra_dirs:
        base = os.path.expanduser(directory)
        for candidate in spec.binaries:
            full = os.path.join(base, candidate)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                return full
    return None


_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_version(text: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """First ``major.minor.patch`` triple in ``text``, or ``None``.

    Deliberately lenient: ``omp --version`` prints ``omp/18.1.10`` and
    ``bun --version`` prints a bare ``1.4.1``, and neither format is a
    contract we control.
    """
    if not text:
        return None
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def version_at_least(actual: Optional[str], minimum: Optional[str]) -> bool:
    """Whether ``actual`` satisfies ``minimum``. Unparseable ``actual`` passes.

    Failing *open* is deliberate: a version string we can't read is much more
    likely to be an upstream format change than a genuinely old install, and
    blocking the spawn on it would break every user the day the format moves.
    The startup error path still catches a truly incompatible runtime.
    """
    want = parse_version(minimum)
    if want is None:
        return True
    have = parse_version(actual)
    if have is None:
        return True
    return have >= want


def _run_version(command: list[str]) -> Optional[str]:
    """Run ``command`` and return its combined output, or ``None`` if it fails."""
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{proc.stdout}\n{proc.stderr}".strip() or None


def check_runtime_requirements(
    spec: PiFamilySpec,
    *,
    which: Optional[Callable[[str], Optional[str]]] = None,
    run_version: Callable[[list[str]], Optional[str]] = _run_version,
) -> Optional[str]:
    """Return an error string when the agent can't actually run here.

    This is more than ``shutil.which``: omp is the only agent in the catalog
    with a runtime dependency outside itself. It ships a ``#!/usr/bin/env bun``
    shebang and refuses to start below Bun 1.3.14 —

        error: Bun runtime must be >= 1.3.14 (found v1.3.12)

    — which, without this check, surfaces to the user as an unexplained
    "process exited with code 1" *after* a session row has already been
    created. Returns ``None`` when everything needed is present.
    """
    binary = resolve_agent_binary(spec, which=which)
    if binary is None:
        tried = "', '".join(spec.binaries)
        return (
            f"{spec.display_name} CLI ('{tried}') is not installed or not on "
            f"PATH. {spec.install_hint}"
        )
    if spec.requires_bun:
        bun = (which or shutil.which)("bun")
        if not bun:
            return (
                f"{spec.display_name} runs on Bun, which is not installed or "
                f"not on PATH. Install Bun >= {spec.requires_bun} "
                f"(https://bun.sh), or install {spec.display_name} via a "
                f"bundled build. {spec.install_hint}"
            )
        bun_version = run_version([bun, "--version"])
        if not version_at_least(bun_version, spec.requires_bun):
            found = (bun_version or "unknown").strip()
            return (
                f"{spec.display_name} needs Bun >= {spec.requires_bun} but "
                f"this machine has {found}. Run `bun upgrade` and retry."
            )
    return None


__all__ = [
    "PI_FAMILY_AGENTS",
    "PiFamilySpec",
    "check_runtime_requirements",
    "parse_version",
    "resolve_agent_binary",
    "version_at_least",
]
