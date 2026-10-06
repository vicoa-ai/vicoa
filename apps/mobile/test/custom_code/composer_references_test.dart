import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/custom_code/actions/index.dart' as actions;
import 'package:vicoa/custom_code/utils/composer_references.dart';

ComposerReference ref({
  String kind = 'task',
  String id = 'task-1',
  String token = 'VIC-42',
  String label = 'Fix the diff editor',
  String context = 'Task VIC-42 — Fix the diff editor',
}) =>
    ComposerReference(
        kind: kind, id: id, token: token, label: label, context: context);

const _task = ReferenceCandidate(
  kind: 'task',
  id: 'task-1',
  label: 'Fix the diff editor',
  token: 'VIC-42',
  meta: 'Vicoa',
  identifier: 'VIC-42',
  status: 'in_progress',
);

/// A composer with the network swapped out.
class _FakeComposer with ComposerReferenceMixin {
  _FakeComposer({this.enabled = true});

  final bool enabled;
  final controller = TextEditingController();
  List<ReferenceCandidate> candidates = const [_task];
  Object? error;
  ComposerReference? detail;
  final queries = <String>[];
  int notifications = 0;

  @override
  TextEditingController get referenceTextController => controller;
  @override
  VoidCallback? get referenceOnStateChanged => () => notifications++;
  @override
  bool get referencesEnabled => enabled;

  @override
  Future<List<ReferenceCandidate>> fetchReferenceCandidates(
      String query) async {
    queries.add(query);
    if (error != null) throw error!;
    return candidates;
  }

  @override
  Future<ComposerReference?> fetchReferenceDetail(
          String kind, String id) async =>
      detail;

  /// Type [text] with the caret at [caret] (end by default), as onChanged would.
  void type(String text, [int? caret]) {
    controller.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: caret ?? text.length),
    );
    filterReferences(text);
  }
}

Future<void> _pastDebounce() => Future<void>.delayed(
    ComposerReferenceMixin.referenceDebounce + const Duration(milliseconds: 50));

