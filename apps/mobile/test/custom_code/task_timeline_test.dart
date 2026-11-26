import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/custom_code/utils/task_mentions.dart';
import 'package:vicoa/custom_code/utils/task_questions.dart';
import 'package:vicoa/custom_code/utils/task_timeline.dart';
import 'package:vicoa/l10n/app_localizations_en.dart';
import 'package:vicoa/pages/tasks/task_timeline_text.dart';

Map<String, dynamic> person(String id, String? name, {String type = 'user'}) =>
    {'type': type, 'id': id, 'name': name, 'avatar_image_uri': null, 'emoji': null, 'updated_at': null};

Map<String, dynamic> comment(
  String id,
  String createdAt, {
  String? parent,
  Map<String, dynamic>? author,
  String? body,
  String? deletedAt,
  Map<String, dynamic>? question,
}) =>
    {
      'id': id,
      'task_id': 't1',
      'parent_comment_id': parent,
      'author': author ?? person('u1', 'Nick'),
      'agent_instance_id': null,
      'body': deletedAt != null ? null : (body ?? id),
      'kind': 'comment',
      'reactions': [],
      'question': question,
      'created_at': createdAt,
      'edited_at': null,
      'deleted_at': deletedAt,
    };

Map<String, dynamic> activityRow(String id, String createdAt, {Map<String, dynamic> details = const {}, String action = 'status_changed'}) =>
    {'id': id, 'actor': person('u1', 'Nick'), 'action': action, 'details': details, 'created_at': createdAt};

const viewer = TaskViewer(id: 'u1', name: 'test1@gmail.com');

const _agentA = '11111111-1111-1111-1111-111111111111';
const _agentB = '22222222-2222-2222-2222-222222222222';
const _user = '33333333-3333-3333-3333-333333333333';

