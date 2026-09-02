// Leading icon shown in front of a tool-use row / collapsed tool-use group /
// sub-agent group header. Mirrors vicoa-web's per-tool icon table
// (`iconForToolName` + `TOOL_RANK` in `components/dashboard/tool-use-display.tsx`):
// every tool gets a generic, single-color glyph — there are no per-tool
// "rounded logos" on web either. The one exception is the Task/Agent tool
// (and its sub-agent group): when the underlying agent type is known, it
// shows that agent's actual rounded brand logo (`AgentTypeIconWidget`)
// instead of a generic robot glyph — that logo already exists in the app for
// agent branding and is threaded through as `agentTypeName` everywhere a
// tool row is built, so it's "available" exactly where web has nothing to
// show.

import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/components/agent_type_icon/agent_type_icon_widget.dart';

String _normalizeToolName(String name) =>
    name.replaceAll(RegExp(r'[\s_]'), '').toLowerCase();

/// Whether [toolName] is the Task/Agent tool (or a sub-agent group's synthetic
/// name) — the one case where a rounded agent-brand logo can stand in for the
/// generic icon.
bool isAgentToolName(String toolName) {
  final key = _normalizeToolName(toolName);
  return key == 'task' || key.contains('agent');
}

/// Generic glyph for [toolName], used whenever no rounded logo applies.
/// Mirrors `iconForToolName` on web (lucide-react names in parens).
IconData iconForToolName(String toolName) {
  final key = _normalizeToolName(toolName);
  if (key == 'bash' || key == 'exec') return Icons.terminal; // Terminal
  if (key == 'edit' ||
      key == 'edited' ||
      key == 'write' ||
      key == 'multiedit') {
    return Icons.edit_outlined; // Pencil
  }
  if (key == 'read') return Icons.remove_red_eye_outlined; // Eye
  if (key == 'askuserquestion') return Icons.help_outline; // MessageCircleQuestion
  if (key == 'thinking') return Icons.lightbulb_outline; // Lightbulb (reasoning)
  if (isAgentToolName(toolName)) return Icons.smart_toy_outlined; // Bot
  if (key == 'search' || key == 'grep' || key == 'glob') return Icons.search; // Search
  if (key == 'list') return Icons.list; // List
  if (key == 'todos' || key == 'todowrite') return Icons.checklist; // ListTodo
  if (key == 'webfetch' || key == 'websearch' || key == 'fetch') {
    return Icons.public; // Globe
  }
  return Icons.build_outlined; // Wrench (catch-all)
}

/// Priority used to pick which tool "represents" a collapsed run of several
/// tools for its group-header icon — mirrors web's `TOOL_RANK`. Lower wins:
/// Task/Agent/AskUserQuestion, then edits, then reads, then searches, then
/// shell commands, then lists, then todos. Unranked tools sort last.
const Map<String, int> _toolIconRank = {
  'task': 0, 'agent': 0, 'subagent': 0, 'askuserquestion': 0,
  'edit': 1, 'edited': 1, 'write': 1, 'multiedit': 1,
  'read': 2,
  'search': 3, 'grep': 3, 'glob': 3,
  'bash': 4, 'exec': 4,
  'list': 5,
  'todos': 6, 'todowrite': 6,
};

/// Picks which tool name in [toolNames] should decide a collapsed run's icon.
String representativeToolName(Iterable<String> toolNames) {
  String? best;
  var bestRank = 1 << 30;
  for (final name in toolNames) {
    if (name.isEmpty) continue;
    final rank = _toolIconRank[_normalizeToolName(name)] ?? (1 << 29);
    if (rank < bestRank) {
      bestRank = rank;
      best = name;
    }
  }
  return best ?? '';
}

/// Leading icon for a tool-use row or its collapsed group header. Rounded
/// agent-brand logo for the Task/Agent tool when [agentTypeName] resolves to
/// one; a generic glyph (`iconForToolName`) otherwise.
class ToolIcon extends StatelessWidget {
  const ToolIcon({
    super.key,
    required this.toolName,
    this.agentTypeName,
    this.size = 15.0,
  });

  final String toolName;
  final String? agentTypeName;
  final double size;

  @override
  Widget build(BuildContext context) {
    if (isAgentToolName(toolName) && agentTypeHasLogo(agentTypeName)) {
      return AgentTypeIconWidget(agentTypeName: agentTypeName, size: size);
    }
    return Icon(
      iconForToolName(toolName),
      size: size,
      color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.7),
    );
  }
}
