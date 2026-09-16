"""Curated catalog of ACP agents a user can add with one click.

Served inside ``GET /api/v1/agent-catalog`` as ``acp_catalog`` and read by the
``vicoa provider add`` CLI, so the list can grow without a client release —
the point of :mod:`protocol.provider_overrides`. Each entry is exactly what
``provider-add`` writes to ``agents.providers`` in ``~/.vicoa/config.json``
(``extends: "acp"`` + ``label`` + ``command`` + ``env``), plus ``install_url``
and ``version`` for the UI.

Ported from paseo's ``acp-provider-catalog.ts`` (2026-08-21 snapshot), minus
the agents Vicoa already ships as built-ins (cursor, gemini, kimi, hermes —
those live in ``integrations.headless.generic_acp.GENERIC_ACP_AGENTS`` with
model-flag handling the generic path does not have).

Two kinds of ``command``:

* ``npx -y <pkg>@<version> …`` / ``uvx --from <pkg>==<version> …`` — the
  launcher is always present when Node / uv is, and the package downloads on
  the first session. Adding one of these is genuinely one click. Versions
  are pinned so a session on Tuesday runs the same agent as one on Monday;
  bump them here, not in the client.
* A bare binary (``goose acp``) — the user installs the CLI from
  ``install_url`` first; until then the entry shows as added-but-missing.

Vicoa never installs an agent itself (same posture as onboarding's
AgentScanStep): spawning package managers with no log on disk is a trade
worth making only once desktop logging exists.

No icons: an unknown id renders as a generated initial square (the track-A
decision), which keeps 33 SVGs and their licences out of the tree.
"""

from __future__ import annotations

from typing import Any


