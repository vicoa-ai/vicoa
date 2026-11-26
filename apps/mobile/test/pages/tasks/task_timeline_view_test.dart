import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:vicoa/components/agent_type_icon/agent_type_icon_widget.dart';
import 'package:vicoa/custom_code/utils/task_timeline.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/tasks/task_detail_model.dart';
import 'package:vicoa/pages/tasks/task_reactions.dart';
import 'package:vicoa/pages/tasks/task_session_list.dart';
import 'package:vicoa/pages/tasks/task_timeline_text.dart';
import 'package:vicoa/pages/tasks/task_timeline_view.dart';

Map<String, dynamic> person(String id, String? name, {String type = 'user'}) =>
    {'type': type, 'id': id, 'name': name, 'avatar_image_uri': null, 'emoji': null, 'updated_at': null};

Map<String, dynamic> comment(String id, String at, {String? parent, Map<String, dynamic>? author, String? body, bool deleted = false, Map<String, dynamic>? question}) => {
      'id': id,
      'parent_comment_id': parent,
      'author': author ?? person('u1', 'Nick'),
      'agent_instance_id': null,
      'body': deleted ? null : (body ?? id),
      'kind': 'comment',
      'reactions': [],
      'question': question,
      'created_at': at,
      'edited_at': null,
      'deleted_at': deleted ? at : null,
    };

