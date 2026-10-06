// What `#` references do to the new-session composer: the first message it
// sends, and which task the new session is filed under.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/composer_references.dart';
import 'package:vicoa/pages/new_session/new_session_model.dart';

const _taskRef = ComposerReference(
  kind: 'task',
  id: 'task-1',
  token: 'LIG-1',
  label: 'Fix flaky checkout test',
  context: 'Task LIG-1: Fix flaky checkout test',
);

const _sessionRef = ComposerReference(
  kind: 'session',
  id: 'session-1',
  token: 'slow-invoice-search',
  label: 'Investigate slow invoice search',
  context: 'Session "Investigate slow invoice search"',
);

const _block = 'Referenced with # in Vicoa:';

void main() {
  test('appends the referenced blocks below the typed prompt', () {
    final model = NewSessionModel()
      ..pendingReferences = [_taskRef, _sessionRef];
    model.promptController.text = 'look at #LIG-1 and #slow-invoice-search';

    expect(
      model.composeFirstMessage(),
      'look at #LIG-1 and #slow-invoice-search\n\n---\n$_block\n\n'
      '${_taskRef.context}\n\n${_sessionRef.context}',
    );
  });

  test('a deleted token drops its block', () {
    final model = NewSessionModel()..pendingReferences = [_taskRef];
    model.promptController.text = 'nothing referenced any more';

    expect(model.composeFirstMessage(), 'nothing referenced any more');
    expect(model.linkTaskId, isNull);
  });

  test('a referenced task files the session when nothing seeded it', () {
    final model = NewSessionModel()
      ..pendingReferences = [_sessionRef, _taskRef];
    model.promptController.text = '#slow-invoice-search then #LIG-1';

    expect(model.linkTaskId, 'task-1');
  });

  test('the seeding task wins, and a # to it is not repeated', () {
    final model = NewSessionModel(seedTaskId: 'task-1')
      ..pendingReferences = [_taskRef];
    model.promptController.text = 'Fix flaky checkout test\n\nsee #LIG-1';

    expect(model.linkTaskId, 'task-1');
    expect(model.composeFirstMessage(), isNot(contains(_block)));
  });

  test('a seeded session still carries other references', () {
    const other = ComposerReference(
      kind: 'task',
      id: 'task-2',
      token: 'LIG-2',
      label: 'Add CSV export',
      context: 'Task LIG-2: Add CSV export',
    );
    final model = NewSessionModel(seedTaskId: 'task-1')
      ..pendingReferences = [other];
    model.promptController.text = 'also #LIG-2';

    expect(model.linkTaskId, 'task-1');
    expect(model.composeFirstMessage(), contains(other.context));
  });
}
