/// Slash command definitions and default commands for different agent types.
/// Based on the vicoa-web implementation for consistency.

/// Represents a slash command with its metadata
class SlashCommand {
  final String command;
  final String description;
  final String source; // 'default' or 'custom'
  /// 'command' or 'skill'. Lets a future Skills tab list skills separately;
  /// built-in defaults are plain commands unless flagged otherwise.
  final String kind;
  /// Text to insert on selection when it differs from `command` — Codex
  /// invokes skills with `$name` rather than `/name`. Null means insert the
  /// command itself.
  final String? insert;

  const SlashCommand({
    required this.command,
    required this.description,
    this.source = 'default',
    this.kind = 'command',
    this.insert,
  });

  bool get isSkill => kind == 'skill';

  /// Creates a SlashCommand from a map (typically from API response)
  factory SlashCommand.fromMap(Map<String, dynamic> map) {
    String name = map['name']?.toString() ?? map['command']?.toString() ?? '';
    // Ensure command starts with '/'
    if (!name.startsWith('/')) {
      name = '/$name';
    }

    final insertRaw = map['insert']?.toString();
    return SlashCommand(
      command: name,
      description: map['description']?.toString() ?? '',
      source: map['source']?.toString() ?? 'custom',
      kind: map['kind']?.toString() == 'skill' ? 'skill' : 'command',
      insert: (insertRaw != null && insertRaw.isNotEmpty) ? insertRaw : null,
    );
  }

  /// Converts to a map for serialization
  Map<String, dynamic> toMap() {
    return {
      'name': command,
      'description': description,
      'source': source,
      'kind': kind,
      if (insert != null) 'insert': insert,
    };
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is SlashCommand && other.command == command;
  }

  @override
  int get hashCode => command.hashCode;
}

/// Agent types that support different command sets
enum AgentType {
  claude,
  codex,
  opencode,
}

/// Default Claude Code slash commands
/// Source: Claude Code v2.1.163
/// Synced with vicoa-web/lib/constants/slash-commands.ts
const List<SlashCommand> _claudeCommands = [
  // Session / context
  SlashCommand(command: '/clear', description: 'Start a new conversation. Pass a name to label the previous one in /resume. Aliases: /reset, /new'),
  SlashCommand(command: '/compact', description: 'Free up context by summarizing the conversation. Optionally pass focus instructions'),
  SlashCommand(command: '/context', description: 'Visualize current context usage as a colored grid'),
  SlashCommand(command: '/recap', description: 'Generate a one-line summary of the current session on demand'),
  SlashCommand(command: '/copy', description: 'Copy the last assistant response to clipboard. Pass N to copy the Nth-latest response'),
  SlashCommand(command: '/export', description: 'Export the current conversation as plain text'),

  // Task / workflow
  SlashCommand(command: '/btw', description: 'Ask a quick side question without adding to the conversation'),
  SlashCommand(command: '/plan', description: 'Enter plan mode. Pass a description to start immediately'),
  SlashCommand(command: '/goal', description: 'Set a goal: Claude keeps working until the condition is met. No arg shows current goal'),
  SlashCommand(command: '/fork', description: 'Spawn a forked subagent that inherits the full conversation and works in the background'),
  SlashCommand(command: '/background', description: 'Detach the current session to run as a background agent. Monitor with claude agents. Alias: /bg'),
  SlashCommand(command: '/stop', description: 'Stop the current background session (transcript and worktree are kept)'),
  SlashCommand(command: '/tasks', description: 'List and manage background tasks. Alias: /bashes'),
  SlashCommand(command: '/loop', description: 'Run a prompt repeatedly while the session stays open. Omit interval for model self-pacing. Alias: /proactive'),
  SlashCommand(command: '/schedule', description: 'Create, update, list, or run routines on Anthropic-managed cloud infrastructure. Alias: /routines'),
  SlashCommand(command: '/batch', description: 'Skill. Orchestrate large-scale changes across a codebase in parallel across up to 30 independent units'),
  SlashCommand(command: '/autofix-pr', description: "Spawn a Claude Code on the web session that watches the current branch's PR and pushes fixes when CI fails or reviewers comment. Requires gh CLI"),
  SlashCommand(command: '/ultraplan', description: 'Draft a plan in an ultraplan session, review in your browser, then execute remotely or send back to your terminal'),

  // Code review / analysis
  SlashCommand(command: '/review', description: 'Review a pull request locally. For deeper cloud-based review, use /code-review ultra'),
  SlashCommand(command: '/code-review', description: 'Skill. Review the current diff for bugs and cleanups. Pass --fix to apply, --comment to post as PR comments, or ultra for deep cloud review'),
  SlashCommand(command: '/simplify', description: 'Skill. Review changed code for cleanup opportunities and apply fixes. Does not look for bugs — use /code-review for that'),
  SlashCommand(command: '/security-review', description: 'Analyze pending changes on the current branch for security vulnerabilities'),
  SlashCommand(command: '/ultrareview', description: 'Run a deep, multi-agent code review in a cloud sandbox. Alias for /code-review ultra'),
  SlashCommand(command: '/deep-research', description: 'Workflow. Fan out web searches on a question, fetch and cross-check sources, and synthesize a cited report'),

  // Development
  SlashCommand(command: '/run', description: "Skill. Launch and drive your project's app to see a change working in the running app. Requires v2.1.145+"),
  SlashCommand(command: '/verify', description: 'Skill. Confirm a code change does what it should by building, running, and observing the app. Requires v2.1.145+'),
  SlashCommand(command: '/debug', description: 'Skill. Enable debug logging for the current session and troubleshoot issues'),
  SlashCommand(command: '/fewer-permission-prompts', description: 'Skill. Scan transcripts for common read-only tool calls and add an allowlist to reduce permission prompts'),

  // Setup / configuration
  SlashCommand(command: '/init', description: 'Initialize project with a CLAUDE.md guide. Set CLAUDE_CODE_NEW_INIT=1 for interactive setup'),
  SlashCommand(command: '/add-dir', description: 'Add a working directory for file access during the current session'),
  SlashCommand(command: '/terminal-setup', description: 'Install Shift+Enter key binding for newlines'),
  SlashCommand(command: '/reload-plugins', description: 'Reload all active plugins to apply pending changes without restarting'),
  SlashCommand(command: '/reload-skills', description: 'Re-scan skill and command directories so new or changed skills become available. Added in v2.1.152'),
  SlashCommand(command: '/run-skill-generator', description: "Skill. Teach /run and /verify how to build and launch your project's app. Requires v2.1.145+"),

  // Information
  SlashCommand(command: '/help', description: 'Show help and available commands'),
  SlashCommand(command: '/insights', description: 'Generate a report analyzing your Claude Code sessions, including project areas, interaction patterns, and friction points'),
  SlashCommand(command: '/team-onboarding', description: 'Generate a team onboarding guide from your Claude Code usage history (past 30 days)'),

  // Navigation
  SlashCommand(command: '/exit', description: 'Exit the CLI. In an attached background session, this detaches and the session keeps running. Alias: /quit'),
];

