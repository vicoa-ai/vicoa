#!/usr/bin/env python3
"""Generic headless ACP integration for Vicoa.

One module drives every agent whose integration surface is a spec-compliant
ACP server subcommand: Cursor (``cursor-agent acp``), Gemini CLI
(``gemini --experimental-acp``), Copilot CLI (``copilot --acp --stdio``),
Kimi CLI (``kimi acp``) and Hermes (``hermes acp``). Each agent is one
:class:`GenericAgentSpec` table row — adding another ACP agent is a table
entry plus catalog/UI plumbing, not a new wrapper.

The protocol behavior (initialize handshake, session/new + authenticate,
prompt turns with stopReason handling, permission round-trips, mode
switching, interrupts) all lives in :class:`ACPWrapperBase`; this module
only contributes spawn specifics and spawn-time model application.

Spawned by ``machine_daemon._build_headless_command`` as::

    python -m integrations.headless.generic_acp --agent cursor \
        --api-key ... --base-url ... --project-path ... [--session-id ...]
        [--model ...] [--permission-mode ...] [--prompt ...]
"""

import argparse
import logging
import os
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from integrations.headless.acp_base import ACPWrapperBase, ACPWrapperConfig


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenericAgentSpec:
    """Static description of one ACP-served agent CLI."""

    catalog_id: str  # id in shared/agent_catalog.py ("cursor", "gemini", …)
    display_name: str  # agent_type shown in the dashboard
    binaries: tuple[str, ...]  # PATH candidates, first match wins
    acp_args: tuple[str, ...]  # appended to the binary to start ACP mode
    env: Dict[str, str] = field(default_factory=dict)
    initialize_timeout_seconds: float = 60.0
    install_hint: str = ""
    # Launch flag that sets the model at spawn (e.g. "--model"). Set only for
    # agents whose ACP model surface is the dedicated `models` block (Gemini,
    # Kimi), which can't be set via session config options — passing the model
    # on the command line is the reliable, documented path. None = rely on the
    # in-protocol config-option path (cursor/copilot) instead.
    model_arg: Optional[str] = None
    # Whether the model flag must precede the ACP args. Needed when ACP mode is
    # a *subcommand* and the model flag is a global option (Kimi:
    # `kimi --model X acp`). False when ACP mode is an option and order is free
    # (Gemini: `gemini --experimental-acp --model X`).
    model_arg_first: bool = False
    # Extra directories to search for the binary when it isn't on PATH (e.g.
    # kimi-code installs to ~/.kimi-code/bin, which isn't added to PATH). `~`
    # is expanded. Used by both spawn resolution and daemon install detection.
    extra_dirs: tuple[str, ...] = ()


GENERIC_ACP_AGENTS: Dict[str, GenericAgentSpec] = {
    "cursor": GenericAgentSpec(
        catalog_id="cursor",
        display_name="Cursor",
        # Shipped as `cursor-agent`, later renamed `agent` — accept both.
        binaries=("cursor-agent", "agent"),
        acp_args=("acp",),
        install_hint=(
            "Install the Cursor CLI: curl https://cursor.com/install -fsS | bash"
        ),
    ),
    "gemini": GenericAgentSpec(
        catalog_id="gemini",
        display_name="Gemini CLI",
        binaries=("gemini",),
        # `--acp` is the current flag with `--experimental-acp` kept as an
        # alias; older installs only know the experimental spelling, so the
        # legacy flag covers both.
        acp_args=("--experimental-acp",),
        # Suppress the OAuth browser popup when spawned headlessly; the CLI
        # must already be authenticated (cached creds or GEMINI_API_KEY).
        env={"NO_BROWSER": "true"},
        # First ACP start is slow (model/tooling warmup) — happy ships 120s.
        initialize_timeout_seconds=180.0,
        # Gemini exposes models via the dedicated `models` block (no config
        # option), so set the spawn-time model with its own `--model` flag.
        model_arg="--model",
        install_hint="Install the Gemini CLI: npm install -g @google/gemini-cli",
    ),
    "copilot": GenericAgentSpec(
        catalog_id="copilot",
        display_name="Copilot CLI",
        binaries=("copilot",),
        acp_args=("--acp", "--stdio"),
        install_hint="Install the Copilot CLI: npm install -g @github/copilot",
    ),
    "kimi": GenericAgentSpec(
        catalog_id="kimi",
        display_name="Kimi CLI",
        binaries=("kimi",),
        acp_args=("acp",),
        # Kimi uses the dedicated models block; set the spawn-time model with
        # its global `--model` flag, which must precede the `acp` subcommand:
        # `kimi --model <alias> acp`.
        model_arg="--model",
        model_arg_first=True,
        # kimi-code installs to ~/.kimi-code/bin (not on PATH); legacy
        # kimi-cli to ~/.kimi/bin.
        extra_dirs=("~/.kimi-code/bin", "~/.kimi/bin"),
        install_hint=(
            "Install the Kimi CLI: see https://github.com/MoonshotAI/kimi-cli"
        ),
    ),
    "hermes": GenericAgentSpec(
        catalog_id="hermes",
        display_name="Hermes",
        binaries=("hermes",),
        acp_args=("acp",),
        install_hint=(
            "Install Hermes: curl -fsSL "
            "https://hermes-agent.nousresearch.com/install.sh | bash"
        ),
    ),
}


