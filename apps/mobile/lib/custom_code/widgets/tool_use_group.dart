// Collapsed tool-use rendering for the agent chat. A run of consecutive tool
// uses collapses to a single bordered summary header ("Run 2 commands, edit 2
// files"); tapping it reveals each tool in the current bordered format, and
// each tool row with output beyond its header carries its own chevron to expand
// that output. A standalone tool renders as its bordered row with a chevron for
// its detail. Gated by the `collapseToolUse` appearance setting.

import 'package:flutter/material.dart';
import '/custom_code/widgets/markdown_text_builder.dart'
    show
        parseToolMessage,
        sanitizeToolContent,
        buildCollapsibleToolRow,
        buildToolGroupHeader;
import '/custom_code/widgets/tool_icon.dart' show representativeToolName;

/// Compact summary of one tool-use message, used to build a run's aggregate
/// label (["Run 2 commands, edit 2 files"]).
class ToolUseSummary {
  const ToolUseSummary({
    required this.name,
    required this.description,
    required this.hasDetail,
    this.fileName,
  });

  final String name; // display name, e.g. Edit / Bash / Todos / Edited
  final String description; // backticks stripped, single line (command or path)
  final String? fileName; // basename when the description is a lone path
  final bool hasDetail; // trailing code / output or a multi-line description

  bool get isShell => name == 'Bash' || name == 'Exec';
  bool get isFile => fileName != null && fileName!.isNotEmpty;
}

String _stripBackticks(String v) =>
    v.replaceFirst(RegExp(r'^`'), '').replaceFirst(RegExp(r'`$'), '').trim();

/// Tolerant tool-name key: case- and separator-insensitive, so `AskUserQuestion`,
/// `askUserQuestion`, and `ask_user_question` all compare equal.
String _toolNameKey(String name) =>
    name.replaceAll(RegExp(r'[\s_]'), '').toLowerCase();

/// Whether a (sanitized) tool-use message is an AskUserQuestion tool use.
///
/// Distinct from the `message_metadata.ask_user_question` payload check: the
/// announcement message ("Using tool: **AskUserQuestion** - ...") carries no
/// metadata at all, so a payload-only guard lets it fold into a run and vanish
/// behind a summary header ("Run 2 commands, askuserquestion"). Matching the
/// parsed tool name catches the announcement, a message whose payload failed to
/// parse, and the post-answer summary alike.
bool isAskUserQuestionToolContent(String content) =>
    _toolNameKey(parseToolMessage(content).toolName) == 'askuserquestion';

/// Parses a single (already sanitized) tool-use message into a [ToolUseSummary].
ToolUseSummary summarizeToolMessage(String content) {
  final f = parseToolMessage(content);
  var desc = f.toolDescription.trim();

  // Drop a trailing "+N -M" diff stat so a lone path parses to a clean file.
  final diffMatch = RegExp(r'(\+\d+\s+-\d+)\s*$').firstMatch(desc);
  if (diffMatch != null) desc = desc.substring(0, diffMatch.start).trim();

  final stripped = _stripBackticks(desc);
  String? fileName;
  if (stripped.isNotEmpty &&
      !RegExp(r'\s').hasMatch(stripped) &&
      (stripped.contains('/') || stripped.contains('.'))) {
    final segments = stripped.split('/').where((s) => s.isNotEmpty).toList();
    fileName = segments.isNotEmpty ? segments.last : stripped;
  }

  final hasDetail =
      f.remainingContent.trim().isNotEmpty || f.isMultilineDescription;

  return ToolUseSummary(
    name: f.toolName,
    description: stripped,
    fileName: fileName,
    hasDetail: hasDetail,
  );
}