ACP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "agoragentic-acp",
        "label": "Agoragentic",
        "description": "Agent marketplace with 174+ AI capabilities. Browse, invoke, and pay for agent services settled in USDC on Base L2.",
        "command": ["npx", "-y", "agoragentic-mcp@1.3.6", "--acp"],
        "install_url": "https://agoragentic.com",
        "version": "1.3.6",
    },
    {
        "id": "amp-acp",
        "label": "Amp",
        "description": "ACP wrapper for Amp - the frontier coding agent",
        "command": ["amp-acp"],
        "install_url": "https://github.com/tao12345666333/amp-acp",
        "version": "0.7.0",
    },
    {
        "id": "auggie",
        "label": "Auggie CLI",
        "description": "Augment Code's powerful software agent, backed by industry-leading context engine",
        "command": ["npx", "-y", "@augmentcode/auggie@0.33.0", "--acp"],
        "env": {"AUGMENT_DISABLE_AUTO_UPDATE": "1"},
        "install_url": "https://www.augmentcode.com/",
        "version": "0.33.0",
    },
    {
        "id": "autohand",
        "label": "Autohand Code",
        "description": "Autohand Code - AI coding agent powered by Autohand AI",
        "command": ["npx", "-y", "@autohandai/autohand-acp@0.2.1"],
        "install_url": "https://www.autohand.ai/cli/",
        "version": "0.2.1",
    },
    {
        "id": "cline",
        "label": "Cline",
        "description": "Autonomous coding agent CLI - capable of creating/editing files, running commands, using the browser, and more",
        "command": ["npx", "-y", "cline@3.0.46", "--acp"],
        "install_url": "https://cline.bot/cli",
        "version": "3.0.46",
    },
    {
        "id": "codebuddy-code",
        "label": "Codebuddy Code",
        "description": "Tencent Cloud's official intelligent coding tool",
        "command": ["codebuddy", "--acp"],
        "install_url": "https://www.codebuddy.cn/cli/",
    },
    {
        "id": "codewhale",
        "label": "CodeWhale",
        "description": "Terminal coding agent for DeepSeek V4 and open models",
        "command": ["codewhale", "serve", "--acp"],
        "install_url": "https://codewhale.net/",
        "version": "0.8.55",
    },
    {
        "id": "cortex-code",
        "label": "Cortex Code",
        "description": "Snowflake's Cortex Code coding agent",
        "command": ["cortex", "acp", "serve"],
        "install_url": "https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli",
        "version": "1.0.73",
    },
    {
        "id": "corust-agent",
        "label": "Corust Agent",
        "description": "Co-building with a seasoned Rust partner.",
        "command": ["corust-agent-acp"],
        "install_url": "https://github.com/Corust-ai/corust-agent-release/releases",
        "version": "0.5.1",
    },
    {
        "id": "crow-cli",
        "label": "crow-cli",
        "description": "Minimal ACP Native Coding Agent",
        "command": ["crow-cli", "acp"],
        "install_url": "https://crow-ai.dev/",
        "version": "0.1.23",
    },
    {
        "id": "deepagents",
        "label": "DeepAgents",
        "description": "Batteries-included AI coding and general purpose agent powered by LangChain.",
        "command": ["npx", "-y", "deepagents-acp@0.1.20"],
        "install_url": "https://docs.langchain.com/oss/javascript/deepagents/overview",
        "version": "0.1.20",
    },
    {
        "id": "devin",
        "label": "Devin CLI",
        "description": "Cognition's Devin for Terminal via Agent Client Protocol",
        "command": ["devin", "acp"],
        "install_url": "https://cli.devin.ai/docs",
    },
    {
        "id": "dimcode",
        "label": "DimCode",
        "description": "A coding agent that puts leading models at your command.",
        "command": ["npx", "-y", "dimcode@0.2.36", "acp"],
        "install_url": "https://dimcode.dev/docs/acp.html",
        "version": "0.2.36",
    },
    {
        "id": "dirac",
        "label": "Dirac",
        "description": "Reduces API costs by more than 50%, produces better and faster work. Uses Hash anchored parallel edits, AST manipulation and a whole lot of neat optimizations. Fully Open Source.",
        "command": ["npx", "-y", "dirac-cli@0.4.22", "--acp"],
        "install_url": "https://dirac.run",
        "version": "0.4.22",
    },
    {
        "id": "factory-droid",
        "label": "Factory Droid",
        "description": "Factory Droid - AI coding agent powered by Factory AI",
        "command": [
            "npx",
            "-y",
            "droid@0.179.0",
            "exec",
            "--output-format",
            "acp-daemon",
        ],
        "env": {
            "DROID_DISABLE_AUTO_UPDATE": "true",
            "FACTORY_DROID_AUTO_UPDATE_ENABLED": "false",
        },
        "install_url": "https://factory.ai/product/cli",
        "version": "0.179.0",
    },
    {
        "id": "fast-agent",
        "label": "fast-agent",
        "description": "Code and build agents with comprehensive multi-provider support",
        "command": ["uvx", "--from", "fast-agent-acp==0.9.22", "fast-agent-acp", "-x"],
        "install_url": "https://fast-agent.ai/acp/",
        "version": "0.9.22",
    },
    {
        "id": "glm-acp-agent",
        "label": "GLM Agent",
        "description": "ACP agent powered by Zhipu AI's GLM Coding Plan models (glm-5.1, glm-5-turbo, glm-4.7, glm-4.5-air). Supports streaming, tool calls, mid-session model switching, image input via Z.AI Coding Plan Vision MCP, and session load/fork/resume with on-disk persistence.",
        "command": ["npx", "-y", "glm-acp-agent@1.3.0"],
        "install_url": "https://github.com/stefandevo/glm-acp-agent",
        "version": "1.3.0",
    },
    {
        "id": "goose",
        "label": "goose",
        "description": "A local, extensible, open source AI agent that automates engineering tasks",
        "command": ["goose", "acp"],
        "install_url": "https://block.github.io/goose/",
        "version": "1.33.1",
    },
    {
        "id": "grok",
        "label": "Grok",
        "description": "xAI's Grok Build agentic coding CLI with plan mode and parallel subagents. Requires a SuperGrok or X Premium+ subscription.",
        "command": ["grok", "agent", "stdio"],
        "install_url": "https://docs.x.ai/build/overview",
        "version": "0.2.11",
    },
    {
        "id": "junie",
        "label": "Junie",
        "description": "AI Coding Agent by JetBrains",
        "command": ["junie", "--acp", "true"],
        "install_url": "https://junie.jetbrains.com/docs/junie-cli-acp.html",
        "version": "1468.30.0",
    },
    {
        "id": "kilo",
        "label": "Kilo",
        "description": "The open source coding agent",
        "command": ["kilo", "acp"],
        "install_url": "https://kilo.ai/docs/code-with-ai/platforms/cli",
        "version": "7.2.40",
    },
    {
        "id": "kiro",
        "label": "Kiro CLI",
        "description": "Amazon's AI coding agent with native ACP support",
        "command": ["kiro-cli", "acp"],
        "install_url": "https://kiro.dev/docs/cli/acp/",
    },
    {
        "id": "minimax-code",
        "label": "MiniMax Code",
        "description": "MiniMax's coding agent for the terminal",
        "command": ["npx", "-y", "@minimax-ai/code@0.1.2", "acp"],
        "install_url": "https://agent.minimax.io",
        "version": "0.1.2",
    },
    {
        "id": "minion-code",
        "label": "Minion Code",
        "description": "An enhanced AI code assistant built on the Minion framework with rich development tools",
        "command": ["uvx", "--from", "minion-code==0.1.44", "minion-code", "acp"],
        "install_url": "https://github.com/femto/minion-code",
        "version": "0.1.44",
    },
    {
        "id": "mistral-vibe",
        "label": "Mistral Vibe",
        "description": "Mistral's open-source coding assistant",
        "command": ["vibe-acp"],
        "install_url": "https://github.com/mistralai/mistral-vibe",
        "version": "2.9.3",
    },
    {
        "id": "nova",
        "label": "Nova",
        "description": "Nova by Compass AI - a fully-fledged software engineer at your command",
        "command": ["npx", "-y", "@compass-ai/nova@1.1.29", "acp"],
        "install_url": "https://www.compassap.ai/portfolio/nova.html",
        "version": "1.1.29",
    },
    {
        "id": "poolside",
        "label": "Poolside",
        "description": "Poolside's coding agent",
        "command": ["pool", "acp"],
        "install_url": "https://docs.poolside.ai/cli/pool",
        "version": "1.0.0",
    },
    {
        "id": "qoder",
        "label": "Qoder CLI",
        "description": "AI coding assistant with agentic capabilities",
        "command": ["npx", "-y", "@qoder-ai/qodercli@1.1.4", "--acp"],
        "install_url": "https://qoder.com",
        "version": "1.1.4",
    },
    {
        "id": "qwen-code",
        "label": "Qwen Code",
        "description": "Alibaba's Qwen coding assistant",
        "command": [
            "npx",
            "-y",
            "@qwen-code/qwen-code@0.20.1",
            "--acp",
            "--experimental-skills",
        ],
        "install_url": "https://qwenlm.github.io/qwen-code-docs/en/users/overview",
        "version": "0.20.1",
    },
    {
        "id": "sigit",
        "label": "siGit Code",
        "description": "Local-first coding agent. Runs entirely on your machine with optional on-device LLM inference via Onde.",
        "command": ["sigit"],
        "install_url": "https://github.com/getsigit/sigit",
        "version": "1.0.3",
    },
    {
        "id": "stakpak",
        "label": "Stakpak",
        "description": "Open-source DevOps agent in Rust with enterprise-grade security",
        "command": ["stakpak", "acp"],
        "install_url": "https://stakpak.dev/",
        "version": "0.3.80",
    },
    {
        "id": "traecli",
        "label": "TRAE CLI",
        "description": "ByteDance's official TRAE coding agent with native ACP support",
        "command": ["traecli", "acp", "serve"],
        "install_url": "https://docs.trae.cn/cli_get-started-with-trae-cli",
    },
    {
        "id": "vtcode",
        "label": "VT Code",
        "description": "An open-source coding agent with LLM-native code understanding and robust shell safety. Supports multiple LLM providers with automatic failover and efficient context management.",
        "command": ["vtcode", "acp"],
        "env": {"VT_ACP_ENABLED": "1", "VT_ACP_ZED_ENABLED": "1"},
        "install_url": "https://github.com/vinhnx/VTCode/blob/main/docs/guides/zed-acp.md",
        "version": "0.96.14",
    },
]