#: Cache for :func:`effective_acp_agents`, keyed on the config file's mtime.
#: The daemon consults the table on every spawn and every install probe, so
#: the file is not re-parsed each time — but `vicoa provider add` and a hand
#: edit both change it under a running daemon, and the user should not have to
#: restart (which kills live sessions) for the new agent to be spawnable. One
#: ``stat`` per call is the price.
_EFFECTIVE_CACHE: Optional[Dict[str, GenericAgentSpec]] = None
_EFFECTIVE_CACHE_STAMP: Optional[float] = None


def _config_stamp() -> Optional[float]:
    """mtime of ``~/.vicoa/config.json``; None when it is absent/unreadable."""
    try:
        from vicoa.cli import get_user_config_path

        return os.stat(get_user_config_path()).st_mtime
    except Exception:
        return None


def spec_from_override(
    provider_id: str,
    override: Dict[str, object],
    base_specs: Dict[str, GenericAgentSpec],
) -> Optional[GenericAgentSpec]:
    """Build one :class:`GenericAgentSpec` from a validated config entry.

    ``command`` replaces the launch argv wholesale (paseo's semantics): its
    first element is the binary and the rest are the args that put it in ACP
    mode. Everything not named is inherited from ``extends``, so a profile that
    only swaps ``env`` keeps the base agent's binary names, timeouts and
    model-flag ordering.
    """
    extends = str(override.get("extends") or "")
    if extends and extends != "acp":
        base = base_specs.get(extends)
    else:
        base = base_specs.get(provider_id)

    command = override.get("command")
    command_parts = [str(part) for part in command] if isinstance(command, list) else []

    if base is None:
        # extends: "acp" — nothing to inherit, so the command is the whole
        # definition. The validator guarantees it is present.
        if not command_parts:
            return None
        binaries: tuple[str, ...] = (command_parts[0],)
        acp_args: tuple[str, ...] = tuple(command_parts[1:])
        display_name = str(override.get("label") or provider_id)
        env: Dict[str, str] = {}
        initialize_timeout = 60.0
        install_hint = ""
        model_arg = None
        model_arg_first = False
        extra_dirs: tuple[str, ...] = ()
    else:
        binaries = (command_parts[0],) if command_parts else base.binaries
        acp_args = tuple(command_parts[1:]) if command_parts else base.acp_args
        display_name = str(override.get("label") or base.display_name)
        env = dict(base.env)
        initialize_timeout = base.initialize_timeout_seconds
        install_hint = base.install_hint
        model_arg = base.model_arg
        model_arg_first = base.model_arg_first
        extra_dirs = base.extra_dirs

    override_env = override.get("env")
    if isinstance(override_env, dict):
        env.update({str(k): str(v) for k, v in override_env.items()})

    timeout = override.get("initialize_timeout_seconds")
    if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
        initialize_timeout = float(timeout)

    hint = override.get("install_hint")
    if isinstance(hint, str) and hint:
        install_hint = hint

    return GenericAgentSpec(
        catalog_id=provider_id,
        display_name=display_name,
        binaries=binaries,
        acp_args=acp_args,
        env=env,
        initialize_timeout_seconds=initialize_timeout,
        install_hint=install_hint,
        model_arg=model_arg,
        model_arg_first=model_arg_first,
        extra_dirs=extra_dirs,
    )


def build_effective_acp_agents(
    overrides: Dict[str, Dict[str, object]],
) -> Dict[str, GenericAgentSpec]:
    """Merge validated config overrides over the built-in spec table.

    Pure, so the daemon and the wrapper subprocess derive the same table from
    the same config, and tests do not have to touch the filesystem.
    """
    effective = dict(GENERIC_ACP_AGENTS)
    for provider_id, override in overrides.items():
        if override.get("enabled") is False:
            effective.pop(provider_id, None)
            continue
        spec = spec_from_override(provider_id, override, GENERIC_ACP_AGENTS)
        if spec is not None:
            effective[provider_id] = spec
    return effective


