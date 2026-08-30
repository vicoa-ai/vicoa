// Collapsed sub-agent (Task tool) rendering for the agent chat. Child
// messages carry `message_metadata.subagent = { tool_use_id, subagent_type,
// description, role }` (see `src/integrations/headless/subagent.py` in
// vicoa-backend); every message sharing a `tool_use_id` groups under one
// "Sub-agent: <type>" collapsible header, indented like `ToolUseGroup`.
//
// Unlike `ToolUseGroup`'s consecutive-run grouping, sub-agent grouping is
// ANCHORED AT FIRST OCCURRENCE of each `tool_use_id`: Claude can run parallel
// sub-agents whose child messages interleave in chat order (A, B, A, B, ...).
// `computeSubagentGrouping` below is the pure, unit-testable core of that
// bucketing; the widget itself only renders.

import 'package:flutter/material.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/custom_code/widgets/markdown_text_builder.dart'
    show
        buildMarkdownText,
        buildCollapsibleToolRow,
        buildToolGroupHeader,
        sanitizeToolContent;

/// Reads a message's `message_metadata.subagent.tool_use_id`, or null when
/// [message] isn't tagged as sub-agent activity (not a Map, no metadata, or a
/// blank id). This is the sole grouping key — sub-agent messages with the
/// same `tool_use_id` belong to the same collapsible group.
String? subagentToolUseIdOf(dynamic message) {
  if (message is! Map) return null;
  final metadata = message['message_metadata'];
  if (metadata is! Map) return null;
  final subagent = metadata['subagent'];
  if (subagent is! Map) return null;
  final toolUseId = subagent['tool_use_id'];
  if (toolUseId == null) return null;
  final id = toolUseId.toString();
  return id.isEmpty ? null : id;
}

/// Reads `message_metadata.subagent.subagent_type`, defaulting to `'agent'`
/// to match the backend's `SubAgentTracker` fallback.
String subagentTypeOf(dynamic message) {
  if (message is! Map) return 'agent';
  final metadata = message['message_metadata'];
  if (metadata is! Map) return 'agent';
  final subagent = metadata['subagent'];
  if (subagent is! Map) return 'agent';
  final type = subagent['subagent_type']?.toString().trim();
  return (type == null || type.isEmpty) ? 'agent' : type;
}

/// Reads `message_metadata.subagent.description`, or null when absent/blank.
String? subagentDescriptionOf(dynamic message) {
  if (message is! Map) return null;
  final metadata = message['message_metadata'];
  if (metadata is! Map) return null;
  final subagent = metadata['subagent'];
  if (subagent is! Map) return null;
  final desc = subagent['description']?.toString().trim();
  return (desc == null || desc.isEmpty) ? null : desc;
}

/// Precomputed, anchor-at-first-occurrence bucketing of sub-agent messages by
/// `tool_use_id`, over a full chat message list. Pure and independent of any
/// widget/list-recycling lifecycle so it's directly unit-testable; the chat
/// page's `_isSubagentMessage`/`_isSubagentRunStart`/`_collectSubagentRunIndices`
/// wrap an instance of this held in State.
class SubagentGrouping {
  const SubagentGrouping({
    required this.toolUseIdByIndex,
    required this.indicesById,
  });

  /// message[i]'s subagent tool_use_id, or null when message[i] isn't
  /// sub-agent activity. Same length as the source message list.
  final List<String?> toolUseIdByIndex;

  /// For each tool_use_id, every index in the source list carrying it, in
  /// list order. May be non-contiguous (interleaved parallel sub-agents).
  final Map<String, List<int>> indicesById;

  bool isSubagentMessage(int index) =>
      index >= 0 &&
      index < toolUseIdByIndex.length &&
      toolUseIdByIndex[index] != null;

  /// True only at the first index carrying its tool_use_id — the anchor at
  /// which the whole group renders. Every other member renders nothing.
  bool isRunStart(int index) {
    if (!isSubagentMessage(index)) return false;
    final indices = indicesById[toolUseIdByIndex[index]!];
    return indices != null && indices.isNotEmpty && indices.first == index;
  }

