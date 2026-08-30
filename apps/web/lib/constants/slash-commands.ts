/**
 * Default slash commands for different AI agents
 * These are built-in commands that are always available
 */

export interface SlashCommand {
  command: string;
  description: string;
  source?: 'default' | 'custom';
  /**
   * Whether this entry is a plain slash command or an installed skill. Built-in
   * defaults omit it (treated as 'command'); custom entries carry it so a
   * future Skills tab can list skills separately.
   */
  kind?: 'command' | 'skill';
  /**
   * Text to insert into the composer on selection when it differs from
   * `command` — Codex invokes skills with `$name` rather than `/name`.
   */
  insert?: string;
}

export type AgentType = 'claude' | 'codex' | 'opencode';

/**
 * Claude Code built-in slash commands
 * Source: Claude Code v2.1.163
 */
export const CLAUDE_CODE_COMMANDS: SlashCommand[] = [
  // --- Session / context ---
  { command: '/clear', description: 'Start a new conversation. Pass a name to label the previous conversation in /resume. Aliases: /reset, /new', source: 'default' },
  { command: '/compact', description: 'Free up context by summarizing the conversation. Optionally pass focus instructions', source: 'default' },
  { command: '/context', description: 'Visualize current context usage as a colored grid', source: 'default' },
  { command: '/recap', description: 'Generate a one-line summary of the current session on demand', source: 'default' },
  { command: '/copy', description: 'Copy the last assistant response to clipboard. Pass N to copy the Nth-latest response', source: 'default' },
  { command: '/export', description: 'Export the current conversation as plain text', source: 'default' },

  // --- Task / workflow ---
  { command: '/btw', description: 'Ask a quick side question without adding to the conversation', source: 'default' },
  { command: '/plan', description: 'Enter plan mode. Pass a description to start immediately', source: 'default' },
  { command: '/goal', description: 'Set a goal: Claude keeps working until the condition is met. No arg shows current goal; clear/stop removes it', source: 'default' },
  { command: '/fork', description: 'Spawn a forked subagent that inherits the full conversation and works in the background', source: 'default' },
  { command: '/background', description: 'Detach the current session to run as a background agent. Monitor with claude agents. Alias: /bg', source: 'default' },
  { command: '/stop', description: 'Stop the current background session (transcript and worktree are kept)', source: 'default' },
  { command: '/tasks', description: 'List and manage background tasks. Alias: /bashes', source: 'default' },
  { command: '/loop', description: 'Run a prompt repeatedly while the session stays open. Omit interval for model self-pacing. Alias: /proactive', source: 'default' },
  { command: '/schedule', description: 'Create, update, list, or run routines on Anthropic-managed cloud infrastructure. Alias: /routines', source: 'default' },
  { command: '/batch', description: 'Skill. Orchestrate large-scale changes across a codebase in parallel across up to 30 independent units', source: 'default' },
  { command: '/autofix-pr', description: 'Spawn a Claude Code on the web session that watches the current branch\'s PR and pushes fixes when CI fails or reviewers comment. Requires gh CLI', source: 'default' },
  { command: '/ultraplan', description: 'Draft a plan in an ultraplan session, review it in your browser, then execute remotely or send back to your terminal', source: 'default' },

  // --- Code review / analysis ---
  { command: '/review', description: 'Review a pull request locally. For deeper cloud-based review, use /code-review ultra', source: 'default' },
  { command: '/code-review', description: 'Skill. Review the current diff for bugs and cleanups. Pass --fix to apply, --comment to post as PR comments, or ultra for deep cloud review', source: 'default' },
  { command: '/simplify', description: 'Skill. Review changed code for cleanup opportunities and apply fixes (reuse, simplification, efficiency). Does not look for bugs — use /code-review for that', source: 'default' },
  { command: '/security-review', description: 'Analyze pending changes on the current branch for security vulnerabilities (injection, auth issues, data exposure)', source: 'default' },
  { command: '/ultrareview', description: 'Run a deep, multi-agent code review in a cloud sandbox. Alias for /code-review ultra', source: 'default' },
  { command: '/deep-research', description: 'Workflow. Fan out web searches on a question, fetch and cross-check sources, and synthesize a cited report', source: 'default' },

  // --- Development ---
  { command: '/run', description: 'Skill. Launch and drive your project\'s app to see a change working in the running app. Requires v2.1.145+', source: 'default' },
  { command: '/verify', description: 'Skill. Confirm a code change does what it should by building, running, and observing the app. Requires v2.1.145+', source: 'default' },
  { command: '/debug', description: 'Skill. Enable debug logging for the current session and troubleshoot issues', source: 'default' },
  { command: '/fewer-permission-prompts', description: 'Skill. Scan transcripts for common read-only tool calls and add an allowlist to reduce permission prompts', source: 'default' },

  // --- Setup / configuration ---
  { command: '/init', description: 'Initialize project with a CLAUDE.md guide. Set CLAUDE_CODE_NEW_INIT=1 for interactive setup including skills, hooks, and personal memory', source: 'default' },
  { command: '/add-dir', description: 'Add a working directory for file access during the current session', source: 'default' },
  { command: '/terminal-setup', description: 'Install Shift+Enter key binding for newlines', source: 'default' },
  { command: '/reload-plugins', description: 'Reload all active plugins to apply pending changes without restarting', source: 'default' },
  { command: '/reload-skills', description: 'Re-scan skill and command directories so new or changed skills become available. Added in v2.1.152', source: 'default' },
  { command: '/run-skill-generator', description: 'Skill. Teach /run and /verify how to build and launch your project\'s app. Requires v2.1.145+', source: 'default' },

  // --- Information ---
  { command: '/help', description: 'Show help and available commands', source: 'default' },
  { command: '/insights', description: 'Generate a report analyzing your Claude Code sessions, including project areas, interaction patterns, and friction points', source: 'default' },
  { command: '/team-onboarding', description: 'Generate a team onboarding guide from your Claude Code usage history (past 30 days)', source: 'default' },

  // --- Navigation ---
  { command: '/exit', description: 'Exit the CLI. In an attached background session, this detaches and the session keeps running. Alias: /quit', source: 'default' },

  // --- Commands that open interactive TUI (output not displayable in web) ---
  // { command: '/model', description: 'Select or change the AI model', source: 'default' },
  // { command: '/mcp', description: 'Manage MCP server connections and OAuth authentication', source: 'default' },
  // { command: '/config', description: 'Open the Settings interface (Config tab)', source: 'default' },
  // { command: '/memory', description: 'Edit CLAUDE.md memory files', source: 'default' },
  // { command: '/permissions', description: 'View or update permissions', source: 'default' },
  // { command: '/hooks', description: 'Manage hook configurations for tool events', source: 'default' },
  // { command: '/agents', description: 'Manage custom AI subagents for specialized tasks', source: 'default' },
  // { command: '/plugin', description: 'Manage Claude Code plugins', source: 'default' },
  // { command: '/login', description: 'Switch Anthropic accounts', source: 'default' },
  // { command: '/logout', description: 'Sign out from your Anthropic account', source: 'default' },
  // { command: '/status', description: 'Open Settings interface showing version and account info', source: 'default' },
  // { command: '/rewind', description: 'Rewind the conversation and/or code', source: 'default' },
  // { command: '/resume', description: 'Resume a conversation', source: 'default' },
  // { command: '/fast', description: 'Toggle fast mode (uses Claude Opus with faster output)', source: 'default' },
  // { command: '/workflows', description: 'List and manage background workflows', source: 'default' },
  // { command: '/doctor', description: 'Checks the health of your Claude Code installation', source: 'default' },
  // { command: '/feedback', description: 'Submit feedback about Claude Code', source: 'default' },
  // { command: '/install-github-app', description: 'Set up Claude GitHub Actions for a repository', source: 'default' },
  // { command: '/privacy-settings', description: 'View and update your privacy settings', source: 'default' },
  // { command: '/sandbox', description: 'Enable sandboxed bash tool with filesystem isolation', source: 'default' },
  // { command: '/statusline', description: "Set up Claude Code's status line UI", source: 'default' },
  // { command: '/vim', description: 'Enter vim mode for alternating insert and command modes', source: 'default' },
  // { command: '/usage', description: 'Show plan usage limits and rate limit status', source: 'default' },
  // { command: '/ide', description: 'Manage IDE integrations and show status', source: 'default' },
  // { command: '/output-style', description: 'Set the output style directly or from a selection menu', source: 'default' },
  // { command: '/claude-api', description: 'Skill. Load Claude API reference material for your project language', source: 'default' },

  // --- Removed commands ---
  // { command: '/pr-comments', description: 'Removed in v2.1.91. Ask Claude directly to view pull request comments instead', source: 'default' },
];

