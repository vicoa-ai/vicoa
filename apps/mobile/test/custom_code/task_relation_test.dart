// Spec for the Tasks list's Relation to me filter (the web's TaskRelation):
//   - "Assigned to me" keeps tasks assigned to the viewer as a person; an agent
//     that happens to share the id does not count;
//   - "Waiting on me" keeps tasks with an open question addressed to the viewer;
//   - ticked values are OR; none ticked keeps everything;
//   - until the viewer is known, an active filter keeps nothing;
//   - values this build doesn't know are dropped, and the rest come back in
//     menu order.
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/task_relation.dart';

void main() {
  const me = 'u-me';
  Map<String, dynamic> question(String addresseeId) => {
        'comment_id': 'c-$addresseeId',
        'addressee': {'type': 'user', 'id': addresseeId},
        'asked_by': {'type': 'agent', 'id': 'a-1'},
        'asked_at': '2026-11-20T10:00:00Z',
      };
  final tasks = [
    {'id': 'mine', 'assignee_type': 'user', 'assignee_id': me, 'open_questions': []},
    {'id': 'asks-me', 'assignee_type': 'agent', 'assignee_id': 'a-1', 'open_questions': [question(me)]},
    {'id': 'asks-other', 'assignee_type': 'agent', 'assignee_id': 'a-1', 'open_questions': [question('u-other')]},
    {'id': 'agent-same-id', 'assignee_type': 'agent', 'assignee_id': me},
    {'id': 'unassigned', 'assignee_type': null, 'assignee_id': null},
    {'id': 'older-backend'}, // no assignee or open_questions fields at all
  ];
  List<String> kept(Set<String> active, String? viewer) =>
      tasks.where((t) => taskMatchesRelation(t, active, viewer)).map((t) => t['id'] as String).toList();

  test('no relation ticked keeps everything, known viewer or not', () {
    expect(kept({}, me), hasLength(tasks.length));
    expect(kept({}, null), hasLength(tasks.length));
  });

  test('Assigned to me keeps tasks assigned to the viewer as a person', () {
    expect(kept({kTaskRelationAssigned}, me), ['mine']);
  });

  test('Waiting on me keeps tasks with an open question for the viewer', () {
    expect(kept({kTaskRelationWaiting}, me), ['asks-me']);
  });

  test('both ticked is either one', () {
    expect(kept({kTaskRelationAssigned, kTaskRelationWaiting}, me), ['mine', 'asks-me']);
  });

  test('an active filter keeps nothing until the viewer is known', () {
    expect(kept({kTaskRelationAssigned, kTaskRelationWaiting}, null), isEmpty);
  });

  test('unknown values are dropped and the rest come back in menu order', () {
    expect(knownTaskRelations(['waiting', 'mentioned', 'assigned', 'waiting']), [kTaskRelationAssigned, kTaskRelationWaiting]);
    expect(knownTaskRelations(['mentioned']), isEmpty);
  });
}
