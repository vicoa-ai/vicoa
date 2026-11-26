import 'dart:async';

import 'package:flutter/foundation.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/task_mentions.dart';
import '/custom_code/utils/task_questions.dart';
import '/custom_code/utils/task_timeline.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import 'task_timeline_text.dart';

/// How often an open sheet reloads: slow on purpose. The point is to catch an
/// agent's comment landing while the sheet sits open, not to imitate realtime;
/// coming back to the app reloads at once. The web polls at the same rate.
const Duration kTaskDetailPollInterval = Duration(seconds: 30);

/// The data behind the task detail sheet: one task, its timeline (comments,
/// activity, task reactions, the sessions its rows name, the people who can
/// see it), every session related to it, and the viewer's agents for the `@`
/// picker. Plus the writes the sheet makes. The mobile twin of the web's
/// `use-task-detail.ts`.
///
/// No WebSocket channel for tasks, by decision (collaboration plan §9): the
/// sheet reloads when the app comes back to the foreground and on a slow poll
/// while it is open ([kTaskDetailPollInterval]). Every comment and reaction
/// write answers with the whole timeline, which replaces local state as is.
class TaskDetailModel {
  TaskDetailModel({required this.task, required this.project});

  /// The task as last read: the list's copy until the first load answers.
  dynamic task;

  /// The task's project from the list (its `role` is the viewer's standing).
  final dynamic project;

  List<dynamic> comments = const [];
  List<dynamic> activity = const [];
  List<dynamic> taskReactions = const [];
  List<dynamic> people = const [];

  /// Every session the task's record names, most recently active first.
  List<dynamic> relatedSessions = const [];

  /// id → `{id, name, agent_type_name}` for the sessions rows may name.
  Map<String, Map<String, dynamic>> sessionRefs = const {};

  /// The viewer's saved agents: whom an `@` can mention.
  List<dynamic> agentProfiles = const [];
  TaskViewer? viewer;

  /// The stream, rebuilt whenever the timeline or the sessions change.
  List<TimelineEntry> entries = const [];

  /// The first timeline load has answered (successfully or not).
  bool timelineLoaded = false;

  /// The last timeline load failed and nothing is on screen yet.
  bool timelineFailed = false;

  VoidCallback? _notify;
  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  bool _disposed = false;
  bool _loading = false;
  bool _referenceLoaded = false;

  /// Bumped by every write that answers with a timeline. A load that started
  /// before the write would otherwise land after it and put the pre-write
  /// timeline (without the comment just posted) back on screen.
  int _writes = 0;

  String get taskId => tutils.taskId(task);

  /// The sessions filed under the task: the timeline's session cards.
  List<dynamic> get linkedSessions => linkedTaskSessions(relatedSessions);

  String? get _role => tutils.taskViewerRole(task, project);
  bool get canComment => tutils.projectRoleAtLeast(_role, 'commenter');

  /// Agents with an open question to the viewer: whom a top-level comment
  /// answers. Read off the thread once it loads, off the task before that.
  List<WaitingAgent> get askers => timelineLoaded ? askersFromComments(comments, viewer?.id) : askersFromTask(task, viewer?.id);

  /// Where the bottom box's comment goes when it starts a new thread.
  WakeContext get topLevelWake => WakeContext(
        inThread: false,
        assigneeAgentId: tutils.taskAssigneeType(task) == 'agent' ? tutils.taskAssigneeId(task) : null,
        taskClosed: tutils.taskIsClosed(task),
        askers: askers,
      );

  /// Where a reply in [thread] goes.
  WakeContext replyWake(TaskThread thread) => WakeContext(inThread: true, threadAgentId: threadAgentId(thread), taskClosed: tutils.taskIsClosed(task), askers: askers);

  /// The agents a comment can actually start: the viewer's own (a team's
  /// agent can't be mentioned into a run from here, as on the web).
  List<dynamic> get mentionableAgents => agentProfiles.where((a) => a is Map && a['is_archived'] != true && (a['team_id'] == null || a['team_id'].toString().isEmpty)).toList();

  /// Agent names by lower-cased id, for the wake hint: the viewer's agents
  /// plus the askers (an agent asking the viewer may be a teammate's).
  Map<String, String> get agentNames => {
        for (final a in askers) a.id.toLowerCase(): a.name,
        for (final a in mentionableAgents) (a['id']?.toString() ?? '').toLowerCase(): a['name']?.toString() ?? '',
      };

  /// The whole sheet's data. One function so the first open, the poll and the
  /// resume refresh can't drift apart.
  Future<void> load() async {
    if (_loading || _disposed || taskId.isEmpty) return;
    _loading = true;
    final writesAtStart = _writes;
    try {
      final reference = _referenceLoaded ? null : _loadReferenceData();
      final results = await Future.wait<dynamic>([
        actions.apiGetTask(taskId),
        actions.apiGetTaskTimeline(taskId),
        actions.apiGetTaskSessions(taskId),
      ]);
      await reference;
      if (_disposed) return;
      final fresh = results[0];
      final timeline = results[1];
      final sessions = results[2];
      if (fresh != null) task = fresh;
      if (sessions is List) relatedSessions = sessions;
      if (timeline is Map && writesAtStart == _writes) {
        _applyTimeline(timeline);
      } else if (timeline == null && !timelineLoaded) {
        timelineFailed = true;
      }
      timelineLoaded = true;
      _rebuildEntries();
    } finally {
      _loading = false;
      _bump();
    }
  }

