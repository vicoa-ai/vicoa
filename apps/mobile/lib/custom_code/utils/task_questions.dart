/// Questions an agent asked on a task (`vicoa task comment --ask`), as the
/// card and the thread show them. A port of the web's `lib/task-questions.ts`.
/// A question is stored state, on the task (`open_questions`) and on its
/// comment (`question`), never read from text, so "Waiting on Nick" is only
/// ever as wrong as the server.
library;

import 'task_mentions.dart' show WaitingAgent;
import 'task_timeline.dart' show TaskThread;
import 'task_utils.dart';

/// The people [task] waits on, oldest question first, each once
/// (`PrincipalResponse` maps).
List<Map<String, dynamic>> waitingOnPeople(dynamic task) {
  final seen = <String>{};
  final out = <Map<String, dynamic>>[];
  for (final q in taskOpenQuestions(task)) {
    final addressee = q is Map ? q['addressee'] : null;
    if (addressee is! Map) continue;
    final key = principalId(addressee) ?? '?${out.length}';
    if (!seen.add(key)) continue;
    out.add(Map<String, dynamic>.from(addressee));
  }
  return out;
}

/// A comment's question while it is still open, or null.
Map<String, dynamic>? openQuestion(dynamic comment) {
  final q = commentQuestion(comment);
  if (q == null || q['closed_at'] != null || commentIsDeleted(comment)) return null;
  return q;
}

/// The agents with an open question to the viewer, from the thread: whom the
/// viewer's next top-level comment answers.
List<WaitingAgent> askersFromComments(List<dynamic> comments, String? viewerId) {
  if (viewerId == null) return const [];
  final out = <WaitingAgent>[];
  for (final c in comments) {
    final q = openQuestion(c);
    if (q == null || principalId(q['addressee']) != viewerId) continue;
    final author = commentAuthor(c);
    final id = principalId(author);
    if (principalType(author) != 'agent' || id == null) continue;
    if (out.any((a) => a.id == id)) continue;
    out.add(WaitingAgent(id, principalName(author) ?? ''));
  }
  return out;
}

/// The same, from the task's `open_questions` (before the thread loads).
List<WaitingAgent> askersFromTask(dynamic task, String? viewerId) {
  if (viewerId == null) return const [];
  final out = <WaitingAgent>[];
  for (final q in taskOpenQuestions(task)) {
    if (q is! Map || principalId(q['addressee']) != viewerId) continue;
    final by = q['asked_by'];
    final id = principalId(by);
    if (principalType(by) != 'agent' || id == null) continue;
    if (out.any((a) => a.id == id)) continue;
    out.add(WaitingAgent(id, principalName(by) ?? ''));
  }
  return out;
}

/// The agent that wrote in [thread] most recently: who a plain reply wakes.
String? threadAgentId(TaskThread thread) {
  final comments = thread.comments;
  for (var i = comments.length - 1; i >= 0; i--) {
    final c = comments[i];
    final author = commentAuthor(c);
    final id = principalId(author);
    if (principalType(author) == 'agent' && id != null && commentBody(c) != null) return id;
  }
  return null;
}