  /// All indices sharing [index]'s tool_use_id (including [index] itself),
  /// wherever they fall in the list. Empty when [index] isn't sub-agent
  /// activity.
  List<int> runIndices(int index) {
    if (!isSubagentMessage(index)) return const [];
    return indicesById[toolUseIdByIndex[index]!] ?? const [];
  }
}

/// Sanitizes each entry in [contents] via [sanitizeToolContent] and drops any
/// that come out empty (e.g. a stderr-only tool result whose content
/// sanitises down to `''`), so [SubagentGroup] never renders a blank bubble
/// for a member with no real content. Pure and independent of the widget
/// lifecycle, mirroring [computeSubagentGrouping]'s testable-core pattern —
/// [SubagentGroup.build] is the sole caller.
List<String> visibleSubagentGroupContents(
  List<String> contents, {
  String? agentTypeName,
  String Function(String content)? filterProjectRoot,
}) {
  return [
    for (final c in contents)
      sanitizeToolContent(c,
          agentTypeName: agentTypeName, filterProjectRoot: filterProjectRoot),
  ]..removeWhere((c) => c.trim().isEmpty);
}

/// Builds a [SubagentGrouping] from a chat's message list in a single pass.
SubagentGrouping computeSubagentGrouping(List<dynamic> messages) {
  final toolUseIdByIndex = <String?>[];
  final indicesById = <String, List<int>>{};
  for (int i = 0; i < messages.length; i++) {
    final id = subagentToolUseIdOf(messages[i]);
    toolUseIdByIndex.add(id);
    if (id != null) {
      (indicesById[id] ??= <int>[]).add(i);
    }
  }
  return SubagentGrouping(
    toolUseIdByIndex: toolUseIdByIndex,
    indicesById: indicesById,
  );
}

/// A group of one sub-agent's chat messages, collapsed behind a "Sub-agent:
/// <type>" header (+ description) mirroring [buildToolGroupHeader]'s bordered
/// style. Expanded, it renders exactly like a top-level tool-use run
/// ([ToolUseGroup]): no indent, no left rule — the header fuses with the first
/// tool run directly beneath it into one continuous bordered box. Plain-text
/// children render as a lightweight bubble and break the run.
class SubagentGroup extends StatefulWidget {
  const SubagentGroup({
    super.key,
    required this.subagentType,
    this.description,
    required this.contents,
    required this.expanded,
    required this.onToggle,
    this.onBeforeToggle,
    this.agentTypeName,
    this.filterProjectRoot,
  });

  /// e.g. "Explore", "general-purpose" — from `subagent_type`.
  final String subagentType;
  final String? description;

  /// Sanitized message contents belonging to this sub-agent run, in chat order.
  final List<String> contents;
  final bool expanded;
  final VoidCallback onToggle;

  /// Called immediately before any expand/collapse here (the group header),
  /// mirroring [ToolUseGroup.onBeforeToggle] — lets the host pin scroll
  /// position so the tapped line doesn't shift as content grows.
  final VoidCallback? onBeforeToggle;
  final String? agentTypeName;
  final String Function(String content)? filterProjectRoot;

  @override
  State<SubagentGroup> createState() => _SubagentGroupState();
}

class _SubagentGroupState extends State<SubagentGroup> {
  // Per-row detail expansion for tool-use children, keyed by index into the
  // sanitized `contents` list. Mirrors `_ToolUseGroupState._expandedChildren`;
  // resets if the row is recycled offscreen, which is acceptable.
  final Set<int> _expandedChildren = <int>{};

  void _toggleRun() {
    widget.onBeforeToggle?.call();
    widget.onToggle();
  }

  /// Per-row detail toggle inside the expanded group.
  void _toggleChild(int i) {
    widget.onBeforeToggle?.call();
    setState(() {
      if (!_expandedChildren.remove(i)) _expandedChildren.add(i);
    });
  }

  String get _label {
    final type = widget.subagentType.trim();
    final header = 'Sub-agent: ${type.isEmpty ? 'agent' : type}';
    final desc = widget.description?.trim();
    return (desc == null || desc.isEmpty) ? header : '$header — $desc';
  }