  /// The viewer and their agents. Loaded once per sheet: neither changes
  /// while it is open, and a failure only empties the `@` picker.
  Future<void> _loadReferenceData() async {
    final results = await Future.wait<dynamic>([actions.apiGetCurrentUserProfile(), actions.apiListAgentProfiles()]);
    viewer = TaskViewer.fromProfile(results[0] as Map<String, dynamic>?);
    agentProfiles = (results[1] as List<dynamic>?) ?? const [];
    _referenceLoaded = viewer != null;
  }

  void _applyTimeline(Map timeline) {
    comments = tutils.timelineComments(timeline);
    activity = tutils.timelineActivity(timeline);
    taskReactions = tutils.timelineReactions(timeline);
    people = tutils.timelinePeople(timeline);
    sessionRefs = sessionRefsById(tutils.timelineSessionRefs(timeline));
    timelineFailed = false;
  }

  void _rebuildEntries() {
    entries = buildTimelineEntries(comments, activity, linkedSessions);
  }

  /// A write's answer: the whole timeline, put on screen as is.
  bool _applyWrite(Map<String, dynamic>? timeline) {
    if (timeline == null || _disposed) return false;
    _writes++;
    _applyTimeline(timeline);
    timelineLoaded = true;
    _rebuildEntries();
    _bump();
    return true;
  }

  /// Post a new thread, or a reply in [parentCommentId]'s thread. A comment
  /// can wake an agent, and an answered question changes the task, so the
  /// task reloads behind it.
  Future<bool> postComment(String body, {String? parentCommentId}) async {
    final ok = _applyWrite(await actions.apiCreateTaskComment(taskId, body, parentCommentId: parentCommentId));
    if (ok) unawaited(_refreshTask());
    return ok;
  }

  Future<bool> editComment(String commentId, String body) async => _applyWrite(await actions.apiUpdateTaskComment(taskId, commentId, body));

  /// A soft delete: the comment stays as a tombstone so its replies keep
  /// their thread.
  Future<bool> deleteComment(String commentId) async {
    final ok = _applyWrite(await actions.apiDeleteTaskComment(taskId, commentId));
    if (ok) unawaited(_refreshTask());
    return ok;
  }

  /// Toggle one emoji on the task (`task`) or a comment (`comment`). The pill
  /// moves at once; the server's timeline then replaces the guess, and a
  /// failure puts the old pills back.
  Future<bool> toggleReaction(String targetType, String targetId, String emoji) async {
    final before = (comments: comments, taskReactions: taskReactions);
    if (targetType == 'task') {
      taskReactions = toggledReactions(taskReactions, emoji, viewer);
    } else {
      comments = [
        for (final c in comments)
          if (tutils.commentId(c) == targetId) {...Map<String, dynamic>.from(c as Map), 'reactions': toggledReactions(tutils.commentReactions(c), emoji, viewer)} else c,
      ];
      _rebuildEntries();
    }
    _bump();
    final ok = _applyWrite(await actions.apiToggleTaskReaction(taskId, targetType: targetType, targetId: targetId, emoji: emoji));
    if (!ok && !_disposed) {
      comments = before.comments;
      taskReactions = before.taskReactions;
      _rebuildEntries();
      _bump();
    }
    return ok;
  }

  Future<void> _refreshTask() async {
    final fresh = await actions.apiGetTask(taskId);
    if (fresh == null || _disposed) return;
    task = fresh;
    _bump();
  }

  void dispose() {
    _disposed = true;
    _notify = null;
  }
}

/// [reactions] with the viewer's [emoji] flipped: the optimistic half of a
/// toggle. Adds a pill when the viewer is the first, drops it when they were
/// the last.
@visibleForTesting
List<dynamic> toggledReactions(List<dynamic> reactions, String emoji, TaskViewer? viewer) {
  final out = <dynamic>[];
  var found = false;
  for (final r in reactions) {
    if (tutils.reactionEmoji(r) != emoji) {
      out.add(r);
      continue;
    }
    found = true;
    final reacted = tutils.reactionReacted(r);
    final count = tutils.reactionCount(r) + (reacted ? -1 : 1);
    if (count <= 0) continue;
    final reactors = tutils.reactionReactors(r).where((p) => viewer == null || tutils.principalId(p) != viewer.id).toList();
    out.add({
      ...Map<String, dynamic>.from(r as Map),
      'count': count,
      'reacted': !reacted,
      'reactors': [if (!reacted && viewer != null) viewer.toPrincipal(), ...reactors],
    });
  }
  if (!found) {
    out.add({
      'emoji': emoji,
      'count': 1,
      'reacted': true,
      'reactors': [if (viewer != null) viewer.toPrincipal()],
    });
  }
  return out;
}