/// Pure decision: whether a message can fold into a collapsed tool-use run
/// (see [ToolUseGroup] / the page's `_isCollapsibleToolUse`). Callers pass in
/// message-level facts already resolved from context — sender type, the
/// requires-user-input flag, whether an AskUserQuestion payload is attached,
/// whether the tool itself is AskUserQuestion, sub-agent tagging, tool-use
/// content shape, and OPTIONS-block validity — so this stays independent of the
/// chat's message-list state and directly unit-testable.
///
/// [isSubagentMessage] must always exclude: a sub-agent (Task tool) child
/// message is rendered exactly once, inside its own `SubagentGroup` anchor
/// (see `subagent_group.dart`). Letting it also join a consecutive tool-use
/// run here would render that same content a second time.
///
/// [isAskUserQuestionTool] must always exclude, and is deliberately checked
/// separately from [hasAskUserQuestionPayload] — neither subsumes the other:
///
///  - Payload but no name match: the wrapper drops the AskUserQuestion tool_use
///    block before formatting, so when Claude emits it alongside other blocks
///    the content is those *other* blocks ("Using tool: **Bash** - ...") with
///    the payload still attached. Only the payload check sees that one.
///  - Name match but no payload: the bare "Using tool: **AskUserQuestion** - ..."
///    announcement carries no metadata at all.
///
/// The payload check keeps the interactive panel from being collapsed away; the
/// name check keeps the rendered tool row standalone so the question stays
/// readable in place instead of being summarized behind a header.
bool isCollapsibleToolUseMessage({
  required bool isUserOrHumanSender,
  required bool requiresUserInput,
  required bool hasAskUserQuestionPayload,
  required bool isAskUserQuestionTool,
  required bool isSubagentMessage,
  required bool isToolUseContent,
  required bool hasValidOptionsBlock,
}) {
  if (isUserOrHumanSender) return false;
  if (requiresUserInput) return false;
  if (hasAskUserQuestionPayload) return false;
  if (isAskUserQuestionTool) return false;
  if (isSubagentMessage) return false;
  if (!isToolUseContent) return false;
  if (hasValidOptionsBlock) return false;
  return true;
}

/// Builds the aggregate, sentence-cased label for a run of tool uses — e.g.
/// "Run 2 commands, edit 2 files, read a file". Distinct tools are listed in
/// first-use order; file tools count distinct paths; shell tools become
/// "Run a command"/"Run N commands". Falls back to "N tool uses" when nothing
/// parses. English-only (matches the vicoa-web source).
String describeToolRun(List<ToolUseSummary> tools) {
  if (tools.isEmpty) return '';

  final order = <String>[];
  final occurrences = <String, int>{};
  final distinctFiles = <String, Set<String>>{};
  final verbs = <String, String>{};
  final nouns = <String, String>{}; // '' marks a "bare tool name" entry
  var parsedAny = false;

  for (final t in tools) {
    if (t.name.isEmpty) continue;
    parsedAny = true;

    final String key;
    if (t.isShell) {
      key = 'shell';
      verbs[key] = 'run';
      nouns[key] = 'command';
    } else if (t.isFile) {
      key = 'file:${t.name}';
      verbs[key] = t.name.toLowerCase();
      nouns[key] = 'file';
    } else {
      key = 'other:${t.name}';
      verbs[key] = t.name.toLowerCase();
      nouns[key] = '';
    }

    if (!order.contains(key)) order.add(key);
    occurrences[key] = (occurrences[key] ?? 0) + 1;
    if (t.isFile) (distinctFiles[key] ??= <String>{}).add(t.fileName!);
  }

  if (!parsedAny) return '${tools.length} tool uses';

  final parts = <String>[];
  for (final key in order) {
    final verb = verbs[key]!;
    final noun = nouns[key]!;
    if (noun.isEmpty) {
      final n = occurrences[key]!;
      parts.add(n > 1 ? '$verb ($n)' : verb);
    } else {
      final n = noun == 'file'
          ? (distinctFiles[key]?.length ?? occurrences[key]!)
          : occurrences[key]!;
      parts.add(n == 1 ? '$verb a $noun' : '$verb $n ${noun}s');
    }
  }

  final joined = parts.join(', ');
  if (joined.isEmpty) return '${tools.length} tool uses';
  return joined[0].toUpperCase() + joined.substring(1);
}