void main() {
  final l10n = AppLocalizationsEn();

  group('buildThreads', () {
    test('hangs replies off their root, oldest first', () {
      final threads = buildThreads([
        comment('root', '2026-09-01T10:00:00Z'),
        comment('r2', '2026-09-01T12:00:00Z', parent: 'root'),
        comment('r1', '2026-09-01T11:00:00Z', parent: 'root'),
      ]);
      expect(threads, hasLength(1));
      expect(threads[0].root['id'], 'root');
      expect(threads[0].replies.map((r) => r['id']), ['r1', 'r2']);
    });

    test('does not trust arrival order: a reply listed before its root still hangs off it', () {
      final threads = buildThreads([
        comment('reply', '2026-09-01T11:00:00Z', parent: 'root'),
        comment('root', '2026-09-01T10:00:00Z'),
      ]);
      expect(threads.map((t) => t.root['id']), ['root']);
      expect(threads[0].replies.map((r) => r['id']), ['reply']);
    });

    test('orders threads by their root, not by their newest reply', () {
      final threads = buildThreads([
        comment('first', '2026-09-01T10:00:00Z'),
        comment('late-reply', '2026-09-03T10:00:00Z', parent: 'first'),
        comment('second', '2026-09-02T10:00:00Z'),
      ]);
      expect(threads.map((t) => t.root['id']), ['first', 'second']);
    });

    test('promotes a reply whose root is missing rather than dropping it', () {
      final threads = buildThreads([comment('orphan', '2026-09-01T10:00:00Z', parent: 'gone')]);
      expect(threads.map((t) => t.root['id']), ['orphan']);
    });

    test('keeps a deleted root so its replies stay in their thread', () {
      final threads = buildThreads([
        comment('root', '2026-09-01T10:00:00Z', deletedAt: '2026-09-02T10:00:00Z'),
        comment('reply', '2026-09-01T11:00:00Z', parent: 'root'),
      ]);
      expect(threads, hasLength(1));
      expect(threads[0].root['body'], isNull);
      expect(threads[0].replies.map((r) => r['id']), ['reply']);
    });

    test('compares times, not text: a +00:00 stamp sorts with the Z ones', () {
      final threads = buildThreads([
        comment('b', '2026-09-01T10:30:00+00:00'),
        comment('a', '2026-09-01T10:00:00Z'),
        comment('c', '2026-09-01T11:00:00Z'),
      ]);
      expect(threads.map((t) => t.root['id']), ['a', 'b', 'c']);
    });
  });

  group('buildTimelineEntries', () {
    test('does not give a reply a row of its own', () {
      final entries = buildTimelineEntries([
        comment('root', '2026-09-01T10:00:00Z'),
        comment('reply', '2026-09-01T11:00:00Z', parent: 'root'),
      ], [], []);
      expect(entries, hasLength(1));
      expect((entries[0] as ThreadEntry).thread.replies.map((r) => r['id']), ['reply']);
    });

    test('gives each thread its own card', () {
      final entries = buildTimelineEntries([
        comment('a', '2026-09-01T10:00:00Z'),
        comment('b', '2026-09-01T10:01:00Z'),
      ], [], []);
      expect(entries.map((e) => e.runtimeType), [ThreadEntry, ThreadEntry]);
    });

    test('merges consecutive activity into one run, broken by a comment', () {
      final entries = buildTimelineEntries(
        [comment('c', '2026-09-01T10:30:00Z')],
        [
          activityRow('a1', '2026-09-01T10:00:00Z'),
          activityRow('a2', '2026-09-01T10:10:00Z'),
          activityRow('a3', '2026-09-01T11:00:00Z'),
        ],
        [],
      );
      expect(entries.map((e) => e.runtimeType), [ActivityRunEntry, ThreadEntry, ActivityRunEntry]);
      expect((entries[0] as ActivityRunEntry).rows.map((r) => r['id']), ['a1', 'a2']);
    });

    test('keeps activity whose session is not linked to the task', () {
      final entries = buildTimelineEntries([], [activityRow('a1', '2026-09-01T10:00:00Z', details: {'agent_instance_id': 'gone'})], []);
      expect(entries, hasLength(1));
      expect((entries[0] as ActivityRunEntry).rows.map((r) => r['id']), ['a1']);
    });

    const session = {'id': 's1', 'started_at': '2026-09-01T09:00:00Z', 'status': 'ACTIVE'};

    test('folds status churn into the session that caused it', () {
      final entries = buildTimelineEntries([], [activityRow('a1', '2026-09-01T10:00:00Z', details: {'agent_instance_id': 's1'})], [session]);
      expect(entries, hasLength(1));
      expect((entries[0] as SessionEntry).absorbed.map((r) => r['id']), ['a1']);
    });

    test('keeps a change the session made directly out of its card', () {
      final entries = buildTimelineEntries([], [
        activityRow('a1', '2026-09-01T10:00:00Z', details: {'agent_instance_id': 's1'}),
        activityRow('a2', '2026-09-01T11:00:00Z', details: {'agent_instance_id': 's1', 'direct': true}),
      ], [session]);
      expect(entries.map((e) => e.runtimeType), [SessionEntry, ActivityRunEntry]);
      expect((entries[0] as SessionEntry).absorbed.map((r) => r['id']), ['a1']);
      expect((entries[1] as ActivityRunEntry).rows.map((r) => r['id']), ['a2']);
    });

    test('keeps a reference from the linked session out of its card', () {
      final entries = buildTimelineEntries([], [activityRow('a1', '2026-09-01T10:00:00Z', details: {'agent_instance_id': 's1'}, action: 'referenced')], [session]);
      expect(entries.map((e) => e.runtimeType), [SessionEntry, ActivityRunEntry]);
      expect((entries[0] as SessionEntry).absorbed, isEmpty);
    });

    test('puts a session with no start time first instead of dropping it', () {
      final entries = buildTimelineEntries([comment('c', '2026-09-01T10:00:00Z')], [], [
        {'id': 's2', 'started_at': null},
      ]);
      expect(entries.map((e) => e.runtimeType), [SessionEntry, ThreadEntry]);
    });
  });

  group('linkedTaskSessions', () {
    test('keeps only the sessions filed under the task', () {
      final sessions = linkedTaskSessions([
        {'id': 's1', 'task_relations': ['linked', 'commented']},
        {'id': 's2', 'task_relations': ['referenced']},
      ]);
      expect(sessions.map((s) => s['id']), ['s1']);
    });
  });

  group('agentsToWake', () {
    const top = WakeContext(inThread: false, assigneeAgentId: _agentA);

    test('a note wakes nobody', () {
      expect(agentsToWake('/note just for me', top), isEmpty);
      expect(agentsToWake('/notebook is not a note', top), [_agentA]);
    });

    test('an explicit mention wins, even on a closed task', () {
      const body = 'hey [@B](vicoa://agent/$_agentB)';
      expect(agentsToWake(body, top), [_agentB]);
      expect(agentsToWake(body, const WakeContext(inThread: false, taskClosed: true)), [_agentB]);
    });

    test('a person mention wakes no agent by itself', () {
      expect(agentsToWake('cc [@Ada](vicoa://user/$_user)', const WakeContext(inThread: false)), isEmpty);
    });

    test('a closed task wakes only on a mention', () {
      expect(agentsToWake('thanks', const WakeContext(inThread: false, assigneeAgentId: _agentA, taskClosed: true)), isEmpty);
    });

    test('a reply wakes the thread agent, not the assignee', () {
      expect(agentsToWake('ok', const WakeContext(inThread: true, threadAgentId: _agentB, assigneeAgentId: _agentA)), [_agentB]);
      expect(agentsToWake('ok', const WakeContext(inThread: true, assigneeAgentId: _agentA)), isEmpty);
    });

    test('a top-level comment answers the askers before the assignee', () {
      const ctx = WakeContext(inThread: false, assigneeAgentId: _agentA, askers: [WaitingAgent(_agentB, 'B')]);
      expect(agentsToWake('yes, go ahead', ctx), [_agentB]);
    });
  });

  group('mentions in the draft', () {
    const picks = [PickedMention(id: _agentA, name: 'bot'), PickedMention(id: _agentB, name: 'bot2'), PickedMention(id: _user, name: 'Ada Lovelace', kind: 'user')];

    test('matches the longer name first', () {
      final ranges = mentionRanges('ask @bot2 and @bot.', picks);
      expect(ranges.map((r) => r.id), [_agentB, _agentA]);
    });

    test('needs a boundary on both sides', () {
      expect(mentionRanges('mail me@bot please', picks), isEmpty);
      expect(mentionRanges('@botty', picks), isEmpty);
    });

    test('drops a pick whose name was deleted', () {
      expect(activeMentions(picks, 'just @bot').map((p) => p.id), [_agentA]);
    });

    test('serializes picks as mention links, with names that have spaces', () {
      expect(serializeMentions('@bot ping @Ada Lovelace', picks), '[@bot](vicoa://agent/$_agentA) ping [@Ada Lovelace](vicoa://user/$_user)');
    });

    test('shows posted mentions as bold names', () {
      expect(displayMentions('hi [@bot](vicoa://agent/$_agentA)!'), 'hi **@bot**!');
    });

    test('strips the note prefix for display', () {
      expect(stripNotePrefix('/note: remember this'), 'remember this');
    });
  });

  group('questions', () {
    final agent = person(_agentA, 'haiku-bot', type: 'agent');
    final open = {'addressee': person('u1', 'Nick'), 'closed_at': null};

    test('reads an open question off its comment, not a closed or deleted one', () {
      expect(openQuestion(comment('c', '2026-09-01T10:00:00Z', question: open)), isNotNull);
      expect(openQuestion(comment('c', '2026-09-01T10:00:00Z', question: {...open, 'closed_at': '2026-09-02T00:00:00Z'})), isNull);
      expect(openQuestion(comment('c', '2026-09-01T10:00:00Z', question: open, deletedAt: '2026-09-02T00:00:00Z')), isNull);
    });

    test('finds the agents waiting on the viewer, each once', () {
      final askers = askersFromComments([
        comment('c1', '2026-09-01T10:00:00Z', author: agent, question: open),
        comment('c2', '2026-09-01T11:00:00Z', author: agent, question: open),
        comment('c3', '2026-09-01T12:00:00Z', author: agent, question: {'addressee': person('u9', 'Ada'), 'closed_at': null}),
      ], 'u1');
      expect(askers.map((a) => a.id), [_agentA]);
    });

    test('a thread replies to the agent that wrote in it last', () {
      final thread = buildThreads([
        comment('root', '2026-09-01T10:00:00Z', author: agent),
        comment('mine', '2026-09-01T11:00:00Z', parent: 'root'),
      ]).single;
      expect(threadAgentId(thread), _agentA);
    });

    test('lists whom a task waits on', () {
      final task = {
        'open_questions': [
          {'addressee': person('u2', 'Ada'), 'asked_by': agent},
          {'addressee': person('u2', 'Ada'), 'asked_by': agent},
          {'addressee': person('u1', null), 'asked_by': agent},
        ],
      };
      expect(waitingOnPeople(task).map((p) => p['id']), ['u2', 'u1']);
      expect(askersFromTask(task, 'u1').map((a) => a.id), [_agentA]);
    });
  });

  group('describeReactors', () {
    Map<String, dynamic> reaction(int count, List<Map<String, dynamic>> reactors) => {'emoji': '👍', 'count': count, 'reacted': false, 'reactors': reactors};

    test('names a single reactor', () {
      expect(describeReactors(l10n, reaction(1, [person('u2', 'Ada')]), viewer), 'Ada reacted with 👍');
    });

    test('calls the signed-in user "You" and puts them first', () {
      expect(describeReactors(l10n, reaction(2, [person('u2', 'Ada'), person('u1', null)]), viewer), 'You and Ada reacted with 👍');
    });

    test('joins three with commas and a final "and"', () {
      expect(describeReactors(l10n, reaction(3, [person('u2', 'Ada'), person('u3', 'Bo'), person('u4', 'Cy')]), viewer), 'Ada, Bo and Cy reacted with 👍');
    });

    test('collapses the reactors the server did not name', () {
      expect(describeReactors(l10n, reaction(5, [person('u2', 'Ada'), person('u3', 'Bo')]), viewer), 'Ada, Bo and 3 others reacted with 👍');
      expect(describeReactors(l10n, reaction(2, [person('u2', 'Ada')]), viewer), 'Ada and 1 other reacted with 👍');
    });
  });

  group('text', () {
    test('reads activity rows', () {
      expect(activityText(l10n, activityRow('a', 't', details: {'from': 'todo', 'to': 'in_progress'})), 'moved from Todo to In Progress');
      expect(activityText(l10n, activityRow('a', 't', action: 'referenced')), 'referenced this task');
      expect(activityText(l10n, activityRow('a', 't', action: 'assigned', details: {'to': null})), 'cleared the assignee');
      expect(activityText(l10n, activityRow('a', 't', action: 'some_new_thing')), 'some new thing');
    });

    test('names a session by its name, else by its agent', () {
      expect(sessionRefTitle(l10n, {'id': 's1', 'name': 'Fix login', 'agent_type_name': 'claude'}), 'Fix login');
      expect(sessionRefTitle(l10n, {'id': 's1', 'name': null, 'agent_type_name': 'claude'}), 'a Claude session');
      expect(sessionRefTitle(l10n, {'id': 's1', 'name': null, 'agent_type_name': null}), 'a session');
    });

    test('names principals without ever inventing an email', () {
      expect(principalDisplayName(l10n, person('u1', null), viewer), 'test1@gmail.com');
      expect(principalDisplayName(l10n, person('u2', null), viewer), 'Vicoa user');
      expect(principalDisplayName(l10n, person('a1', null, type: 'agent'), viewer), 'Agent');
      expect(principalDisplayName(l10n, null, viewer), 'Unknown');
    });

    test('says whom a task waits on, the viewer first', () {
      expect(waitingOnLabel(l10n, [person('u2', 'Ada'), person('u1', 'Nick')], 'u1'), 'Waiting on you and Ada');
      expect(waitingOnLabel(l10n, [person('u2', 'Ada'), person('u3', 'Bo'), person('u4', 'Cy')], 'u1'), 'Waiting on 3 people');
      expect(waitingOnLabel(l10n, [], 'u1'), isNull);
    });
  });
}
