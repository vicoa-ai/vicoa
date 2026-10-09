// The Home project group header's leading icon, as the web sidebar draws it:
// a folder that opens with the group, a dashed square for No project, the
// project's emoji when it has one, and the owner's avatar on someone else's
// project.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:vicoa/components/principal_avatar/principal_avatar.dart';
import 'package:vicoa/pages/home/project_group_icon.dart';
import 'package:vicoa/pages/home/project_groups.dart';
import 'package:vicoa/pages/tasks/task_glyphs.dart';

Future<void> _pump(WidgetTester tester, SessionGroup group, {bool open = true}) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: Center(child: ProjectGroupIcon(group: group, open: open))),
  ));
  await tester.pump();
}

/// The default folder glyph on screen, open or closed.
Finder _folder({required bool open}) => find.byWidgetPredicate(
    (w) => w is CustomPaint && w.painter is ProjectFolderPainter && (w.painter as ProjectFolderPainter).open == open);

SessionGroup _group(Map<String, dynamic>? project, {String key = 'p-1'}) =>
    SessionGroup(key: key, label: 'app', sessions: const [], isProject: true, project: project);

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  testWidgets('a project without an image or emoji is a folder that opens with the group', (tester) async {
    await _pump(tester, _group({'id': 'p-1', 'name': 'app'}));
    expect(_folder(open: true), findsOneWidget);

    await _pump(tester, _group({'id': 'p-1', 'name': 'app'}), open: false);
    expect(_folder(open: false), findsOneWidget);
  });

  testWidgets('a folder no project claims is still a folder', (tester) async {
    await _pump(tester, _group(null, key: 'app'));
    expect(_folder(open: true), findsOneWidget);
  });

  testWidgets('No project is not a folder', (tester) async {
    final groups = groupSessionsByProject([{'id': 's', 'project': null}], const []);
    await _pump(tester, groups.single);
    expect(_folder(open: true), findsNothing);
    expect(_folder(open: false), findsNothing);
    expect(find.byType(CustomPaint), findsWidgets);
  });

  testWidgets('the emoji wins over the folder', (tester) async {
    await _pump(tester, _group({'id': 'p-1', 'name': 'app', 'icon': '🚀'}));
    expect(find.text('🚀'), findsOneWidget);
  });

  testWidgets("someone else's project carries its owner's avatar", (tester) async {
    await _pump(tester, _group({'id': 'p-1', 'name': 'app'}));
    expect(find.byType(PrincipalAvatar), findsNothing);

    await _pump(tester, _group({
      'id': 'p-1',
      'name': 'app',
      'owner': {'type': 'user', 'id': 'u-2', 'name': 'Ada'},
    }));
    expect(find.byType(PrincipalAvatar), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