/**
 * OpenAI Codex built-in slash commands
 * Source: codex-rs/tui/src/slash_command.rs
 */
export const CODEX_COMMANDS: SlashCommand[] = [
  { command: '/new', description: 'Start a new chat during a conversation', source: 'default' },
  { command: '/clear', description: 'Clear the terminal and start a new chat', source: 'default' },
  { command: '/compact', description: 'Summarize conversation to prevent hitting the context limit', source: 'default' },
  { command: '/init', description: 'Create an AGENTS.md file with instructions for Codex', source: 'default' },
  { command: '/plan', description: 'Switch to Plan mode', source: 'default' },
  { command: '/goal', description: 'Set or view the goal for a long-running task', source: 'default' },
  { command: '/raw', description: 'Toggle raw scrollback mode for copy-friendly terminal selection', source: 'default' },
  // { command: '/skills', description: 'Use skills to improve how Codex performs specific tasks', source: 'default' },
  { command: '/approve', description: 'Approve one retry of a recent auto-review denial', source: 'default' },
  // /status and /ps return output that must be rendered back to the user
  { command: '/status', description: 'Show current session configuration and token usage', source: 'default' },
  { command: '/ps', description: 'List background terminals', source: 'default' },
  { command: '/stop', description: 'Stop all background terminals', source: 'default' },
  { command: '/clean', description: 'Stop all background terminals (alias for /stop)', source: 'default' },
];

