import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/tasks/task_detail_sheet.dart';

// The sheet's requests fail in a test (there is no signed-in client), which
// is the case worth pinning anyway: the list's copy of the task stays on
// screen and the timeline says it couldn't load, rather than the sheet
// breaking.

Map<String, dynamic> task({String? projectId, Map<String, dynamic>? assignee, List<dynamic> questions = const []}) => {
      'id': 't1',
      'identifier': 'VIC-42',
      'title': 'Fix the flaky checkout test',
      'description': 'It fails on **CI** only.',
      'status': 'in_progress',
      'priority': 'high',
      'project_id': projectId,
      'labels': [],
      'assignee_type': assignee == null ? null : assignee['type'],
      'assignee_id': assignee?['id'],
      'assignee': assignee,
      'open_questions': questions,
      'created_at': '2026-09-01T10:00:00Z',
    };

Future<void> _pump(WidgetTester tester, Map<String, dynamic> t, {dynamic project}) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: Align(alignment: Alignment.bottomCenter, child: TaskDetailSheet(task: t, project: project, parentTask: null, subtasks: const []))),
  ));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  testWidgets('shows the task and a comment box, and survives a failed load', (tester) async {
    await _pump(tester, task(assignee: {'type': 'agent', 'id': 'a1', 'name': 'haiku-bot'}));

    expect(find.text('VIC-42'), findsOneWidget);
    expect(find.text('Fix the flaky checkout test'), findsOneWidget);
    expect(find.text('haiku-bot'), findsOneWidget);
    expect(find.text('Activity'), findsOneWidget);
    expect(find.textContaining("Couldn't load the activity"), findsOneWidget);
    // An unfiled task is the viewer's own, so they may comment.
    expect(find.byType(TextField), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a viewer on a shared board reads instead of typing', (tester) async {
    await _pump(tester, task(projectId: 'p1'), project: {'id': 'p1', 'name': 'Lighthouse', 'role': 'viewer'});

    expect(find.byType(TextField), findsNothing);
    expect(find.textContaining('Commenting needs commenter access'), findsOneWidget);
  });

  testWidgets('says whom an open question waits on', (tester) async {
    await _pump(tester, task(questions: [
      {
        'comment_id': 'c1',
        'addressee': {'type': 'user', 'id': 'u9', 'name': 'Ada'},
        'asked_by': {'type': 'agent', 'id': 'a1', 'name': 'haiku-bot'},
        'asked_at': '2026-09-01T10:00:00Z',
      },
    ]));

    expect(find.text('Waiting on Ada'), findsOneWidget);
  });

  testWidgets('with the keyboard up the sheet still stops below the status bar', (tester) async {
    // A notched phone: 402x874 with a 62 pt status area and a 336 pt keyboard.
    // Opened the way the app opens it: the modal route zeroes the top padding
    // inside the sheet, which a directly pumped sheet would not show.
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(402, 874);
    tester.view.padding = const FakeViewPadding(top: 62);
    tester.view.viewPadding = const FakeViewPadding(top: 62);
    tester.view.viewInsets = const FakeViewPadding(bottom: 336);
    addTearDown(tester.view.reset);

    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) => Scaffold(
          body: TextButton(
            onPressed: () => showTaskDetailSheet(context: context, task: task()..['description'] = List.filled(40, 'A long line.').join('\n\n'), project: null),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    // The sheet's own surface: the box with the rounded top.
    final surface = find.byWidgetPredicate((w) => w is Container && w.decoration is BoxDecoration && (w.decoration as BoxDecoration).borderRadius == const BorderRadius.vertical(top: Radius.circular(24.0)));
    expect(tester.getTopLeft(surface).dy, greaterThanOrEqualTo(62.0));
    expect(tester.getBottomLeft(surface).dy, 874.0 - 336.0);

    // Close it, so the poll timer is gone before the test ends.
    Navigator.of(tester.element(find.byType(TaskDetailSheet))).pop();
    await tester.pumpAndSettle();
  });
}
