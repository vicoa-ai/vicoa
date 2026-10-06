import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:vicoa/custom_code/utils/composer_references.dart';
import 'package:vicoa/custom_code/widgets/reference_suggestions.dart';
import 'package:vicoa/l10n/app_localizations.dart';

const _items = [
  ReferenceCandidate(
    kind: 'session',
    id: 's-1',
    label: 'Investigate slow invoice search',
    token: 'investigate-slow-invoice-search',
    meta: '/home/ada/lighthouse',
  ),
  ReferenceCandidate(
    kind: 'task',
    id: 't-1',
    label: 'Fix flaky checkout test',
    token: 'LIG-1',
    meta: 'Lighthouse',
    project: {'id': 'p-1', 'name': 'Lighthouse'},
    identifier: 'LIG-1',
    status: 'todo',
  ),
  ReferenceCandidate(
    kind: 'automation',
    id: 'a-1',
    label: 'Weekly dependency audit',
    token: 'weekly-dependency-audit',
  ),
];

class _Composer with ComposerReferenceMixin {
  final controller = TextEditingController();

  @override
  TextEditingController get referenceTextController => controller;
  @override
  VoidCallback? get referenceOnStateChanged => null;
  @override
  Future<List<ReferenceCandidate>> fetchReferenceCandidates(String query) async => _items;
  @override
  Future<ComposerReference?> fetchReferenceDetail(String kind, String id) async => null;
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: Column(mainAxisSize: MainAxisSize.min, children: [child])),
  ));
  await tester.pump();
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  testWidgets('groups rows under a heading per kind', (tester) async {
    final composer = _Composer()
      ..showReferenceSuggestions = true
      ..referenceCandidates = _items;
    await _pump(tester, ReferenceSuggestions(mixin: composer));

    expect(find.text('Sessions'), findsOneWidget);
    expect(find.text('Tasks'), findsOneWidget);
    expect(find.text('Automations'), findsOneWidget);
    expect(find.text('Fix flaky checkout test'), findsOneWidget);
    // The task's key, with the "#" it types.
    expect(find.text('#LIG-1'), findsOneWidget);
    expect(find.text('Lighthouse'), findsOneWidget);
  });

  testWidgets('a tap inserts the token in place of the partial one', (tester) async {
    final composer = _Composer()
      ..showReferenceSuggestions = true
      ..referenceCandidates = _items;
    composer.controller.value = const TextEditingValue(
      text: 'look at #fix',
      selection: TextSelection.collapsed(offset: 12),
    );
    await _pump(tester, ReferenceSuggestions(mixin: composer));

    await tester.tap(find.text('Fix flaky checkout test'));
    expect(composer.controller.text, 'look at #LIG-1 ');
    expect(composer.pendingReferences.single.id, 't-1');
  });

  testWidgets('says when it is searching or found nothing', (tester) async {
    final composer = _Composer()
      ..showReferenceSuggestions = true
      ..isLoadingReferences = true;
    await _pump(tester, ReferenceSuggestions(mixin: composer));
    expect(find.text('Searching…'), findsOneWidget);

    composer.isLoadingReferences = false;
    await _pump(tester, ReferenceSuggestions(mixin: composer));
    expect(find.text('No sessions, tasks or automations match'), findsOneWidget);
  });

  testWidgets('renders nothing while closed', (tester) async {
    final composer = _Composer()..referenceCandidates = _items;
    await _pump(tester, ReferenceSuggestions(mixin: composer));
    expect(find.text('Sessions'), findsNothing);
  });

  testWidgets('the link hint follows the token', (tester) async {
    final composer = _Composer();
    composer.controller.value = const TextEditingValue(
      text: '#',
      selection: TextSelection.collapsed(offset: 1),
    );
    composer.insertReference(_items[1]);
    await _pump(
      tester,
      ReferenceLinkHint(
        mixin: composer,
        currentTaskId: () => null,
        message: (label) => 'Sending files this session under $label',
      ),
    );
    expect(find.text('Sending files this session under Fix flaky checkout test'), findsOneWidget);

    composer.controller.text = 'token gone';
    await tester.pump();
    expect(find.textContaining('Sending files'), findsNothing);
  });

  testWidgets('no hint for a session that already has a task', (tester) async {
    final composer = _Composer();
    composer.controller.value = const TextEditingValue(
      text: '#',
      selection: TextSelection.collapsed(offset: 1),
    );
    composer.insertReference(_items[1]);
    await _pump(
      tester,
      ReferenceLinkHint(
        mixin: composer,
        currentTaskId: () => 'other-task',
        message: (label) => 'Sending files this session under $label',
      ),
    );
    expect(find.textContaining('Sending files'), findsNothing);
  });
}
