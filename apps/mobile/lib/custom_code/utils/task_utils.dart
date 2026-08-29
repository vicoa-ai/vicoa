import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_theme.dart';

/// Helpers for the Tasks feature. Tasks, projects and labels are kept as
/// dynamic `Map<String, dynamic>` (the same convention machines and agent
/// instances follow) and accessed through the string-keyed getters below. The
/// wire shapes mirror the backend's `TaskResponse` / `ProjectResponse` /
/// `TaskLabelResponse`.

/// Status vocabulary, ordered as the list reads top-to-bottom. Mirrors the web
/// dashboard's STATUS_ORDER: the main lifecycle first, the two side states last.
const List<String> kTaskStatusOrder = [
  'backlog',
  'todo',
  'in_progress',
  'in_review',
  'done',
  'blocked',
  'cancelled',
];

/// Priority vocabulary, most-urgent first.
const List<String> kTaskPriorityOrder = [
  'urgent',
  'high',
  'medium',
  'low',
  'none',
];

/// Closed states — rendered muted / struck through, like the web board.
const List<String> kTaskClosedStatuses = ['done', 'cancelled'];

// --- Task field accessors ---------------------------------------------------

String taskId(dynamic t) => (t is Map ? t['id'] : null)?.toString() ?? '';

String taskTitle(dynamic t) => (t is Map ? t['title'] : null)?.toString() ?? '';

String taskStatus(dynamic t) =>
    (t is Map ? t['status'] : null)?.toString() ?? 'backlog';

String taskPriority(dynamic t) =>
    (t is Map ? t['priority'] : null)?.toString() ?? 'none';

String? taskDescription(dynamic t) {
  final s = (t is Map ? t['description'] : null)?.toString();
  return (s == null || s.isEmpty) ? null : s;
}

String? taskProjectId(dynamic t) =>
    (t is Map ? t['project_id'] : null)?.toString();

String? taskParentId(dynamic t) =>
    (t is Map ? t['parent_task_id'] : null)?.toString();

List<dynamic> taskLabels(dynamic t) {
  final l = t is Map ? t['labels'] : null;
  return l is List ? l : const [];
}

double taskPosition(dynamic t) {
  final p = t is Map ? t['position'] : null;
  return p is num ? p.toDouble() : 0.0;
}

bool taskIsClosed(dynamic t) => kTaskClosedStatuses.contains(taskStatus(t));

/// The first prompt seeded into a session started from a task — the title, the
/// description as context when present, and any [subtasks] rendered as a
/// checklist. Mirrors the web's composeTaskPrompt.
String composeTaskPrompt(dynamic t, {List<dynamic> subtasks = const []}) {
  final title = taskTitle(t);
  final desc = taskDescription(t);
  final buf = StringBuffer(title);
  if (desc != null) buf.write('\n\n$desc');
  if (subtasks.isNotEmpty) {
    buf.write('\n\nSub-tasks:');
    for (final s in subtasks) {
      buf.write('\n- [ ] ${taskTitle(s)}');
    }
  }
  return buf.toString();
}

// --- Label / project accessors ---------------------------------------------

String labelId(dynamic l) => (l is Map ? l['id'] : null)?.toString() ?? '';

String labelName(dynamic l) => (l is Map ? l['name'] : null)?.toString() ?? '';

String labelColorHex(dynamic l) =>
    (l is Map ? l['color'] : null)?.toString() ?? '#8A8F98';

String projectId(dynamic p) => (p is Map ? p['id'] : null)?.toString() ?? '';

String projectName(dynamic p) => (p is Map ? p['name'] : null)?.toString() ?? '';

String? projectColorHex(dynamic p) =>
    (p is Map ? p['color'] : null)?.toString();

/// The project's emoji glyph (`icon` field), or null → caller falls back to an
/// inbox/folder line icon.
String? projectIcon(dynamic p) {
  final s = (p is Map ? p['icon'] : null)?.toString();
  return (s == null || s.isEmpty) ? null : s;
}

bool projectIsInbox(dynamic p) => (p is Map ? p['is_inbox'] : null) == true;

// --- Ordering & grouping ----------------------------------------------------

/// Fractional `position` ascending, then `created_at` — the same order the
/// backend list endpoint returns.
int compareTasks(dynamic a, dynamic b) {
  final pa = taskPosition(a), pb = taskPosition(b);
  if (pa != pb) return pa.compareTo(pb);
  final ca = (a is Map ? a['created_at'] : null)?.toString() ?? '';
  final cb = (b is Map ? b['created_at'] : null)?.toString() ?? '';
  return ca.compareTo(cb);
}

/// Group into the canonical status order. Every status gets a (possibly empty)
/// bucket so the UI can decide whether to show empty sections.
Map<String, List<dynamic>> groupTasksByStatus(List<dynamic> tasks) {
  final map = <String, List<dynamic>>{for (final s in kTaskStatusOrder) s: []};
  for (final t in tasks) {
    (map[taskStatus(t)] ??= []).add(t);
  }
  for (final entry in map.entries) {
    entry.value.sort(compareTasks);
  }
  return map;
}

// --- Colors -----------------------------------------------------------------

/// Parse a `#rrggbb` (or `#aarrggbb`) hex string into a [Color].
Color hexToColor(String? hex, {Color fallback = const Color(0xFF8A8F98)}) {
  if (hex == null) return fallback;
  var h = hex.replaceAll('#', '').trim();
  if (h.length == 6) h = 'FF$h';
  final v = int.tryParse(h, radix: 16);
  return v == null ? fallback : Color(v);
}

/// Status accent, matching the web dashboard's Tailwind tokens exactly
/// (task-ui.tsx STATUS_CONFIG.iconColor). Note done is BLUE and in_review is
/// GREEN; backlog/todo/cancelled are muted grey.
Color taskStatusColor(String status, FlutterFlowTheme theme) {
  switch (status) {
    case 'in_progress':
      return const Color(0xFFEAB308); // yellow-500
    case 'in_review':
      return const Color(0xFF22C55E); // green-500
    case 'done':
      return const Color(0xFF3B82F6); // blue-500
    case 'blocked':
      return const Color(0xFFEF4444); // red-500
    case 'backlog':
    case 'todo':
    case 'cancelled':
    default:
      return theme.secondaryText; // muted-foreground
  }
}

/// Priority accent, matching the web (PRIORITY_CONFIG.color).
Color taskPriorityColor(String priority, FlutterFlowTheme theme) {
  switch (priority) {
    case 'urgent':
      return const Color(0xFFEF4444); // red-500
    case 'high':
    case 'medium':
      return const Color(0xFFEAB308); // yellow-500
    case 'low':
      return const Color(0xFF3B82F6); // blue-500
    default:
      return theme.secondaryText; // none
  }
}

/// Filled bar count (of 4) for the priority glyph, matching the web:
/// urgent=4, high=3, medium=2, low=1, none=0 (rendered as a dash).
int taskPriorityBars(String priority) {
  switch (priority) {
    case 'urgent':
      return 4;
    case 'high':
      return 3;
    case 'medium':
      return 2;
    case 'low':
      return 1;
    default:
      return 0;
  }
}