def install_hint_for(entry: dict[str, Any]) -> str:
    """The one-line "why is it not running" text stored with the provider.

    Shown by the daemon when the launch binary is missing, so it has to name
    the *launcher* for npx/uvx entries — a missing ``npx`` means "install
    Node", not "install cline".
    """
    launcher = str((entry.get("command") or [""])[0])
    url = str(entry.get("install_url") or "")
    if launcher == "npx":
        return f"Runs through npx, so Node.js must be on PATH. Docs: {url}"
    if launcher == "uvx":
        return f"Runs through uvx, so uv must be on PATH. Docs: {url}"
    return f"Install the {entry.get('label') or entry.get('id')} CLI: {url}"


def catalog_entry(provider_id: str) -> dict[str, Any] | None:
    """Look one entry up by id."""
    for entry in ACP_CATALOG:
        if entry["id"] == provider_id:
            return entry
    return None


def provider_config_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """The ``agents.providers[id]`` value a catalog entry installs as.

    Exactly the hand-written shape from ``docs/agents/custom-agents``, so a
    user can read, edit or delete it in the file afterwards and nothing
    downstream knows the difference. ``install_url`` and ``version`` are UI
    metadata and stay out of the config.
    """
    config: dict[str, Any] = {
        "extends": "acp",
        "label": entry["label"],
        "command": list(entry["command"]),
        "install_hint": install_hint_for(entry),
    }
    if entry.get("description"):
        config["description"] = entry["description"]
    if entry.get("env"):
        config["env"] = dict(entry["env"])
    return config


__all__ = [
    "ACP_CATALOG",
    "catalog_entry",
    "install_hint_for",
    "provider_config_from_entry",
]
