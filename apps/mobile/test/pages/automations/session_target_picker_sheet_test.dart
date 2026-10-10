// The automation editor's "Runs in" sheet: a new session each run, or one of
// your sessions that every run continues. Empty search lists recent sessions,
// typing searches; a tap returns the pick.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/automations/session_target_picker_sheet.dart';

const _screen = Size(402.0, 874.0);
const _statusBar = 62.0;

Map<String, dynamic> _session(String id, String name, {String? machineId = 'm-1'}) => {
      'id': id,
      'name': name,
      'machine_id': machineId,
      'project': '~/projects/$id',
      'status': 'COMPLETED',
      'agent_type_name': 'Claude Code',
      'started_at': '2026-10-01T08:00:00Z',
    };

final _recent = [
  _session('a', 'Fix CI'),
  _session('b', 'Terminal session', machineId: null),
  _session('c', 'Nightly report'),
];

Future<List<SessionTargetPick?>> _open(
  WidgetTester tester, {
  String? selectedId,
  List<String>? queries,
}) async {
  tester.view.physicalSize = _screen;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  final picks = <SessionTargetPick?>[];
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async => picks.add(await showSessionTargetPickerSheet(
              context: context,
              selectedId: selectedId,
              loadSessions: (query) async {
                queries?.add(query);
                return query.isEmpty ? _recent : [_session('d', 'Deploy web')];
              },
            )),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return picks;
}

void main() {
  testWidgets('lists recent sessions it can run in, and checks the current one', (tester) async {
    await _open(tester, selectedId: 'c');
    expect(tester.takeException(), isNull);
    expect(find.text('New session each run'), findsOneWidget);
    expect(find.text('Recent sessions'), findsOneWidget);
    expect(find.text('Fix CI'), findsOneWidget);
    expect(find.text('Nightly report'), findsOneWidget);
    // No computer to resume it on, so the scheduler could never reach it.
    expect(find.text('Terminal session'), findsNothing);
    expect(find.byIcon(Icons.check_rounded), findsOneWidget);
    final selectedRow = find.ancestor(of: find.text('Nightly report'), matching: find.byType(InkWell)).first;
    expect(find.descendant(of: selectedRow, matching: find.byIcon(Icons.check_rounded)), findsOneWidget);
  });

  testWidgets('tapping a session returns it', (tester) async {
    final picks = await _open(tester);
    await tester.tap(find.text('Fix CI'));
    await tester.pumpAndSettle();
    expect(picks.single?.target?.id, 'a');
    expect(picks.single?.target?.machineId, 'm-1');
    expect(picks.single?.target?.project, '~/projects/a');
  });

  testWidgets('New session each run returns no target; closing returns nothing', (tester) async {
    final picks = await _open(tester, selectedId: 'a');
    await tester.tap(find.text('New session each run'));
    await tester.pumpAndSettle();
    expect(picks.single, isNotNull);
    expect(picks.single!.target, isNull);

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.close_rounded));
    await tester.pumpAndSettle();
    expect(picks.last, isNull);
  });

  testWidgets('typing searches, and clearing goes back to recent sessions without a refetch',
      (tester) async {
    final queries = <String>[];
    final picks = await _open(tester, queries: queries);
    await tester.enterText(find.byType(TextField), 'deploy');
    await tester.pump(const Duration(milliseconds: 250));
    await tester.pumpAndSettle();
    expect(find.text('Matching sessions'), findsOneWidget);
    expect(find.text('Deploy web'), findsOneWidget);
    expect(find.text('Fix CI'), findsNothing);

    await tester.enterText(find.byType(TextField), '');
    await tester.pumpAndSettle();
    expect(find.text('Recent sessions'), findsOneWidget);
    expect(find.text('Fix CI'), findsOneWidget);
    expect(queries, ['', 'deploy']);

    await tester.enterText(find.byType(TextField), 'deploy');
    await tester.pump(const Duration(milliseconds: 250));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Deploy web'));
    await tester.pumpAndSettle();
    expect(picks.single?.target?.id, 'd');
  });

  testWidgets('keyboard up: the sheet rides it, clear of the status bar, without overflowing',
      (tester) async {
    await _open(tester);
    // The sheet route hides this inset from the sheet's MediaQuery; the header
    // once slid under the status bar because of it.
    tester.view.padding = const FakeViewPadding(top: _statusBar);
    tester.view.viewInsets = const FakeViewPadding(bottom: 336.0);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byType(TextField), findsOneWidget);
    expect(tester.getRect(find.byIcon(Icons.close_rounded)).top, greaterThan(_statusBar));
  });
}