/// Default Codex slash commands
/// Source: codex-rs/tui/src/slash_command.rs
const List<SlashCommand> _codexCommands = [
  SlashCommand(command: '/new', description: 'Start a new chat during a conversation'),
  SlashCommand(command: '/clear', description: 'Clear the terminal and start a new chat'),
  SlashCommand(command: '/compact', description: 'Summarize conversation to prevent hitting the context limit'),
  SlashCommand(command: '/init', description: 'Create an AGENTS.md file with instructions for Codex'),
  SlashCommand(command: '/plan', description: 'Switch to Plan mode'),
  SlashCommand(command: '/goal', description: 'Set or view the goal for a long-running task'),
  SlashCommand(command: '/raw', description: 'Toggle raw scrollback mode for copy-friendly terminal selection'),
  // SlashCommand(command: '/skills', description: 'Use skills to improve how Codex performs specific tasks'),
  SlashCommand(command: '/approve', description: 'Approve one retry of a recent auto-review denial'),
  // /status and /ps return output that must be rendered back to the user
  // SlashCommand(command: '/status', description: 'Show current session configuration and token usage'),
  // SlashCommand(command: '/ps', description: 'List background terminals'),
  SlashCommand(command: '/stop', description: 'Stop all background terminals'),
  SlashCommand(command: '/clean', description: 'Stop all background terminals (alias for /stop)'),
];

/// Default OpenCode TUI slash commands
/// Based on vicoa-web/lib/constants/slash-commands.ts
const List<SlashCommand> _opencodeCommands = [
  SlashCommand(command: '/new', description: 'Start a new session'),
  SlashCommand(command: '/compact', description: 'Compact session'),
  SlashCommand(command: '/share', description: 'Share session'),
  SlashCommand(command: '/unshare', description: 'Unshare session'),
  SlashCommand(command: '/exit', description: 'Exit the app'),
];

/// Get default slash commands for a specific agent type
List<SlashCommand> getDefaultCommands(AgentType agentType) {
  switch (agentType) {
    case AgentType.claude:
      return _claudeCommands;
    case AgentType.codex:
      return _codexCommands;
    case AgentType.opencode:
      return _opencodeCommands;
  }
}

/// Get default commands for a string-based agent type identifier
List<SlashCommand> getDefaultCommandsByString(String agentType) {
  final type = agentType.toLowerCase();
  if (type.contains('claude')) {
    return getDefaultCommands(AgentType.claude);
  } else if (type.contains('codex')) {
    return getDefaultCommands(AgentType.codex);
  } else if (type.contains('opencode')) {
    return getDefaultCommands(AgentType.opencode);
  }
  // Default to Claude commands for unknown types
  return getDefaultCommands(AgentType.claude);
}

/// Merge default and custom commands, with custom commands overriding defaults
/// Custom commands with the same name as default commands will replace them
List<SlashCommand> mergeCommands(
  List<SlashCommand> defaultCommands,
  List<SlashCommand> customCommands,
) {
  // Preserve the preset order from defaultCommands.
  final result = List<SlashCommand>.from(defaultCommands);
  final Map<String, int> indexByCommand = {};

  for (var i = 0; i < result.length; i++) {
    indexByCommand[result[i].command] = i;
  }

  for (final cmd in customCommands) {
    // Preserve kind/insert so skills stay distinguishable downstream.
    final custom = SlashCommand(
      command: cmd.command,
      description: cmd.description,
      source: 'custom',
      kind: cmd.kind,
      insert: cmd.insert,
    );

    if (indexByCommand.containsKey(cmd.command)) {
      // Replace existing command while keeping its position.
      final idx = indexByCommand[cmd.command]!;
      result[idx] = custom;
    } else {
      // Append new custom commands after defaults in received order.
      indexByCommand[cmd.command] = result.length;
      result.add(custom);
    }
  }

  return result;
}
