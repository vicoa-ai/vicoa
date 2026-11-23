/**
 * Install instructions for each coding agent Vicoa can drive.
 *
 * Keyed by agent-catalog id — the same ids the daemon's
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
 * Each command is the agent's own documented installer, per OS: a `curl | bash`
 * line does nothing in PowerShell, which is where a Windows user pastes it.
 *
 * The backend carries prose `install_hint` strings for the generic ACP agents
 * (`integrations/headless/generic_acp.py`) and the Pi family
 * (`integrations/headless/pi_family/spec.py`), used in CLI error messages.
 * These are the structured equivalent for a copy button, and cover every agent.
 * Deliberate duplication — noted in plans/todos/desktop-onboarding-flow.md.
 */

import { machinePlatformLabel } from '@/lib/machine-display';

export interface AgentInstallInfo {
  /** The agent's own one-liner for macOS and Linux, shown in a copy button. */
  command: string;
  /**
   * The one-liner for native Windows. Absent when `command` runs there as it
   * is (npm works the same in PowerShell); null when the agent documents no
   * Windows one-liner, so its setup guide is the way.
   */
  windowsCommand?: string | null;
  /** Where to go when the one-liner isn't enough (auth, prerequisites). */
  docsUrl: string;
  /** What to do once it is installed, as one sentence; `code` spans in backticks. */
  signIn?: string;
}

export const AGENT_INSTALL_INFO: Record<string, AgentInstallInfo> = {
  claude: {
    command: 'curl -fsSL https://claude.ai/install.sh | bash',
    windowsCommand: 'irm https://claude.ai/install.ps1 | iex',
    docsUrl: 'https://code.claude.com/docs/en/setup',
    signIn: 'After it installs, run `claude` once in a terminal to sign in.',
  },
  codex: {
    command: 'curl -fsSL https://chatgpt.com/codex/install.sh | sh',
    windowsCommand: 'powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"',
    docsUrl: 'https://github.com/openai/codex',
    signIn: 'After it installs, run `codex` once in a terminal and choose Sign in with ChatGPT.',
  },
  // OpenCode 1, the one Vicoa drives (`opencode acp`). Its install script is
  // macOS and Linux only; on Windows the same release ships as `opencode-ai`
  // on npm. Not `@opencode/cli`, which is OpenCode 2.
  opencode: {
    command: 'curl -fsSL https://opencode.ai/install | bash',
    windowsCommand: 'npm install -g opencode-ai',
    docsUrl: 'https://opencode.ai/docs/',
  },
  cursor: {
    command: 'curl https://cursor.com/install -fsS | bash',
    windowsCommand: null,
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
    windowsCommand: null,
    docsUrl: 'https://github.com/MoonshotAI/kimi-cli',
  },
  hermes: {
    command: 'curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash',
    windowsCommand: null,
    docsUrl: 'https://github.com/NousResearch/hermes-agent',
  },
  // Deliberately NOT the npm package. `@oh-my-pi/pi-coding-agent` declares
  // `engines: {"bun": ">=1.3.14"}` and ships a `#!/usr/bin/env bun` shebang
  // without bundling Bun, so the npm path leaves every user to solve the Bun
  // gate themselves — and the daemon's install check then refuses the spawn.
  omp: {
    command: 'brew install can1357/tap/omp',
    windowsCommand: null,
    docsUrl: 'https://github.com/can1357/oh-my-pi',
  },
  // Pi is plain node, so npm is fine here.
  pi: {
    command: 'npm install -g @earendil-works/pi-coding-agent',
    docsUrl: 'https://github.com/earendil-works/pi',
  },
  // Google's installer script; the binary lands in ~/.local/bin and signs in
  // with a Google account on first run (`agy`). Vicoa needs >= 1.1.15.
  antigravity: {
    command: 'curl -fsSL https://antigravity.google/cli/install.sh | bash',
    windowsCommand: null,
    docsUrl: 'https://antigravity.google/docs/cli/install',
  },
};

export function installInfoFor(agentId: string): AgentInstallInfo | null {
  return AGENT_INSTALL_INFO[agentId] ?? null;
}

/** Which family of one-liners a machine takes. */
export type InstallOs = 'windows' | 'unix';

/** A machine's install OS from its daemon-reported `platform` string. */
export function installOsForPlatform(platform: string | null | undefined): InstallOs {
  return machinePlatformLabel(platform)?.toLowerCase() === 'windows' ? 'windows' : 'unix';
}

/** The OS of the computer this page runs on, for copy not tied to one machine. */
export function installOsForThisComputer(): InstallOs {
  if (typeof navigator === 'undefined') return 'unix';
  return /windows/i.test(navigator.userAgent) ? 'windows' : 'unix';
}

/** Everything needed to show how to install one agent on one OS. */
export interface InstallStep {
  /** The one-liner, or null when this OS has none and the setup guide is the way. */
  command: string | null;
  /** Where to run it, in the user's words. */
  shell: 'PowerShell' | 'a terminal';
  /** Something the command needs first, worth saying out loud. */
  requires: 'Node.js' | null;
  signIn: string | null;
  docsUrl: string;
}

export function installStepFor(agentId: string, os: InstallOs): InstallStep | null {
  const info = installInfoFor(agentId);
  if (!info) return null;
  const command =
    os === 'windows' ? (info.windowsCommand === undefined ? info.command : info.windowsCommand) : info.command;
  return {
    command,
    shell: os === 'windows' ? 'PowerShell' : 'a terminal',
    requires: command?.startsWith('npm ') ? 'Node.js' : null,
    signIn: info.signIn ?? null,
    docsUrl: info.docsUrl,
  };
}

/**
 * The agents to lead with when a machine has none, in this order: the two that
 * run on a subscription the user may already pay for, then the one that needs
 * none. One is enough; the rest of the catalog sits behind "Show more".
 */
export const PLAN_CHOICES: readonly { id: string; plan: string; free?: true; note?: string }[] = [
  { id: 'claude', plan: 'Uses your Claude Pro, Max or Team plan' },
  { id: 'codex', plan: 'Uses your ChatGPT Plus or Pro plan' },
  {
    id: 'opencode',
    plan: 'No plan? Start with its free models',
    free: true,
    note: 'The free models are offered for a limited time.',
  },
];