def effective_acp_agents(*, refresh: bool = False) -> Dict[str, GenericAgentSpec]:
    """The built-in ACP agents plus whatever ``~/.vicoa/config.json`` adds.

    This is the table every caller should use — the built-in
    :data:`GENERIC_ACP_AGENTS` is only the starting point. Falls back to the
    built-ins on any config problem: an unreadable or malformed file must cost
    the user their *custom* agents, never the ones Vicoa ships.
    """
    global _EFFECTIVE_CACHE, _EFFECTIVE_CACHE_STAMP
    stamp = _config_stamp()
    if _EFFECTIVE_CACHE is not None and not refresh and stamp == _EFFECTIVE_CACHE_STAMP:
        return _EFFECTIVE_CACHE

    try:
        from protocol.provider_overrides import read_provider_overrides
        from vicoa.cli import load_user_config

        overrides, errors = read_provider_overrides(
            load_user_config(), builtin_ids=frozenset(GENERIC_ACP_AGENTS)
        )
        for error in errors:
            logger.warning("agents.providers: %s", error)
        _EFFECTIVE_CACHE = build_effective_acp_agents(overrides)
    except Exception:
        logger.warning("agents.providers: config unreadable; using built-ins only")
        _EFFECTIVE_CACHE = dict(GENERIC_ACP_AGENTS)
    _EFFECTIVE_CACHE_STAMP = stamp
    return _EFFECTIVE_CACHE


