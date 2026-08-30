"""Static agent catalog served by `GET /api/v1/agent-catalog`.

Hand-curated per `plans/new-session-model-selection.md` §3.1, §4.1, §5.1.
Module-level constants are computed once at import; the daemon imports the
derived `PERMISSION_MODES` / `THINKING_EFFORTS` / `REASONING_EFFORTS` sets for
structural validation so no snapshot has to ship with each daemon release.

Canonical copy. Lives under the top-level `protocol/` package — the wire-format
contract shared between backend (serves it) and CLI/web/mobile (consume it) —
rather than `shared/`, which is reserved for backend↔servers DB and infra.
The backend still imports `from shared.agent_catalog import ...` for
back-compat; `shared/agent_catalog.py` is a re-export shim around this module.

Fallback mirrors in `vicoa-web/lib/agent-catalog.ts` and
`vicoa-app/lib/backend/agent_catalog.dart` must move with it. Refresh process
and upstream slug discovery: `docs/agents/agent-catalog.md`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


AGENT_CATALOG: dict[str, Any] = {
    "version": "2026-07-18-1",
    "min_cli_version": "1.20.0",
    "min_client_version": "0.42.0",
    "agents": [
        {
            "id": "claude",
            "label": "Claude Code",
            "models": [
                # Per-model `thinking_efforts` / `permission_modes` arrays list
                # ONLY the opt-in ids this model adds beyond the common set.
                # Omit the field entirely when the model has no opt-ins.
                # `auto` permission requires SDK capabilities present in
                # Sonnet 4.6+ and Opus 4.7+; older models omit it.
                # Opus 4.7+ default to xhigh thinking — they're the only models
                # with the depth-of-reasoning to justify the agent-level `high`
                # baseline being bumped. `default_thinking_effort` overrides
                # `is_default` when this model is selected.
                # Fable 5 is natively 1M-context (max == default), so it has
                # no `[1m]` variant. Premium-priced and thinking-always-on, so
                # it is not the picker default. `xhigh` is the recommended
                # coding/agentic effort tier.
                {
                    "id": "claude-fable-5",
                    "label": "Fable 5",
                    "default_thinking_effort": "xhigh",
                    "permission_modes": ["auto"],
                },
                {
                    "id": "claude-opus-4-8",
                    "label": "Opus 4.8",
                    "default_thinking_effort": "xhigh",
                    "permission_modes": ["auto"],
                },
                {
                    "id": "claude-opus-4-8[1m]",
                    "label": "Opus 4.8 1M",
                    "default_thinking_effort": "xhigh",
                    "permission_modes": ["auto"],
                },
                {
                    "id": "claude-opus-4-7",
                    "label": "Opus 4.7",
                    "default_thinking_effort": "xhigh",
                    "permission_modes": ["auto"],
                },
                {
                    "id": "claude-opus-4-7[1m]",
                    "label": "Opus 4.7 1M",
                    "default_thinking_effort": "xhigh",
                    "permission_modes": ["auto"],
                },
                {"id": "claude-opus-4-6", "label": "Opus 4.6"},
                {"id": "claude-opus-4-6[1m]", "label": "Opus 4.6 1M"},
                {
                    "id": "claude-sonnet-5",
                    "label": "Sonnet 5",
                    "is_default": True,
                    "permission_modes": ["auto"],
                },
                {
                    "id": "claude-sonnet-5[1m]",
                    "label": "Sonnet 5 1M",
                    "permission_modes": ["auto"],
                },
                {
                    "id": "claude-sonnet-4-6",
                    "label": "Sonnet 4.6",
                    "permission_modes": ["auto"],
                },
                {
                    "id": "claude-sonnet-4-6[1m]",
                    "label": "Sonnet 4.6 1M",
                    "permission_modes": ["auto"],
                },
                {"id": "claude-haiku-4-5", "label": "Haiku 4.5"},
            ],
            # Agent-level lists carry labels + display order for ALL known
            # values. Entries tagged `opt_in: True` are model-specific
            # capabilities — they only render when the active model's
            # per-model array explicitly opts them in. Entries without the
            # flag are "common" and shown for every model unless excluded.
            "thinking_efforts": [
                {"id": "max", "label": "Max"},
                {"id": "xhigh", "label": "Extra High"},
                {"id": "high", "label": "High", "is_default": True},
                {"id": "medium", "label": "Medium"},
                {"id": "low", "label": "Low"},
                {"id": "off", "label": "Off"},
            ],
            "permission_modes": [
                {"id": "default", "label": "Default", "is_default": True},
                {"id": "auto", "label": "Auto mode", "opt_in": True},
                {"id": "acceptEdits", "label": "Accept Edits"},
                {"id": "plan", "label": "Plan"},
                {"id": "bypassPermissions", "label": "Skip permissions (Yolo)"},
            ],
        },
        {
            "id": "codex",
            "label": "Codex",
            # Refresh per docs/agents/agent-catalog.md. Do NOT source from
            # ~/.codex/models_cache.json — that file is per-user / per-account
            # (filtered by entitlements) and doesn't reflect the canonical
            # list of slugs users could pick. Use the codex CLI's own
            # documentation or release notes instead.
            #
            # gpt-5.6 ships as three variants in codex-cli 0.144.5 (Sol =
            # latest frontier, Terra = balanced everyday, Luna = fast/cheap);
            # all three share the low/medium/high/xhigh effort axis below.
            # gpt-5.5 stays the default; 5.6 is opt-in until it's proven.
            "models": [
                {"id": "gpt-5.5", "label": "GPT-5.5", "is_default": True},
                {"id": "gpt-5.6-sol", "label": "GPT-5.6-Sol"},
                {"id": "gpt-5.6-terra", "label": "GPT-5.6-Terra"},
                {"id": "gpt-5.6-luna", "label": "GPT-5.6-Luna"},
                {"id": "gpt-5.4", "label": "GPT-5.4"},
                {"id": "gpt-5.4-mini", "label": "GPT-5.4-Mini"},
            ],
            # Subset of codex-rs ReasoningEffort (openai_models.rs:45) — full
            # enum is none/minimal/low/medium/high/xhigh. We expose the four
            # useful for coding; `none` and `minimal` are skipped (analogous
            # to skipping Claude's `off` from the default picker).
            "reasoning_efforts": [
                {"id": "low", "label": "Low"},
                {"id": "medium", "label": "Medium", "is_default": True},
                {"id": "high", "label": "High"},
                {"id": "xhigh", "label": "Extra High"},
            ],
            # Vicoa's permission_mode is a BUNDLED abstraction — each slug
            # collapses 2-3 codex settings (approval_policy + sandbox_mode +
            # collaboration_mode). See integrations/headless/codex/permission_translate.py
            # for the canonical spawn-time mapping; the Rust bridge mirrors
            # the same bundle when dispatching mid-session changes.
            "permission_modes": [
                {"id": "default", "label": "Default", "is_default": True},
                {"id": "bypassPermissions", "label": "Full Access"},
            ],
        },
        {
            "id": "opencode",
            "label": "OpenCode",
            # OpenCode is a multi-provider proxy whose available models depend
            # on each user's local opencode config. `default` keeps the user's
            # own configured model (no --model at spawn); the rest is a starter
            # set. The real per-config list is reported live to the mid-session
            # gear (the wrapper PATCHes available_models from session/new).
            "models": [
                {"id": "default", "label": "Default", "is_default": True},
                {
                    "id": "opencode/big-pickle",
                    "label": "OpenCode Zen - big-pickle",
                },
            ],
            "modes": [
                {"id": "build", "label": "Build", "is_default": True},
                {"id": "plan", "label": "Plan"},
            ],
        },
        # ---------------------------------------------------------------
        # Generic ACP agents (integrations/headless/generic_acp.py).
        #
        # IMPORTANT: for ACP agents the AUTHORITATIVE source of available
        # modes and models is each session's `session/new` response
        # (`modes.availableModes` / `models.availableModels` / `configOptions`),
        # which the wrapper captures live (acp_base: `available_modes`,
        # `session_config_options`). The values below are only spawn-time
        # hints / fallback labels — they're account-gated and version-specific
        # upstream, so don't treat them as exhaustive. permission_modes are
        # validated against the live availableModes at spawn (unknown ids are
        # skipped). Verified June 2026 against each CLI's ACP server:
        #   • cursor  → agent / plan / ask (real ACP mode ids)
        #   • gemini  → default / autoEdit (camelCase!) / yolo / plan(when enabled)
        #   • kimi    → only `default` over ACP (plan/yolo are shell/slash-only)
        #   • copilot → ACP mode ids undocumented (closed source); omit until
        #               sourced from the live session
        #
        # `models` here is a STATIC default set shown in the new-session model
        # picker. It's account/version-specific upstream, so it can't be
        # exhaustive (a given install may advertise others — those appear in
        # the mid-session gear, which is sourced live from session/new).
        # `auto`/`default` is offered so the user can always defer to the
        # agent's own default. Proper fix for showing an install's REAL models
        # at new-session is per-machine discovery (TODO).
        # ---------------------------------------------------------------
        {
            "id": "cursor",
            "label": "Cursor",
            "models": [
                {"id": "auto", "label": "Default", "is_default": True},
                {"id": "composer-2.5", "label": "Composer 2.5"},
            ],
            "permission_modes": [
                {"id": "agent", "label": "Agent", "is_default": True},
                {"id": "plan", "label": "Plan"},
                {"id": "ask", "label": "Ask"},
            ],
        },
        {
            "id": "gemini",
            "label": "Gemini",
            "models": [
                {"id": "auto", "label": "Default", "is_default": True},
                {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite"},
                {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
                {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            ],
            "permission_modes": [
                {"id": "default", "label": "Default", "is_default": True},
                # Wire id is camelCase `autoEdit` (ApprovalMode enum), not
                # the `auto_edit` CLI-flag spelling.
                {"id": "autoEdit", "label": "Auto Edit"},
                {"id": "plan", "label": "Plan"},
                {"id": "yolo", "label": "Skip permissions (Yolo)"},
            ],
        },
        {
            "id": "copilot",
            "label": "Copilot",
            # Copilot's default install offers these; richer model access is
            # subscription-gated. Like the others this is a starter set — an
            # install's real options show in the live gear, and the catalog id
            # is resolved against the agent's live values at spawn.
            "models": [
                {"id": "default", "label": "Default", "is_default": True},
                {"id": "gpt-5-mini", "label": "GPT-5 mini"},
                {"id": "claude-haiku-4.5", "label": "Claude Haiku 4.5"},
            ],
            # ACP mode ids are undocumented (Copilot CLI is closed source) and
            # likely a permission config-option rather than a mode list —
            # source modes from the live session instead.
        },
        {
            "id": "kimi",
            "label": "Kimi",
            # `auto` (default) skips --model so Kimi uses its config
            # default_model; the rest are the common namespaced aliases. Like
            # the others this is a default set — an install's real aliases
            # (account/provider-specific) show in the live gear.
            "models": [
                {"id": "auto", "label": "Default", "is_default": True},
                {"id": "moonshot-ai/kimi-k2.5", "label": "Kimi K2.5"},
                {"id": "moonshot-ai/kimi-k2.6", "label": "Kimi K2.6"},
                {"id": "moonshot-ai/kimi-k2.7-code", "label": "Kimi K2.7 Code"},
            ],
            # Kimi advertises only a single `default` ACP session mode
            # (plan/yolo are shell/slash-mode only) — no mode picker.
        },
        {
            "id": "hermes",
            "label": "Hermes",
            "models": [
                {"id": "default", "label": "Provider default", "is_default": True},
            ],
        },
    ],
}


def _build_enum_indices(
    catalog: dict[str, Any],
) -> tuple[
    dict[str, set[str]],
    set[str],
    set[str],
]:
    """Derive validation sets from the catalog so daemon and endpoint share truth."""
    permission_modes: dict[str, set[str]] = {}
    thinking_efforts: set[str] = set()
    reasoning_efforts: set[str] = set()
    for agent in catalog["agents"]:
        agent_id = agent["id"]
        pm = {entry["id"] for entry in agent.get("permission_modes") or []}
        if pm:
            permission_modes[agent_id] = pm
        for entry in agent.get("thinking_efforts") or []:
            thinking_efforts.add(entry["id"])
        for model in agent.get("models") or []:
            for effort in model.get("thinking_efforts") or []:
                thinking_efforts.add(effort)
        for entry in agent.get("reasoning_efforts") or []:
            reasoning_efforts.add(entry["id"])
    return permission_modes, thinking_efforts, reasoning_efforts


PERMISSION_MODES, THINKING_EFFORTS, REASONING_EFFORTS = _build_enum_indices(
    AGENT_CATALOG
)

# JSON-encoded once at import: stable bytes for ETag computation and direct
# Response body without per-request `json.dumps`.
AGENT_CATALOG_JSON: str = json.dumps(AGENT_CATALOG, sort_keys=True)
AGENT_CATALOG_ETAG: str = hashlib.sha256(AGENT_CATALOG_JSON.encode("utf-8")).hexdigest()
