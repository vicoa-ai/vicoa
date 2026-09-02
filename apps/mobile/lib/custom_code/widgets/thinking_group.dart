// Collapsed model-reasoning ("thinking") card for the agent chat. A reasoning
// message carries `message_metadata.thinking = { source }` (see
// `src/integrations/headless/thinking.py`); the reasoning text rides in the
// message content. This renders it behind a "Thinking" collapsible header
// mirroring `buildToolGroupHeader` (like `SubagentGroup`), so reasoning is
// available without flooding the transcript. Collapsed by default.

import 'package:flutter/material.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/custom_code/widgets/markdown_text_builder.dart'
    show buildMarkdownText, buildToolGroupHeader;

/// Whether [message] is tagged as model reasoning
/// (`message_metadata.thinking`). Sub-agent-tagged reasoning is intentionally
/// NOT surfaced as a standalone thinking card — it renders inside its
/// `SubagentGroup` — so callers pair this with a `!isSubagentMessage` guard.
bool isThinkingMessage(dynamic message) {
  if (message is! Map) return false;
  final metadata = message['message_metadata'];
  if (metadata is! Map) return false;
  return metadata['thinking'] is Map;
}

/// Strips Codex's leading "Reasoning:" label (kept in the message content so
/// pre-card clients still show it inline) — the card header already reads
/// "Thinking", so the prefix is redundant here. The optional "🧠 " covers
/// older daemons that still emit the emoji label.
String thinkingDisplayBody(String content) {
  final stripped = content
      .replaceFirst(RegExp(r'^\s*(?:🧠\s*)?Reasoning:\s*\n?'), '')
      .trim();
  return stripped.isEmpty ? content.trim() : stripped;
}

/// One model-reasoning message, collapsed behind a "Thinking" header that
/// mirrors [buildToolGroupHeader]'s bordered style (same chrome as
/// [SubagentGroup]). Expanded, the reasoning renders as a lightweight bubble.
class ThinkingGroup extends StatefulWidget {
  const ThinkingGroup({
    super.key,
    required this.content,
    required this.expanded,
    required this.onToggle,
    this.onBeforeToggle,
    this.agentTypeName,
    this.filterProjectRoot,
  });

  /// The reasoning text (raw message content, prefix stripped for display).
  final String content;
  final bool expanded;
  final VoidCallback onToggle;

  /// Called immediately before expand/collapse, mirroring
  /// [SubagentGroup.onBeforeToggle] — lets the host pin scroll position so the
  /// tapped line doesn't shift as content grows.
  final VoidCallback? onBeforeToggle;
  final String? agentTypeName;
  final String Function(String content)? filterProjectRoot;

  @override
  State<ThinkingGroup> createState() => _ThinkingGroupState();
}

class _ThinkingGroupState extends State<ThinkingGroup> {
  void _toggle() {
    widget.onBeforeToggle?.call();
    widget.onToggle();
  }

  @override
  Widget build(BuildContext context) {
    final body = thinkingDisplayBody(widget.content);
    if (body.isEmpty) return const SizedBox.shrink();

    if (!widget.expanded) {
      return buildToolGroupHeader(
        context,
        'Thinking',
        isLast: true,
        expanded: false,
        onToggle: _toggle,
        iconToolName: 'Thinking',
        agentTypeName: widget.agentTypeName,
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildToolGroupHeader(
          context,
          'Thinking',
          isLast: true,
          expanded: true,
          onToggle: _toggle,
          iconToolName: 'Thinking',
          agentTypeName: widget.agentTypeName,
        ),
        const SizedBox(height: 8.0),
        _buildBody(context, body),
      ],
    );
  }

  Widget _buildBody(BuildContext context, String content) {
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