def resolve_agent_binary(
    spec: GenericAgentSpec,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[str]:
    """Locate an agent's binary, returning the command to run (or None).

    Checks ``which`` (PATH / npm locations) for each candidate first, then the
    spec's ``extra_dirs`` (e.g. kimi-code's ~/.kimi-code/bin, which isn't on
    PATH). Shared by spawn resolution and the daemon's install detection so the
    two never disagree.

    ``which`` defaults to ``shutil.which`` resolved at call time (not bound as a
    default argument) so tests can monkeypatch ``generic_acp.shutil.which``.
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


class GenericACPConfig(ACPWrapperConfig):
    """Configuration for a spec-table agent."""

    def __init__(
        self,
        spec: GenericAgentSpec,
        *,
        api_key: str,
        base_url: str,
        agent_instance_id: str,
        project_path: str,
        model: Optional[str] = None,
        permission_mode: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        is_resuming: bool = False,
        acp_session_id: Optional[str] = None,
        agent_command: Optional[str] = None,
        name: Optional[str] = None,
    ):
        self.spec = spec
        self.api_key = api_key
        self.base_url = base_url
        self.agent_instance_id = agent_instance_id
        self.project_path = project_path

        self.agent_type = name or spec.display_name
        self.agent_command = agent_command or spec.binaries[0]
        self.catalog_agent_id = spec.catalog_id
        self.initialize_timeout_seconds = spec.initialize_timeout_seconds

        self.model = model
        self.permission_mode = permission_mode
        self.name = name or spec.display_name
        self.is_resuming = is_resuming
        self.acp_session_id = acp_session_id
        self.initial_prompt = initial_prompt
        self.system_prompt = system_prompt

        # Explicit binary path from --agent-command (skips PATH resolution).
        self._agent_command_override = agent_command

    def resolve_binary(self) -> str:
        if self._agent_command_override:
            return self._agent_command_override
        resolved = resolve_agent_binary(self.spec)
        if resolved is not None:
            return resolved
        tried = ", ".join(self.spec.binaries)
        raise FileNotFoundError(
            f"{self.spec.display_name} CLI not found on PATH (tried: {tried}). "
            f"{self.spec.install_hint}"
        )

    def get_acp_command(self) -> list[str]:
        binary = self.resolve_binary()
        # Spawn-time model via the agent's own launch flag. Skip "auto"/
        # "default" (and empty) — those mean "let the agent choose".
        model = (self.model or "").strip()
        model_part = (
            [self.spec.model_arg, model]
            if self.spec.model_arg and model and model not in {"auto", "default"}
            else []
        )
        if self.spec.model_arg_first:
            # e.g. `kimi --model X acp` — global flag before the subcommand.
            return [binary, *model_part, *self.spec.acp_args]
        # e.g. `gemini --experimental-acp --model X` — order-free options.
        return [binary, *self.spec.acp_args, *model_part]

    def get_acp_env(self) -> dict[str, str]:
        return dict(self.spec.env)

    @classmethod
    def from_args(
        cls,
        spec: GenericAgentSpec,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        project_path: Optional[str] = None,
        agent_instance_id: Optional[str] = None,
        model: Optional[str] = None,
        permission_mode: Optional[str] = None,
        initial_prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        is_resuming: bool = False,
        acp_session_id: Optional[str] = None,
        agent_command: Optional[str] = None,
        name: Optional[str] = None,
    ) -> "GenericACPConfig":
        final_api_key = api_key or os.environ.get("VICOA_API_KEY")
        if not final_api_key:
            raise ValueError(
                "Vicoa API key required: provide --api-key or set VICOA_API_KEY"
            )

        final_base_url = (
            base_url
            or os.environ.get("VICOA_API_URL")
            or os.environ.get("VICOA_BASE_URL")
            or "https://api.vicoa.ai"
        )

        return cls(
            spec,
            api_key=final_api_key,
            base_url=final_base_url,
            agent_instance_id=agent_instance_id or str(uuid.uuid4()),
            project_path=project_path or os.getcwd(),
            model=model,
            permission_mode=permission_mode,
            initial_prompt=initial_prompt,
            system_prompt=system_prompt,
            is_resuming=is_resuming,
            acp_session_id=acp_session_id,
            agent_command=agent_command,
            name=name,
        )


class GenericACPWrapper(ACPWrapperBase):
    """Headless wrapper for spec-table ACP agents."""

    config: GenericACPConfig

    _prompt_timeout_seconds: float = 3600.0
    _prompt_cancel_grace_period_seconds: float = 15.0
    _hard_interrupt_fallback_delay_seconds: float = 2.0

    def build_session_config(self) -> Optional[dict]:
        sc = {
            "agent": self.config.catalog_agent_id,
            "model": self.config.model,
            "permission_mode": self.config.permission_mode,
        }
        return {k: v for k, v in sc.items() if v is not None}

    def create_session(self) -> None:
        super().create_session()
        # When the model was set via the agent's launch flag, the session
        # already starts on it — the config-option path would be a no-op (or
        # redundant). Only use it for agents without a launch flag.
        # ``_apply_initial_model`` lives on ACPWrapperBase (shared with OpenCode).
        if self.config.model and not self.config.spec.model_arg:
            self._apply_initial_model(self.config.model)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generic headless ACP agent integration for Vicoa"
    )
    agents = effective_acp_agents()
    parser.add_argument(
        "--agent",
        required=True,
        # The effective table, not the built-ins: the daemon spawns us with a
        # user-defined provider id whenever ~/.vicoa/config.json declares one.
        choices=sorted(agents),
        help="Which ACP agent to run",
    )
    parser.add_argument("--api-key", help="Vicoa API key")
    parser.add_argument("--base-url", help="Vicoa base URL")
    parser.add_argument("--project-path", help="Project directory")
    parser.add_argument("--session-id", help="Session ID")
    parser.add_argument(
        "--resume",
        help=(
            "Reattach to an existing Vicoa agent instance by id "
            "(skips registration). This does NOT restore the agent's "
            "conversation -- pass --acp-session-id for that."
        ),
    )
    parser.add_argument(
        "--acp-session-id",
        default=None,
        help=(
            "The agent's own prior session id, restored via ACP "
            "session/load so the conversation continues. Ignored when "
            "the agent does not advertise loadSession."
        ),
    )
    parser.add_argument("--model", help="Model id from the agent catalog")
    parser.add_argument(
        "--permission-mode", help="Initial ACP session mode (e.g. plan)"
    )
    parser.add_argument("--name", help="Agent display name override")
    parser.add_argument("--agent-command", help="Explicit path to the agent binary")
    parser.add_argument(
        "--prompt", default=None, help="Initial prompt to send on session start"
    )
    parser.add_argument(
        "--system-prompt",
        dest="system_prompt",
        default=None,
        help="Custom instructions, prefixed onto every turn (ACP has no system-prompt slot)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    spec = agents[args.agent]
    agent_instance_id = args.resume or args.session_id

    try:
        config = GenericACPConfig.from_args(
            spec,
            api_key=args.api_key,
            base_url=args.base_url,
            project_path=args.project_path,
            agent_instance_id=agent_instance_id,
            model=args.model,
            permission_mode=args.permission_mode,
            initial_prompt=args.prompt,
            system_prompt=args.system_prompt,
            is_resuming=bool(args.resume),
            acp_session_id=args.acp_session_id,
            agent_command=args.agent_command,
            name=args.name,
        )
        wrapper = GenericACPWrapper(config)
        return wrapper.run()
    except Exception as e:
        logger.error(f"Failed to start {spec.display_name} wrapper: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