  @override
  Widget build(BuildContext context) {
    final raw = widget.contents;
    if (raw.isEmpty) return const SizedBox.shrink();

    // Members whose content sanitises down to '' (e.g. a stderr-only tool
    // result — see the empty-anchor fix in agent_chat_widget.dart) are
    // dropped here rather than rendered as blank bubbles. The group header
    // still renders below as long as at least one member survives.
    final contents = visibleSubagentGroupContents(
      raw,
      agentTypeName: widget.agentTypeName,
      filterProjectRoot: widget.filterProjectRoot,
    );

    if (!widget.expanded) {
      return buildToolGroupHeader(
        context,
        _label,
        isLast: true,
        expanded: false,
        onToggle: _toggleRun,
        iconToolName: 'Task',
        agentTypeName: widget.agentTypeName,
      );
    }

    // The header fuses with the first tool run directly beneath it (like a
    // top-level tool group's summary header), so it's bottom-square then. When
    // the first surviving child is plain text, the header closes itself off
    // (bottom-rounded) and an 8px gap separates it from that text.
    final firstIsTool = contents.isNotEmpty && _isToolUseContent(contents.first);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildToolGroupHeader(
          context,
          _label,
          isLast: !firstIsTool,
          expanded: true,
          onToggle: _toggleRun,
          iconToolName: 'Task',
          agentTypeName: widget.agentTypeName,
        ),
        if (!firstIsTool && contents.isNotEmpty) const SizedBox(height: 8.0),
        ..._buildChildren(context, contents),
      ],
    );
  }

  /// Renders the sub-agent's children with the same tight, border-joined look
  /// as a top-level tool run (see `ToolUseGroup`): a maximal run of consecutive
  /// tool-use children fuses into one continuous bordered box — zero gap,
  /// corners rounded only at the run's ends — via [buildCollapsibleToolRow]
  /// with computed `toolUseIsFirst`/`toolUseIsLast`. The very first run also
  /// fuses upward into the group header (its first row draws no top border),
  /// exactly like a top-level group's header + rows. Plain-text children render
  /// as a lightweight bubble and break the run. An 8px gap separates distinct
  /// blocks (run↔text, text↔text).
  List<Widget> _buildChildren(BuildContext context, List<String> contents) {
    final rows = <Widget>[];
    int i = 0;
    var firstBlock = true;
    while (i < contents.length) {
      if (_isToolUseContent(contents[i])) {
        int j = i;
        while (j < contents.length && _isToolUseContent(contents[j])) {
          j++;
        }
        for (int k = i; k < j; k++) {
          rows.add(buildCollapsibleToolRow(
            context,
            contents[k],
            agentTypeName: widget.agentTypeName,
            // The first block, when it's a tool run, fuses into the header
            // above (no top border on its first row); every later run is a
            // standalone box that rounds its own top.
            toolUseIsFirst: k == i && !firstBlock,
            toolUseIsLast: k == j - 1,
            expanded: _expandedChildren.contains(k),
            onToggle: () => _toggleChild(k),
          ));
        }
        i = j;
      } else {
        rows.add(_buildTextBubble(context, contents[i]));
        i++;
      }
      firstBlock = false;
      if (i < contents.length) rows.add(const SizedBox(height: 8.0));
    }
    return rows;
  }

  /// Same tool-use content detection `buildMarkdownText` uses to route into the
  /// bordered tool-row format.
  bool _isToolUseContent(String content) {
    final t = content.trim();
    return t.startsWith('Using tool:') ||
        t.startsWith('🔧 Using tool:') ||
        t.startsWith('**Exec:**') ||
        (content.contains('✏️ Applying patch to') &&
            content.contains('file (+'));
  }

  /// A plain-text (non-tool) child in a lightweight bubble, distinguishing it
  /// from the bordered tool rows around it.
  Widget _buildTextBubble(BuildContext context, String content) {
    final markdown = buildMarkdownText(
      context,
      content,
      false,
      onSendMessage: (_) {},
      agentTypeName: widget.agentTypeName,
      filterProjectRoot: widget.filterProjectRoot,
    );
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 10.0),
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).secondaryBackground,
        borderRadius: const BorderRadius.all(Radius.circular(16.0)),
      ),
      child: markdown,
    );
  }
}