/// A run of consecutive tool uses. A single tool renders as one bordered row
/// (its detail collapsed behind a chevron); a multi-tool run renders a bordered
/// summary header that, when expanded, reveals the border-joined tool rows —
/// each independently expandable. The run-level (header / single-row) expansion
/// is owned by the parent so it survives list recycling; per-row expansion in a
/// group is local.
class ToolUseGroup extends StatefulWidget {
  const ToolUseGroup({
    super.key,
    required this.contents,
    required this.expanded,
    required this.onToggle,
    this.onBeforeToggle,
    this.agentTypeName,
    this.filterProjectRoot,
  });

  /// Sanitized tool-use message contents, in chat order.
  final List<String> contents;
  final bool expanded;
  final VoidCallback onToggle;

  /// Called immediately before any expand/collapse here — the run header, the
  /// single-tool row, or a nested row. Lets the host pin its scroll position so
  /// the tapped line doesn't shift as the content grows.
  final VoidCallback? onBeforeToggle;
  final String? agentTypeName;
  final String Function(String content)? filterProjectRoot;

  @override
  State<ToolUseGroup> createState() => _ToolUseGroupState();
}

class _ToolUseGroupState extends State<ToolUseGroup> {
  final Set<int> _expandedChildren = <int>{};

  /// Run-level toggle (header or single row), owned by the parent.
  void _toggleRun() {
    widget.onBeforeToggle?.call();
    widget.onToggle();
  }

  /// Per-row detail toggle inside an expanded run.
  void _toggleChild(int i) {
    widget.onBeforeToggle?.call();
    setState(() {
      if (!_expandedChildren.remove(i)) _expandedChildren.add(i);
    });
  }

  @override
  Widget build(BuildContext context) {
    final raw = widget.contents;
    if (raw.isEmpty) return const SizedBox.shrink();

    final contents = [
      for (final c in raw)
        sanitizeToolContent(c,
            agentTypeName: widget.agentTypeName,
            filterProjectRoot: widget.filterProjectRoot),
    ];

    // Single tool: one bordered row; its detail (or an over-long header) toggled
    // by the parent-owned flag, so it survives scrolling. The row itself decides
    // whether there's anything to expand.
    if (contents.length == 1) {
      return buildCollapsibleToolRow(
        context,
        contents.first,
        agentTypeName: widget.agentTypeName,
        toolUseIsFirst: true,
        toolUseIsLast: true,
        expanded: widget.expanded,
        onToggle: _toggleRun,
      );
    }

    final summaries = [for (final c in contents) summarizeToolMessage(c)];
    final label = describeToolRun(summaries);
    final iconToolName =
        representativeToolName([for (final s in summaries) s.name]);

    // Collapsed: just the summary header.
    if (!widget.expanded) {
      return buildToolGroupHeader(
        context,
        label,
        isLast: true,
        expanded: false,
        onToggle: _toggleRun,
        iconToolName: iconToolName,
        agentTypeName: widget.agentTypeName,
      );
    }

    // Expanded: summary header on top, then the border-joined tool rows.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildToolGroupHeader(
          context,
          label,
          isLast: false,
          expanded: true,
          onToggle: _toggleRun,
          iconToolName: iconToolName,
          agentTypeName: widget.agentTypeName,
        ),
        for (int i = 0; i < contents.length; i++)
          buildCollapsibleToolRow(
            context,
            contents[i],
            agentTypeName: widget.agentTypeName,
            toolUseIsFirst: false,
            toolUseIsLast: i == contents.length - 1,
            expanded: _expandedChildren.contains(i),
            onToggle: () => _toggleChild(i),
          ),
      ],
    );
  }
}