/**
 * OpenCode TUI built-in slash commands
 * Source: https://opencode.ai/docs/tui#commands
 */
export const OPENCODE_COMMANDS: SlashCommand[] = [
  // { command: '/sessions', description: 'Switch sessions', source: 'default' },
  { command: '/new', description: 'Start a new session', source: 'default' },
  // { command: '/models', description: 'Switch model', source: 'default' },
  // { command: '/agents', description: 'Switch agent', source: 'default' },
  // { command: '/mcps', description: 'Toggle MCPs', source: 'default' },
  // { command: '/connect', description: 'Connect provider', source: 'default' },
  // { command: '/status', description: 'View status', source: 'default' },
  // { command: '/themes', description: 'Switch theme', source: 'default' },
  // { command: '/help', description: 'Open help', source: 'default' },
  // { command: '/editor', description: 'Open editor', source: 'default' },
  { command: '/compact', description: 'Compact session', source: 'default' },
  { command: '/share', description: 'Share session', source: 'default' },
  // { command: '/rename', description: 'Rename session', source: 'default' },
  // { command: '/timeline', description: 'Jump to message', source: 'default' },
  // { command: '/fork', description: 'Fork from message', source: 'default' },
  { command: '/unshare', description: 'Unshare session', source: 'default' },
  // { command: '/undo', description: 'Undo previous message', source: 'default' },
  // { command: '/redo', description: 'Redo last undo', source: 'default' },
  // { command: '/timestamps', description: 'Toggle timestamps', source: 'default' },
  // { command: '/thinking', description: 'Toggle thinking', source: 'default' },
  // { command: '/copy', description: 'Copy session transcript', source: 'default' },
  // { command: '/export', description: 'Export session transcript', source: 'default' },
  { command: '/exit', description: 'Exit the app', source: 'default' },
];

/**
 * Get default commands for a specific agent type
 */
export function getDefaultCommands(agentType: AgentType): SlashCommand[] {
  switch (agentType) {
    case 'claude':
      return CLAUDE_CODE_COMMANDS;
    case 'codex':
      return CODEX_COMMANDS;
    case 'opencode':
      return OPENCODE_COMMANDS;
    default:
      return [];
  }
}

/**
 * Merge default and custom commands, maintaining default order and appending custom commands
 */
export function mergeCommands(
  defaultCommands: SlashCommand[],
  customCommands: SlashCommand[]
): SlashCommand[] {
  const defaultCommandNames = new Set(defaultCommands.map((cmd) => cmd.command));

  // Start with all default commands in their original order
  const result = [...defaultCommands];

  // Append only custom commands that don't override default ones. Preserve the
  // custom entry's kind/insert so skills stay distinguishable downstream.
  customCommands.forEach((cmd) => {
    if (!defaultCommandNames.has(cmd.command)) {
      result.push({ ...cmd, source: 'custom' });
    }
  });

  return result;
}
