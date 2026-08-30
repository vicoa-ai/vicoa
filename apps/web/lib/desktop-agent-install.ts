/**
 * Install instructions for each coding agent Vicoa can drive.
 *
 * Keyed by agent-catalog id — the same 8 ids the daemon's
 * `_detect_available_agents()` reports and `AgentTypeIcon` has marks for.
 * `lib/desktop-agent-install.test.ts` pins that alignment, so a new agent in
 * the catalog fails the suite until it is given install info here.
 *
 * Vicoa never installs an agent. This is copy-and-run text plus a docs link —
 * the same posture multica takes (it auto-installs only its own CLI, never an
 * agent). Auto-installing would mean spawning package managers with no log on
 * disk to diagnose the failures, which is a trade worth making only once
 * desktop logging exists.
 *
 * The backend carries prose `install_hint` strings for the 5 generic ACP
 * agents (`integrations/headless/generic_acp.py`), used in CLI error messages.
 * These are the structured equivalent for a copy button, and cover all 8.
 * Deliberate duplication — noted in plans/todos/desktop-onboarding-flow.md.
 */

export interface AgentInstallInfo {
  /** Shell one-liner, shown in a copy button. */
  command: string;
  /** Where to go when the one-liner isn't enough (auth, prerequisites). */
  docsUrl: string;
}

export const AGENT_INSTALL_INFO: Record<string, AgentInstallInfo> = {
  claude: {
    command: 'npm install -g @anthropic-ai/claude-code',
    docsUrl: 'https://docs.claude.com/en/docs/claude-code/overview',
  },
  codex: {
    command: 'npm install -g @openai/codex',
    docsUrl: 'https://github.com/openai/codex',
  },
  opencode: {
    command: 'curl -fsSL https://opencode.ai/install | bash',
    docsUrl: 'https://opencode.ai/docs/',
  },
  cursor: {
    command: 'curl https://cursor.com/install -fsS | bash',
    docsUrl: 'https://cursor.com/docs/cli/overview',
  },
  gemini: {
    command: 'npm install -g @google/gemini-cli',
    docsUrl: 'https://github.com/google-gemini/gemini-cli',
  },
  copilot: {
    command: 'npm install -g @github/copilot',
    docsUrl: 'https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli',
  },
  kimi: {
    command: 'curl -fsSL https://kimi-cli.moonshot.cn/install.sh | bash',
    docsUrl: 'https://github.com/MoonshotAI/kimi-cli',
  },
  hermes: {
    command: 'curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash',
    docsUrl: 'https://github.com/NousResearch/hermes-agent',
  },
};

/**
 * The agent we point people at when they have none.
 *
 * OpenCode: installs with one command, needs no npm, and works against a
 * provider the user may already pay for.
 */
export const RECOMMENDED_AGENT_ID = 'opencode';

export function installInfoFor(agentId: string): AgentInstallInfo | null {
  return AGENT_INSTALL_INFO[agentId] ?? null;
}
