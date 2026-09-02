"""Build the register-time session_config payload for Claude TUI.

Folds whatever the wrapper knows at startup (ANTHROPIC_MODEL env,
`--permission-mode` arg, `--dangerously-skip-permissions` flag) into the
canonical session_config dict. Closes the brief window between register
and the JSONLMonitor's first post-init PATCH where the mobile chat
header would otherwise show an empty model/permission row.
"""

from __future__ import annotations

from typing import Optional

from .model_env_parser import parse_anthropic_model_env


# Model-tier default thinking_effort. Claude's TUI doesn't expose the active
# effort at register time (no env, no CLI flag, no jsonl event until /effort
# is run), so we seed a sensible value based on the model. Opus tiers carry
# `xhigh` — the deeper effort they're uniquely capable of (catalog opt-in).
# Sonnet/Haiku default to `high` instead of the catalog's agent-level `low`
# default; coding sessions benefit from more reasoning.
#
# JSONLMonitor's /effort handler overrides this whenever the user changes
# effort mid-session, so this is just the best initial guess.
_MODEL_DEFAULT_THINKING: dict[str, str] = {
    "claude-opus-5": "xhigh",
    "claude-opus-4-7": "xhigh",
    "claude-opus-4-8": "xhigh",
    "claude-sonnet-4-6": "high",
    "claude-haiku-4-5": "high",
}


def _default_thinking_effort_for(model_id: Optional[str]) -> Optional[str]:
    """Return the model-tier default thinking effort, or None when unknown.

    `[1m]` context-window variants share the base model's default.
    """
    if not model_id:
        return None
    # Strip `[1m]` (or any other bracketed context variant) before lookup.
    base = model_id.split("[", 1)[0]
    return _MODEL_DEFAULT_THINKING.get(base)


def build_initial_session_config(
    *,
    anthropic_model_env: Optional[str],
    permission_mode: Optional[str],
    dangerously_skip_permissions: bool,
) -> Optional[dict]:
    """Return the session_config dict to send on first register, or None.

    Returns None when nothing is known — the wrapper then omits the
    field from the POST and the server's field-present semantics
    preserve any pre-staged value on the row.

    `--permission-mode` wins over `--dangerously-skip-permissions` when
    both are set, matching the Claude CLI's own precedence (the skip
    flag is shorthand for `--permission-mode bypassPermissions`).
    """
    sc: dict = {"agent": "claude"}
    model = parse_anthropic_model_env(anthropic_model_env)
    if model:
        sc["model"] = model
        default_thinking = _default_thinking_effort_for(model)
        if default_thinking:
            sc["thinking_effort"] = default_thinking
    if permission_mode:
        sc["permission_mode"] = permission_mode
    elif dangerously_skip_permissions:
        sc["permission_mode"] = "bypassPermissions"

    # Only return the dict when it carries at least one known value.
    if len(sc) == 1:  # just the "agent" key
        return None
    return sc
