"""How an agent profile's ``system_prompt`` reaches each agent (collaboration P1).

One enum, one per-agent table, and **this is the only place the decision exists**.
Everything else — the daemon, the wrappers, the capability gate — asks this module
rather than branching on the agent id itself. Modelled on ``block/buzz``'s
``SystemPromptTransport`` (`crates/buzz-acp/src/acp.rs`); the shape generalises
multica's boolean ``providerNeedsInlineSystemPrompt``.

**No transport writes to disk.** That is a product rule, not an implementation
detail: the alternative routes all mean dropping a file into the user's real repo
(git dirt, committed by an agent running ``git add -A``, residue when a session is
killed) or into their home agent config. Rationale and the full list of rejected
routes: ``plans/todos/agent-profiles-p1.md`` §5.

Why each agent lands where it does:

``SDK_APPEND``      Claude's Agent SDK takes ``system_prompt={"type": "preset",
                    "preset": "claude_code", "append": ...}`` — a real system
                    prompt layered onto the stock Claude Code preset.
``COLLAB_SETTINGS`` codex's app-server ``CollaborationMode.Settings`` struct has
                    a ``developer_instructions`` field. It already existed and
                    was simply never populated.
``CLI_FLAG``        pi/omp expose ``--append-system-prompt <text>``.
``PROMPT_PREFIX``   ACP has no system-prompt slot in v1 **or** v2 (``session/new``
                    is cwd / mcpServers / additionalDirectories / _meta, and no
                    v2 RFD proposes one), and ``_meta.systemPrompt`` is a
                    claude-agent-acp-only convention that every other agent
                    silently ignores. So the text rides as a leading content
                    block on each turn instead.

``PROMPT_PREFIX`` is re-injected **every turn**, not just the first. First-turn-only
fails silently: once the agent compacts, a long session quietly reverts to a plain
agent while the UI still shows the profile's name, and the user just experiences it
as "this agent doesn't listen". It is invisible in the transcript either way — the
wrapper's wire payload and the ``messages`` row are two separate writes.

The residual asymmetry is honest and unfixable: ``PROMPT_PREFIX`` text is user-role,
so it argues down more easily than a real system prompt. It is deliberately NOT
surfaced in the UI — the product decision was a uniform capability, and a greyed-out
field for 8% of agents is exactly what that ruled out.
"""

from __future__ import annotations

from enum import Enum


class SystemPromptTransport(str, Enum):
    """The channel a given agent uses to receive custom instructions."""

    #: Claude Agent SDK ``ClaudeAgentOptions.system_prompt``'s ``append`` member.
    SDK_APPEND = "sdk_append"
    #: codex app-server ``CollaborationMode.Settings.developer_instructions``.
    COLLAB_SETTINGS = "collab_settings"
    #: A CLI flag on the agent binary (pi/omp ``--append-system-prompt``).
    CLI_FLAG = "cli_flag"
    #: A leading text block prepended to every ACP ``session/prompt``.
    PROMPT_PREFIX = "prompt_prefix"


#: Per-agent channel. Anything absent falls through to ``PROMPT_PREFIX``, which is
#: the universal fallback — it needs nothing from the agent but the ability to read
#: its own prompt, so a newly added agent gets working instructions by default
#: rather than silently losing them.
TRANSPORT_BY_AGENT: dict[str, SystemPromptTransport] = {
    "claude": SystemPromptTransport.SDK_APPEND,
    "codex": SystemPromptTransport.COLLAB_SETTINGS,
    "pi": SystemPromptTransport.CLI_FLAG,
    "omp": SystemPromptTransport.CLI_FLAG,
}

#: The flag to pass, per ``CLI_FLAG`` agent. Verified against pi 0.67.2+:
#: ``--append-system-prompt <text>  Append text or file contents to the system prompt``.
CLI_FLAG_BY_AGENT: dict[str, str] = {
    "pi": "--append-system-prompt",
    "omp": "--append-system-prompt",
}

#: Capability flag the daemon publishes in its registration metadata so clients
#: can feature-detect this (``machine_daemon._capabilities``). Gating on a
#: declared capability rather than a version number is what the rest of the app
#: already does (``worktree``, ``file-index``, ``terminal``, …): the daemon says
#: what it can actually do, so nothing has to predict a release number and a
#: daemon run from source reports the truth immediately.
#:
#: It matters here more than for most flags because an old daemon drops unknown
#: metadata *silently* — without the check an agent would spawn with none of its
#: instructions while the UI still showed the profile's name.
SYSTEM_PROMPT_CAPABILITY = "system-prompt"


def transport_for(agent: str) -> SystemPromptTransport:
    """Which channel ``agent`` uses. Unknown agents get the universal fallback."""
    return TRANSPORT_BY_AGENT.get(
        (agent or "").strip().lower(), SystemPromptTransport.PROMPT_PREFIX
    )


def cli_flag_for(agent: str) -> str | None:
    """The agent-binary flag for a ``CLI_FLAG`` agent, else ``None``."""
    return CLI_FLAG_BY_AGENT.get((agent or "").strip().lower())


def format_prompt_prefix(system_prompt: str) -> str:
    """The ``PROMPT_PREFIX`` block, separated so the agent reads it as preamble.

    Same separator multica uses for its inline path (``traecli.go`` / ``qoder.go``),
    which keeps the instructions visibly distinct from the user's own words rather
    than running the two together.
    """
    return f"{system_prompt.strip()}\n\n---\n\n"
