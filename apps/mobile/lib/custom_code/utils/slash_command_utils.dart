import 'package:flutter/material.dart';
import 'dart:async';

import '/constants/slash_commands.dart';
import '/custom_code/actions/index.dart' as actions;

/// Shared slash-command state + load/filter/insert behavior used by both the
/// agent chat page and the new-session sheet. Subclasses provide the text
/// controller, a state-change callback, and the active agent type name.
mixin SlashCommandMixin {
  List<SlashCommand> slashCommands = [];
  List<SlashCommand> filteredSlashCommands = [];
  bool showSlashCommandSuggestions = false;
  bool isLoadingSlashCommands = false;
  String? _loadedSlashCommandsAgent;

  TextEditingController get slashCommandTextController;
  VoidCallback? get slashCommandOnStateChanged;

  /// Raw agent name (e.g. 'Claude Code', 'codex', 'opencode', or null when
  /// unknown). The mixin normalizes 'claude code' → 'claude' so cache + API
  /// keys line up across pages.
  String? resolveSlashCommandRawAgentType();

  /// Machine this session runs on, or null. With it, custom commands read the
  /// live daemon index (`scan-commands`); without it they read the CLI-synced
  /// DB copy. Chat overrides this; the new-session sheet leaves it null (no
  /// bound machine yet), matching the file-mention path.
  String? resolveSlashCommandMachineId() => null;

  /// Session's project path — scopes project-local `.claude/commands` and
  /// `./.agents/skills`. Null falls back to the machine's global sources only.
  String? resolveSlashCommandProjectPath() => null;

  /// Fires once per call to [filterSlashCommands] when the user has typed
  /// anything starting with `/`. Default is a no-op; AgentChatModel overrides
  /// this for its session-first silent refresh.
  void onSlashCommandFilterTriggered() {}

  /// Normalized agent key for cache + API. Falls back to 'claude' when the
  /// subclass doesn't know yet.
  @protected
  String get slashCommandAgentKey {
    var name = resolveSlashCommandRawAgentType() ?? 'claude';
    if (name.toLowerCase() == 'claude code') name = 'claude';
    return name.isEmpty ? 'claude' : name;
  }

  /// Load available slash commands for the active agent.
  ///
  /// Resolution order: in-memory cache → disk cache → network fetch. The
  /// session-wide memory cache means a reopen of a chat (or an agent re-pick
  /// in the new-session sheet) with the same agent type skips even the async
  /// hop. Only API-fetched custom commands are cached; defaults live in code
  /// and are merged in here.
  Future<void> loadSlashCommands() async {
    if (isLoadingSlashCommands) return;
    final agentTypeName = slashCommandAgentKey;
    if (_loadedSlashCommandsAgent == agentTypeName && slashCommands.isNotEmpty) {
      return;
    }
    isLoadingSlashCommands = true;

    final defaultCommands = getDefaultCommandsByString(agentTypeName);

    final memCached =
        actions.SlashCommandsCache.instance.readFromMemory(agentTypeName);
    if (memCached != null) {
      slashCommands = mergeCommands(defaultCommands, memCached);
      _loadedSlashCommandsAgent = agentTypeName;
      filterSlashCommands(slashCommandTextController.text);
      isLoadingSlashCommands = false;
      slashCommandOnStateChanged?.call();
      return;
    }

    // Show defaults immediately while we resolve the rest async.
    slashCommands = defaultCommands;
    _loadedSlashCommandsAgent = agentTypeName;
    slashCommandOnStateChanged?.call();

    try {
      final diskCached =
          await actions.SlashCommandsCache.instance.read(agentTypeName);
      if (diskCached != null) {
        slashCommands = mergeCommands(defaultCommands, diskCached);
        filterSlashCommands(slashCommandTextController.text);
        return;
      }

      final fetch = await actions.fetchSlashCommands(
        agentType: agentTypeName,
        machineId: resolveSlashCommandMachineId(),
        projectPath: resolveSlashCommandProjectPath(),
      );
      // On a cold disk miss there is no knownHash, so the daemon never replies
      // `unchanged` here — commands is non-null. Guard anyway.
      final customCommands = fetch.commands ?? const <SlashCommand>[];
      slashCommands = mergeCommands(defaultCommands, customCommands);
      filterSlashCommands(slashCommandTextController.text);
      if (customCommands.isNotEmpty) {
        unawaited(actions.SlashCommandsCache.instance.write(
            agentTypeName, customCommands,
            hash: fetch.source == actions.SlashCommandsSource.rpc
                ? fetch.hash
                : null));
      }
    } catch (e) {
      debugPrint('Error loading slash commands: $e');
      slashCommands = defaultCommands;
      filterSlashCommands(slashCommandTextController.text);
    } finally {
      isLoadingSlashCommands = false;
      slashCommandOnStateChanged?.call();
    }
  }

  /// Background fetch that updates [slashCommands] and the disk cache without
  /// firing the filter or onStateChanged hooks — used by chat-side staleness
  /// refreshes so the popup doesn't re-render while the user is reading it.
  @protected
  Future<void> refreshSlashCommandsSilently() async {
    final agentTypeName = slashCommandAgentKey;
    try {
      final knownHash =
          await actions.SlashCommandsCache.instance.readHash(agentTypeName);
      final fetch = await actions.fetchSlashCommands(
        agentType: agentTypeName,
        machineId: resolveSlashCommandMachineId(),
        projectPath: resolveSlashCommandProjectPath(),
        knownHash: knownHash,
      );
      if (fetch.unchanged) {
        // Daemon's index still matches the cached list — just reset the
        // staleness clock so we don't re-probe on the next open.
        unawaited(actions.SlashCommandsCache.instance
            .touch(agentTypeName, hash: fetch.hash));
        return;
      }
      final customCommands = fetch.commands ?? const <SlashCommand>[];
      final defaultCommands = getDefaultCommandsByString(agentTypeName);
      slashCommands = mergeCommands(defaultCommands, customCommands);
      if (customCommands.isNotEmpty) {
        unawaited(actions.SlashCommandsCache.instance.write(
            agentTypeName, customCommands,
            hash: fetch.source == actions.SlashCommandsSource.rpc
                ? fetch.hash
                : null));
      }
    } catch (e) {
      debugPrint('Error refreshing slash commands: $e');
    }
  }

  /// Filter slash commands based on current input text.
  void filterSlashCommands(String text) {
    final input = text.trimLeft();
    if (!input.startsWith('/')) {
      showSlashCommandSuggestions = false;
      filteredSlashCommands = [];
      slashCommandOnStateChanged?.call();
      return;
    }

    onSlashCommandFilterTriggered();

    final commandPart = input.substring(1).split(' ').first.toLowerCase();
    filteredSlashCommands = slashCommands.where((cmd) {
      final commandName = cmd.command.startsWith('/')
          ? cmd.command.substring(1).toLowerCase()
          : cmd.command.toLowerCase();
      return commandName.startsWith(commandPart);
    }).toList();
    showSlashCommandSuggestions = filteredSlashCommands.isNotEmpty;
    slashCommandOnStateChanged?.call();
  }

  /// Insert a slash command into the bound text controller, swapping just the
  /// command word at the cursor for `/<name>` and dismissing the popup. Any
  /// draft text after the command is preserved — symmetric with
  /// [FileMentionMixin.insertFileMention] so the two affordances feel the
  /// same.
  void insertSlashCommand(String commandName, {String? insertText}) {
    // A Codex skill inserts `$name` verbatim (via [insertText]); everything
    // else inserts `/name`.
    final command = (insertText != null && insertText.isNotEmpty)
        ? insertText
        : (commandName.startsWith('/') ? commandName : '/$commandName');
    final text = slashCommandTextController.text;
    final selection = slashCommandTextController.selection;
    final cursorPos = selection.isValid && selection.baseOffset >= 0
        ? selection.baseOffset.clamp(0, text.length)
        : text.length;

    // Look back for the slash that opens the current command word. Panel
    // visibility already guarantees text starts with '/' (after any leading
    // whitespace), so this mirrors insertFileMention's '@' lookup.
    final slashIndex =
        cursorPos > 0 ? text.lastIndexOf('/', cursorPos - 1) : -1;
    if (slashIndex == -1) return;

    // Replace from slashIndex through the current word (up to the next
    // whitespace or end of text) — keeps any draft text after the command.
    int wordEnd = cursorPos;
    while (wordEnd < text.length) {
      final ch = text[wordEnd];
      if (ch == ' ' || ch == '\n' || ch == '\t') break;
      wordEnd++;
    }

    final beforeSlash = text.substring(0, slashIndex);
    final afterWord = text.substring(wordEnd);
    final needsSpace = afterWord.isEmpty ||
        (afterWord[0] != ' ' && afterWord[0] != '\n' && afterWord[0] != '\t');
    final separator = needsSpace ? ' ' : '';
    final newText = '$beforeSlash$command$separator$afterWord';
    final newCursorPos =
        beforeSlash.length + command.length + separator.length;

    slashCommandTextController.text = newText;
    slashCommandTextController.selection = TextSelection.fromPosition(
      TextPosition(offset: newCursorPos),
    );
    showSlashCommandSuggestions = false;
    filteredSlashCommands = [];
    slashCommandOnStateChanged?.call();
  }
}