void main() {
  group('detectTriggerToken', () {
    test('finds the token the caret is inside', () {
      const text = 'look at #VIC';
      expect(detectTriggerToken(text, text.length, '#'),
          const TriggerToken(8, 12, 'VIC'));
    });

    test('opens on a bare trigger', () {
      expect(detectTriggerToken('#', 1, '#'), const TriggerToken(0, 1, ''));
    });

    test('ignores a trigger glued to the previous word', () {
      expect(detectTriggerToken('issue#42', 8, '#'), isNull);
    });

    test('ignores a token the caret has moved past', () {
      const text = '#VIC-42 and then some more';
      expect(detectTriggerToken(text, text.length, '#'), isNull);
    });

    test('picks the token the caret is in, not the last one in the text', () {
      expect(detectTriggerToken('#one #two', 4, '#')?.query, 'one');
    });

    test('lets @ and # claim different tokens in the same line', () {
      const text = '@src/app.ts #VIC';
      expect(detectTriggerToken(text, text.length, '@'), isNull);
      expect(detectTriggerToken(text, text.length, '#')?.query, 'VIC');
    });

    test('is null on empty text', () {
      expect(detectTriggerToken('', 0, '#'), isNull);
    });
  });

  group('replaceTriggerToken', () {
    test('replaces the partial token and adds a trailing space', () {
      const text = 'look at #VIC';
      final token = detectTriggerToken(text, text.length, '#')!;
      final next = replaceTriggerToken(text, token, '#', 'VIC-42');
      expect(next.text, 'look at #VIC-42 ');
      expect(next.cursor, 16);
    });

    test('keeps the text that follows and does not double the space', () {
      const text = 'see #VI next';
      final token = detectTriggerToken(text, 7, '#')!;
      expect(replaceTriggerToken(text, token, '#', 'VIC-42').text,
          'see #VIC-42 next');
    });
  });

  group('addReference', () {
    test('replaces an earlier pick that slugified to the same token', () {
      final first = ref(id: 'a', token: 'fix-the-bug');
      final second = ref(id: 'b', token: 'fix-the-bug');
      expect(addReference([first], second), [second]);
    });

    test('keeps references with distinct tokens, in pick order', () {
      final task = ref(token: 'VIC-42');
      final session = ref(kind: 'session', id: 's', token: 'zesty-quartz');
      expect(addReference([task], session).map((r) => r.token),
          ['VIC-42', 'zesty-quartz']);
    });
  });

  group('activeReferences', () {
    test('drops a reference whose token the user deleted', () {
      final kept = ref(token: 'VIC-42');
      final removed = ref(id: 'gone', token: 'zesty-quartz');
      expect(activeReferences([kept, removed], 'work on #VIC-42 please'),
          [kept]);
    });

    test('requires the "#" too, so bare prose does not resurrect a reference',
        () {
      expect(activeReferences([ref(token: 'VIC-42')], 'see VIC-42'), isEmpty);
    });
  });

  group('buildReferenceBlock', () {
    test('joins each reference block under one header', () {
      final block = buildReferenceBlock([
        ref(context: 'Task VIC-42 — Fix it'),
        ref(kind: 'session', id: 's', token: 'z', context: 'Session "z"'),
      ]);
      expect(block,
          'Referenced with # in Vicoa:\n\nTask VIC-42 — Fix it\n\nSession "z"');
    });

    test('is empty when every expansion failed', () {
      expect(buildReferenceBlock([ref(context: '')]), '');
    });
  });

  group('composeOutgoingMessage', () {
    test('appends the block after the typed text', () {
      expect(
        composeOutgoingMessage('continue #VIC-42', [ref()]),
        'continue #VIC-42\n\n---\nReferenced with # in Vicoa:\n\n'
        'Task VIC-42 — Fix the diff editor',
      );
    });

    test('leaves the message untouched when nothing is referenced', () {
      expect(composeOutgoingMessage('plain text', []), 'plain text');
    });
  });

  group('taskLinkForSend', () {
    test('links the first referenced task when the session has none', () {
      final refs = [
        ref(kind: 'session', id: 's', token: 'z'),
        ref(id: 'task-a', token: 'VIC-42'),
        ref(id: 'task-b', token: 'VIC-43'),
      ];
      expect(taskLinkForSend(refs, null), 'task-a');
    });

    test('never re-files a session that already belongs to a task', () {
      expect(taskLinkForSend([ref(id: 'task-a')], 'task-b'), isNull);
    });

    test('treats an empty task id as no task', () {
      expect(taskLinkForSend([ref(id: 'task-a')], ''), 'task-a');
    });

    test('is null when no task was referenced', () {
      expect(taskLinkForSend([ref(kind: 'automation', id: 'x')], null), isNull);
    });
  });

  group('ComposerReference.fromCandidate', () {
    test('stands in for the expansion until (or unless) it arrives', () {
      final composed = ComposerReference.fromCandidate(_task);
      expect(composed.token, 'VIC-42');
      expect(composed.context, 'Task "Fix the diff editor"\nVicoa · id: task-1');
      // A send in the fetch window still carries something resolvable.
      expect(buildReferenceBlock([composed]), contains('id: task-1'));
    });

    test('parses the API shape, including the project', () {
      final item = ReferenceCandidate.fromJson({
        'kind': 'session',
        'id': 's-1',
        'label': 'Refactor cache',
        'token': 'refactor-cache',
        'meta': 'Lighthouse',
        'project': {'id': 'p-1', 'name': 'Lighthouse', 'icon': null},
        'identifier': null,
        'status': 'ACTIVE',
      });
      expect(item.kind, 'session');
      expect(item.project?['name'], 'Lighthouse');
      expect(item.identifier, isNull);
    });
  });

  group('ComposerReferenceMixin', () {
    test('opens on "#" at once, then fills the panel after the debounce',
        () async {
      final c = _FakeComposer();
      c.type('look at #');
      expect(c.showReferenceSuggestions, isTrue);
      expect(c.isLoadingReferences, isTrue);
      expect(c.queries, isEmpty);

      await _pastDebounce();
      expect(c.queries, ['']);
      expect(c.isLoadingReferences, isFalse);
      expect(c.referenceCandidates.single.id, 'task-1');
    });

    test('only the last of several quick keystrokes queries', () async {
      final c = _FakeComposer();
      c.type('#V');
      c.type('#VI');
      c.type('#VIC');
      await _pastDebounce();
      expect(c.queries, ['VIC']);
    });

    test('closes and drops the rows once the caret leaves the token',
        () async {
      final c = _FakeComposer();
      c.type('#VIC');
      await _pastDebounce();
      c.type('#VIC done');
      expect(c.showReferenceSuggestions, isFalse);
      expect(c.referenceCandidates, isEmpty);
    });

    test('a pick replaces the partial token and upgrades to the full block',
        () async {
      final c = _FakeComposer()
        ..detail = ref(context: 'Task VIC-42: Fix the diff editor\nstatus: todo');
      c.type('see #VI');
      await _pastDebounce();

      c.insertReference(_task);
      expect(c.controller.text, 'see #VIC-42 ');
      expect(c.controller.selection.baseOffset, 'see #VIC-42 '.length);
      expect(c.showReferenceSuggestions, isFalse);
      expect(c.pendingReferences.single.context,
          'Task "Fix the diff editor"\nVicoa · id: task-1');

      await Future<void>.delayed(Duration.zero);
      expect(c.pendingReferences.single.context, contains('status: todo'));
    });

    test('a failed expansion keeps the one-line fallback', () async {
      final c = _FakeComposer();
      c.type('#');
      c.insertReference(_task);
      await Future<void>.delayed(Duration.zero);
      expect(c.pendingReferences.single.context, contains('id: task-1'));
    });

    test('a 404 turns the trigger off for good', () async {
      final c = _FakeComposer()
        ..error = actions.ApiException('Not Found', 404);
      c.type('#');
      await _pastDebounce();
      expect(c.referencesUnavailable, isTrue);
      expect(c.showReferenceSuggestions, isFalse);

      c.type('#again');
      expect(c.showReferenceSuggestions, isFalse);
    });

    test('another failure just shows no rows', () async {
      final c = _FakeComposer()..error = actions.ApiException('Boom', 500);
      c.type('#');
      await _pastDebounce();
      expect(c.referencesUnavailable, isFalse);
      expect(c.showReferenceSuggestions, isTrue);
      expect(c.referenceCandidates, isEmpty);
      expect(c.isLoadingReferences, isFalse);
    });

    test('stays closed where references are disabled', () {
      final c = _FakeComposer(enabled: false);
      c.type('#');
      expect(c.showReferenceSuggestions, isFalse);
    });

    test('the link hint follows the token and the current task', () {
      final c = _FakeComposer();
      c.type('#');
      c.insertReference(_task);
      expect(c.pendingTaskLink(c.controller.text, null)?.id, 'task-1');
      expect(c.pendingTaskLink(c.controller.text, 'other-task'), isNull);
      expect(c.pendingTaskLink('token deleted', null), isNull);
    });

    test('clearing forgets the picks', () {
      final c = _FakeComposer();
      c.type('#');
      c.insertReference(_task);
      c.clearPendingReferences();
      expect(c.pendingReferences, isEmpty);
      expect(c.liveReferences('#VIC-42'), isEmpty);
    });
  });
}
