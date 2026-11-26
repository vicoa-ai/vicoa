/// The task-detail timeline's shape: comments, generated activity and agent
/// sessions folded into one chronological stream. A line-for-line port of the
/// web's `buildThreads` / `buildEntries` (apps/web/app/dashboard/tasks/
/// [taskId]/task-timeline.tsx), so a task reads the same on both clients. The
/// layout rules behind it are written at the top of that file and of
/// `task_timeline_view.dart`.
library;

import 'package:collection/collection.dart' show mergeSort;

import 'task_utils.dart';

/// A root comment and the replies hanging off it. Never deeper than this:
/// the server re-points a reply to a reply at its root.
class TaskThread {
  TaskThread(this.root) : replies = [];

  final dynamic root;
  final List<dynamic> replies;

  /// Root first, then the replies in order.
  List<dynamic> get comments => [root, ...replies];
}

/// One row of the stream.
sealed class TimelineEntry {
  const TimelineEntry(this.id, this.at);

  /// Stable key for the row's widget.
  final String id;

  /// What it sorts by: a thread's ROOT time, an activity run's first row, a
  /// session's start.
  final String at;
}

/// A thread: one card, its replies and the way to answer it.
class ThreadEntry extends TimelineEntry {
  ThreadEntry(this.thread) : super('c-${commentId(thread.root)}', commentCreatedAt(thread.root));

  final TaskThread thread;
}

/// Consecutive activity rows, folded into one line when there are several.
class ActivityRunEntry extends TimelineEntry {
  ActivityRunEntry(dynamic first)
      : rows = [first],
        super('a-${activityId(first)}', activityCreatedAt(first));

  final List<dynamic> rows;
}

/// A session filed under the task, carrying the status hops it caused.
class SessionEntry extends TimelineEntry {
  SessionEntry(this.session, this.absorbed, String at) : super('s-${session is Map ? session['id'] : ''}', at);

  final dynamic session;
  final List<dynamic> absorbed;
}

final DateTime _epoch = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

/// Sort key for a server timestamp. Parsed rather than compared as text: the
/// strings all come from one server today, but a mix of `Z` and `+00:00`
/// would sort wrong as text and nobody would notice.
DateTime _time(String iso) => DateTime.tryParse(iso) ?? _epoch;

int _byTime(String a, String b) => _time(a).compareTo(_time(b));

/// Group a flat comment list into one-level threads, oldest root first.
///
/// Built from `parent_comment_id`, never from arrival order: the server sends
/// the list threaded today, but a client that silently depends on that breaks
/// in a way nobody notices until a reply renders as a root. A reply whose root
/// isn't in the list is promoted to a root, because a comment that exists must
/// be readable. A soft-deleted root stays (as a tombstone) and keeps anchoring
/// its replies.
List<TaskThread> buildThreads(List<dynamic> comments) {
  final threads = <String, TaskThread>{};
  final order = <String>[];
  final orphans = <dynamic>[];

  for (final c in comments) {
    if (commentParentId(c) == null) {
      threads[commentId(c)] = TaskThread(c);
      order.add(commentId(c));
    }
  }
  for (final c in comments) {
    final parent = commentParentId(c);
    if (parent == null) continue;
    final thread = threads[parent];
    if (thread != null) {
      thread.replies.add(c);
    } else {
      orphans.add(c);
    }
  }
  for (final orphan in orphans) {
    threads[commentId(orphan)] = TaskThread(orphan);
    order.add(commentId(orphan));
  }

  // mergeSort is stable: two comments in the same instant keep their order.
  final out = order.map((id) => threads[id]!).toList();
  mergeSort<TaskThread>(out, compare: (a, b) => _byTime(commentCreatedAt(a.root), commentCreatedAt(b.root)));
  for (final thread in out) {
    mergeSort<dynamic>(thread.replies, compare: (a, b) => _byTime(commentCreatedAt(a), commentCreatedAt(b)));
  }
  return out;
}

/// Fold comments, activity and the task's linked sessions into one stream.
///
/// A session is placed at its start and swallows the status changes it caused
/// (`details.agent_instance_id`), so a task that ran three sessions is three
/// cards rather than nine automated lines. Only churn folds: a change the
/// session made on purpose (`details.direct`, e.g. `vicoa task update`) and
/// anything that isn't a status change (a `referenced` row) stay in the
/// stream. A row naming a session the task no longer links to stays too:
/// bucketed against a card that never renders, a real change would vanish.
/// Whatever is left merges by kind: consecutive activity becomes one run,
/// while every thread keeps its own card.
List<TimelineEntry> buildTimelineEntries(
  List<dynamic> comments,
  List<dynamic> activity,
  List<dynamic> sessions,
) {
  final threads = buildThreads(comments);
  final linked = {for (final s in sessions) if (s is Map) s['id']?.toString()};
  final bySession = <String, List<dynamic>>{};
  final loose = <dynamic>[];
  for (final row in activity) {
    final instanceId = activityAgentInstanceId(row);
    final churn = activityAction(row) == 'status_changed' && activityDetails(row)['direct'] != true;
    if (instanceId != null && linked.contains(instanceId) && churn) {
      (bySession[instanceId] ??= []).add(row);
    } else {
      loose.add(row);
    }
  }

  final raw = <({String at, Object item})>[
    for (final t in threads) (at: commentCreatedAt(t.root), item: t),
    for (final row in loose) (at: activityCreatedAt(row), item: _ActivityRow(row)),
    // A session with no start time sorts to the top rather than being
    // dropped; it is still a real link on the task.
    for (final s in sessions)
      if (s is Map) (at: s['started_at']?.toString() ?? _epoch.toIso8601String(), item: _SessionRow(s)),
  ];
  mergeSort<({String at, Object item})>(raw, compare: (a, b) => _byTime(a.at, b.at));

  final entries = <TimelineEntry>[];
  for (final r in raw) {
    final item = r.item;
    final last = entries.isEmpty ? null : entries.last;
    if (item is TaskThread) {
      // Never merged with the thread before it: each thread owns its card
      // because each thread owns its reply.
      entries.add(ThreadEntry(item));
    } else if (item is _ActivityRow) {
      if (last is ActivityRunEntry) {
        last.rows.add(item.row);
      } else {
        entries.add(ActivityRunEntry(item.row));
      }
    } else if (item is _SessionRow) {
      final id = item.session['id']?.toString() ?? '';
      entries.add(SessionEntry(item.session, bySession[id] ?? const [], r.at));
    }
  }
  return entries;
}

class _ActivityRow {
  const _ActivityRow(this.row);
  final dynamic row;
}

class _SessionRow {
  const _SessionRow(this.session);
  final Map session;
}

/// The sessions filed under the task (`task_relations` has `linked`): the
/// timeline's session cards. The rest of the related list only shows in the
/// Sessions section.
List<dynamic> linkedTaskSessions(List<dynamic> related) =>
    related.where((s) => sessionTaskRelations(s).contains('linked')).toList();

/// id → `{id, name, agent_type_name}` for the sessions a row may name.
Map<String, Map<String, dynamic>> sessionRefsById(List<dynamic> refs) => {
      for (final r in refs)
        if (r is Map && r['id'] != null) r['id'].toString(): Map<String, dynamic>.from(r),
    };
