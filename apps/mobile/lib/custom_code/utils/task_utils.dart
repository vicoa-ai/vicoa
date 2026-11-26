import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_theme.dart';

/// Helpers for the Tasks feature. Tasks, projects and labels are kept as
/// dynamic `Map<String, dynamic>` (the same convention machines and agent
/// instances follow) and accessed through the string-keyed getters below. The
/// wire shapes mirror the backend's `TaskResponse` / `ProjectResponse` /
/// `TaskLabelResponse`.

/// Status vocabulary, ordered as the list reads top-to-bottom. Mirrors the web
/// dashboard's STATUS_ORDER: the open states first, the two closed ones last.
const List<String> kTaskStatusOrder = [
  'backlog',
  'todo',
  'in_progress',
  'in_review',
  'blocked',
  'done',
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

/// The rendered "VIC-42", or null when the task has none: unfiled tasks and
/// tasks whose project has no key yet carry no identifier.
String? taskIdentifier(dynamic t) {
  final s = (t is Map ? t['identifier'] : null)?.toString();
  return (s == null || s.isEmpty) ? null : s;
}

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

String? _nonEmpty(dynamic v) {
  final s = v?.toString();
  return (s == null || s.isEmpty) ? null : s;
}

Map<String, dynamic>? _map(dynamic v) => v is Map ? Map<String, dynamic>.from(v) : null;

List<dynamic> _list(dynamic v) => v is List ? v : const [];

/// Who owns the work: a `PrincipalResponse` map (a user or an agent), or null
/// when the task is unassigned.
Map<String, dynamic>? taskAssignee(dynamic t) => _map(t is Map ? t['assignee'] : null);

/// `user` | `agent`, or null when unassigned.
String? taskAssigneeType(dynamic t) => _nonEmpty(t is Map ? t['assignee_type'] : null);

String? taskAssigneeId(dynamic t) => _nonEmpty(t is Map ? t['assignee_id'] : null);

/// The questions an agent asked on the task that still wait, oldest first:
/// each `{comment_id, addressee, asked_by, asked_at}` (`TaskQuestionResponse`).
List<dynamic> taskOpenQuestions(dynamic t) => _list(t is Map ? t['open_questions'] : null);

/// The task's newest dispatch to an agent (`TaskDispatchSummary`), or null
/// when no agent was ever asked to act on it.
Map<String, dynamic>? taskDispatch(dynamic t) => _map(t is Map ? t['dispatch'] : null);

/// The session the task was created in (`vicoa task create` inside one).
String? taskCreatedInInstanceId(dynamic t) => _nonEmpty(t is Map ? t['created_in_instance_id'] : null);

// --- Standing on a task's board ---------------------------------------------

/// Project roles, least to most.
const List<String> kProjectRoleOrder = ['viewer', 'commenter', 'editor', 'admin', 'owner'];

/// The viewer's role on [task]'s board: `owner` for an unfiled task (only its
/// owner can see it), else [project]'s `role`. Null when the role is unknown:
/// the project is missing from the list (a failed fetch, or archived).
String? taskViewerRole(dynamic task, dynamic project) {
  if (taskProjectId(task) == null) return 'owner';
  return _nonEmpty(project is Map ? project['role'] : null);
}

/// Whether [role] is at least [minimum]. An unknown role passes: the server
/// enforces the same floors and its refusal reads as a failed action, which
/// beats hiding the composer whenever the project list failed to load. A
/// KNOWN low role (a viewer on a shared board) is what hides controls.
bool projectRoleAtLeast(String? role, String minimum) {
  if (role == null) return true;
  final have = kProjectRoleOrder.indexOf(role);
  return have >= 0 && have >= kProjectRoleOrder.indexOf(minimum);
}

// --- Principal accessors (`PrincipalResponse`) -----------------------------
//
// A user, a team or an agent, in the one shape every task surface renders:
// assignees, comment authors, activity actors, reactors, question addressees.
// Never carries an email.

/// `user` | `team` | `agent` | `system`.
String principalType(dynamic p) => (p is Map ? p['type'] : null)?.toString() ?? 'user';

String? principalId(dynamic p) => _nonEmpty(p is Map ? p['id'] : null);

/// The display name, trimmed, or null when the principal has none.
String? principalName(dynamic p) => _nonEmpty((p is Map ? p['name'] : null)?.toString().trim());

String? principalAvatarImageUri(dynamic p) => _nonEmpty(p is Map ? p['avatar_image_uri'] : null);

String? principalEmoji(dynamic p) => _nonEmpty(p is Map ? p['emoji'] : null);

String? principalUpdatedAt(dynamic p) => _nonEmpty(p is Map ? p['updated_at'] : null);

// --- Comment accessors (`TaskCommentResponse`) -----------------------------

String commentId(dynamic c) => (c is Map ? c['id'] : null)?.toString() ?? '';

/// The root this answers, or null when the comment is a root. Threads are one
/// level deep, so this always names a root.
String? commentParentId(dynamic c) => _nonEmpty(c is Map ? c['parent_comment_id'] : null);

Map<String, dynamic>? commentAuthor(dynamic c) => _map(c is Map ? c['author'] : null);

bool commentIsDeleted(dynamic c) => _nonEmpty(c is Map ? c['deleted_at'] : null) != null;

/// The text, or null once soft-deleted (the row stays as a tombstone).
String? commentBody(dynamic c) {
  if (commentIsDeleted(c)) return null;
  return (c is Map ? c['body'] : null)?.toString();
}

String commentCreatedAt(dynamic c) => (c is Map ? c['created_at'] : null)?.toString() ?? '';

String? commentEditedAt(dynamic c) => _nonEmpty(c is Map ? c['edited_at'] : null);

/// The session the comment was posted from, if any.
String? commentAgentInstanceId(dynamic c) => _nonEmpty(c is Map ? c['agent_instance_id'] : null);

List<dynamic> commentReactions(dynamic c) => _list(c is Map ? c['reactions'] : null);

/// The question the comment asks (`{addressee, closed_at, closed_reason}`), or
/// null when it is not one.
Map<String, dynamic>? commentQuestion(dynamic c) => _map(c is Map ? c['question'] : null);

// --- Activity accessors (`TaskActivityResponse`) ---------------------------

String activityId(dynamic a) => (a is Map ? a['id'] : null)?.toString() ?? '';

String activityAction(dynamic a) => (a is Map ? a['action'] : null)?.toString() ?? '';

Map<String, dynamic> activityDetails(dynamic a) => _map(a is Map ? a['details'] : null) ?? const {};

/// Who made the change, or null for an unattributed background change.
Map<String, dynamic>? activityActor(dynamic a) => _map(a is Map ? a['actor'] : null);

String activityCreatedAt(dynamic a) => (a is Map ? a['created_at'] : null)?.toString() ?? '';

/// The session the change came from (`details.agent_instance_id`), if any.
String? activityAgentInstanceId(dynamic a) => _nonEmpty(activityDetails(a)['agent_instance_id']);

// --- Reaction accessors (`TaskReactionSummary`) ----------------------------

String reactionEmoji(dynamic r) => (r is Map ? r['emoji'] : null)?.toString() ?? '';

int reactionCount(dynamic r) {
  final n = r is Map ? r['count'] : null;
  return n is num ? n.toInt() : 0;
}

/// Whether the signed-in user is one of the reactors: the pill's filled state.
bool reactionReacted(dynamic r) => r is Map && r['reacted'] == true;

/// Who reacted, oldest first, capped by the server; [reactionCount] is the
/// true total.
List<dynamic> reactionReactors(dynamic r) => _list(r is Map ? r['reactors'] : null);

final RegExp _space = RegExp(r'\s');

/// Whether [value] is plausibly one emoji, by the server's rule
/// (`shared/database/reactions.py` `is_emoji`): short, no ASCII letters,
/// digits or whitespace, and at least one character past Latin-1. Joiners and
/// variation selectors are allowed inside. Structural rather than a list, so
/// any emoji the keyboard offers passes.
bool isReactionEmoji(String value) {
  final runes = value.runes.toList();
  if (runes.isEmpty || runes.length > 16) return false;
  var exotic = false;
  for (final r in runes) {
    if (r == 0x200D || r == 0xFE0F || r == 0xFE0E) continue;
    final ch = String.fromCharCode(r);
    if (r < 0x80 && RegExp(r'[A-Za-z0-9]').hasMatch(ch)) return false;
    if (_space.hasMatch(ch)) return false;
    if (r > 0xFF) exotic = true;
  }
  return exotic;
}

// --- Timeline payload (`TaskTimelineResponse`) -----------------------------

List<dynamic> timelineComments(dynamic tl) => _list(tl is Map ? tl['comments'] : null);

List<dynamic> timelineActivity(dynamic tl) => _list(tl is Map ? tl['activity'] : null);

/// Reactions on the task itself, not on any comment.
List<dynamic> timelineReactions(dynamic tl) => _list(tl is Map ? tl['reactions'] : null);

/// The sessions the task and its rows name that the viewer may open: each
/// `{id, name, agent_type_name}`. A session missing here is one they can't
/// open, so it gets no link and no title.
List<dynamic> timelineSessionRefs(dynamic tl) => _list(tl is Map ? tl['sessions'] : null);

/// Who can see the task: whom a comment can `@`mention.
List<dynamic> timelinePeople(dynamic tl) => _list(tl is Map ? tl['people'] : null);

// --- Session rows (`TaskSessionResponse`) ----------------------------------

/// How a session relates to the task, strongest first: `linked`, `created`,
/// `updated`, `commented`, `referenced`.
List<String> sessionTaskRelations(dynamic s) =>
    _list(s is Map ? s['task_relations'] : null).map((r) => r.toString()).toList();

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

/// Project-filter value for "unfiled tasks only" (`project_id` null). A null
/// filter is "all projects"; anything else is a project id. Mirrors the web's
/// `NO_PROJECT_FILTER`.
const String kNoProjectFilter = 'none';

/// The project's emoji glyph (`icon` field), or null → the caller falls back
/// to a folder glyph (see `TaskProjectIcon`).
String? projectIcon(dynamic p) {
  final s = (p is Map ? p['icon'] : null)?.toString();
  return (s == null || s.isEmpty) ? null : s;
}

/// Backend-relative URL of the project's uploaded / git-seeded image icon, or
/// null. Wins over the emoji when set (the web's fallback order).
String? projectIconImageUri(dynamic p) {
  final s = (p is Map ? p['icon_image_uri'] : null)?.toString();
  return (s == null || s.isEmpty) ? null : s;
}

/// `updated_at` as sent — the cache-buster for the image icon, whose URL is
/// stable across replacements.
String? projectUpdatedAt(dynamic p) =>
    (p is Map ? p['updated_at'] : null)?.toString();

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

/// One row of the flattened tasks list: a status section header, or a task
/// card under it.
class TaskListRow {
  const TaskListRow.header(this.status, this.count, this.collapsed)
      : task = null,
        isHeader = true;
  const TaskListRow.task(this.status, this.task)
      : count = 0,
        collapsed = false,
        isHeader = false;

  final bool isHeader;
  final String status;

  /// Header only: how many tasks the section holds, and whether it is folded.
  final int count;
  final bool collapsed;

  /// Task row only.
  final dynamic task;
}

/// The list top-to-bottom: for each non-empty status in [kTaskStatusOrder], its
/// header, then its tasks unless the section is in [collapsed]. One flat list
/// so the page can build rows lazily and scroll to a row by index.
List<TaskListRow> flattenTaskRows(
  Map<String, List<dynamic>> grouped,
  Set<String> collapsed,
) {
  final rows = <TaskListRow>[];
  for (final status in kTaskStatusOrder) {
    final items = grouped[status] ?? const [];
    if (items.isEmpty) continue;
    final folded = collapsed.contains(status);
    rows.add(TaskListRow.header(status, items.length, folded));
    if (folded) continue;
    for (final t in items) {
      rows.add(TaskListRow.task(status, t));
    }
  }
  return rows;
}

/// Index of the row showing task [id], or -1 when it isn't in [rows] (filtered
/// out, or its section is folded).
int indexOfTaskRow(List<TaskListRow> rows, String id) =>
    rows.indexWhere((r) => !r.isHeader && taskId(r.task) == id);

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