const viewer = TaskViewer(id: 'u1', name: 'Nick');
final agent = person('a1', 'haiku-bot', type: 'agent');

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: SingleChildScrollView(child: child)),
  ));
  await tester.pump();
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  testWidgets('a deleted root stays as a tombstone with its replies under it', (tester) async {
    final entries = buildTimelineEntries([
      comment('root', '2026-09-01T10:00:00Z', deleted: true),
      comment('reply', '2026-09-01T11:00:00Z', parent: 'root', body: 'still here'),
    ], [], []);
    await _pump(tester, TaskTimelineView(entries: entries, viewer: viewer, sessionRefs: const {}, actions: TaskTimelineActions(onOpenSession: (_) {})));

    expect(find.text('This comment was deleted.'), findsOneWidget);
    expect(find.textContaining('still here', findRichText: true), findsOneWidget);
  });

  testWidgets('a thread ends in a reply row that aims the composer at it', (tester) async {
    TaskThread? replied;
    final entries = buildTimelineEntries([comment('root', '2026-09-01T10:00:00Z', author: agent, body: 'Which port?')], [], []);
    await _pump(
      tester,
      TaskTimelineView(entries: entries, viewer: viewer, sessionRefs: const {}, actions: TaskTimelineActions(onOpenSession: (_) {}, onReply: (t) => replied = t)),
    );

    await tester.tap(find.text('Leave a reply…'));
    expect(replied?.root['id'], 'root');
    // An agent's comment carries the badge, and no ⋯: it isn't the viewer's.
    expect(find.text('agent'), findsOneWidget);
    expect(find.byIcon(Icons.more_horiz_rounded), findsNothing);
  });

  testWidgets('no reply row and no reaction button for a viewer who cannot comment', (tester) async {
    final entries = buildTimelineEntries([comment('root', '2026-09-01T10:00:00Z')], [], []);
    await _pump(tester, TaskTimelineView(entries: entries, viewer: viewer, sessionRefs: const {}, actions: TaskTimelineActions(onOpenSession: (_) {})));

    expect(find.text('Leave a reply…'), findsNothing);
    expect(find.byIcon(Icons.add_reaction_outlined), findsNothing);
    expect(find.byIcon(Icons.more_horiz_rounded), findsNothing);
  });

  testWidgets('your own comment has a ⋯ menu; a note has a badge instead of its prefix', (tester) async {
    final entries = buildTimelineEntries([comment('mine', '2026-09-01T10:00:00Z', body: '/note remember the cache')], [], []);
    await _pump(
      tester,
      TaskTimelineView(entries: entries, viewer: viewer, sessionRefs: const {}, actions: TaskTimelineActions(onOpenSession: (_) {}, onEdit: (_) {}, onDelete: (_) {})),
    );

    expect(find.byIcon(Icons.more_horiz_rounded), findsOneWidget);
    expect(find.text('Note'), findsOneWidget);
    expect(find.textContaining('/note', findRichText: true), findsNothing);
  });

  testWidgets("an agent's open question says it waits on you", (tester) async {
    final entries = buildTimelineEntries([
      comment('q', '2026-09-01T10:00:00Z', author: agent, body: 'Ship it?', question: {'addressee': person('u1', 'Nick'), 'closed_at': null}),
    ], [], []);
    await _pump(tester, TaskTimelineView(entries: entries, viewer: viewer, sessionRefs: const {}, actions: TaskTimelineActions(onOpenSession: (_) {})));

    expect(find.text('Waiting on you'), findsOneWidget);
  });

  testWidgets('a burst of activity folds into one line that opens', (tester) async {
    Map<String, dynamic> row(String id, String action) => {'id': id, 'actor': person('u1', 'Nick'), 'action': action, 'details': {}, 'created_at': '2026-09-01T10:00:00Z'};
    final entries = buildTimelineEntries([], [row('a1', 'title_changed'), row('a2', 'description_changed')], []);
    await _pump(tester, TaskTimelineView(entries: entries, viewer: viewer, sessionRefs: const {}, actions: TaskTimelineActions(onOpenSession: (_) {})));

    expect(find.textContaining('made 2 changes', findRichText: true), findsOneWidget);
    expect(find.textContaining('edited the title', findRichText: true), findsNothing);
    await tester.tap(find.textContaining('made 2 changes', findRichText: true));
    await tester.pump();
    expect(find.textContaining('edited the title', findRichText: true), findsOneWidget);
  });

  testWidgets('a "via" line opens the session it names', (tester) async {
    String? opened;
    final c = comment('c', '2026-09-01T10:00:00Z', author: agent)..['agent_instance_id'] = 's1';
    final entries = buildTimelineEntries([c], [], []);
    await _pump(
      tester,
      TaskTimelineView(entries: entries, viewer: viewer, sessionRefs: const {'s1': {'id': 's1', 'name': 'Fix login', 'agent_type_name': 'claude'}}, actions: TaskTimelineActions(onOpenSession: (id) => opened = id)),
    );

    await tester.tap(find.text('via Fix login'));
    expect(opened, 's1');
  });

  testWidgets('reaction pills hug their content and share a row', (tester) async {
    await _pump(
      tester,
      TaskReactionRow(
        reactions: const [
          {'emoji': '👍', 'count': 2, 'reacted': true, 'reactors': []},
          {'emoji': '👀', 'count': 1, 'reacted': false, 'reactors': []},
        ],
        viewer: viewer,
        onToggle: (_) {},
      ),
    );

    final pills = find.byType(InkWell);
    expect(pills, findsNWidgets(3));
    for (var i = 0; i < 3; i++) {
      expect(tester.getSize(pills.at(i)).width, lessThan(90.0));
      expect(tester.getTopLeft(pills.at(i)).dy, tester.getTopLeft(pills.first).dy);
    }
  });

  testWidgets('a live session keeps its mark in line with the other sessions', (tester) async {
    Map<String, dynamic> session(String id, String status) => {'id': id, 'name': id, 'agent_type_name': 'my-bot', 'status': status, 'started_at': '2026-09-01T10:00:00Z', 'task_relations': ['linked']};
    final sessions = [session('live', 'ACTIVE'), session('idle', 'AWAITING_INPUT')];

    for (final child in [
      TaskTimelineView(entries: buildTimelineEntries([], [], sessions), viewer: viewer, sessionRefs: const {}, actions: TaskTimelineActions(onOpenSession: (_) {})),
      TaskSessionList(sessions: sessions, onOpenSession: (_) {}),
    ]) {
      await _pump(tester, child);
      final marks = find.byType(AgentTypeIconWidget);
      expect(marks, findsNWidgets(2));
      expect(tester.getSize(marks.at(0)), tester.getSize(marks.at(1)));
      expect(tester.getTopLeft(marks.at(0)).dx, tester.getTopLeft(marks.at(1)).dx);
    }
  });

  test('toggling a reaction adds, bumps and removes the viewer', () {
    final added = toggledReactions(const [], '👍', viewer);
    expect(added.single['count'], 1);
    expect(added.single['reacted'], isTrue);

    final bumped = toggledReactions([
      {'emoji': '👍', 'count': 1, 'reacted': false, 'reactors': [person('u2', 'Ada')]},
    ], '👍', viewer);
    expect(bumped.single['count'], 2);
    expect((bumped.single['reactors'] as List).first['id'], 'u1');

    expect(toggledReactions(added, '👍', viewer), isEmpty);
  });
}
