// The project picker sheet's sizing. A fixed 65%-height column used to keep
// its lists under the keyboard and just push everything up by the inset, which
// on a tall keyboard left less room than the fixed rows needed — a RenderFlex
// overflow (by a fraction of a pixel on a 402×874 screen, by more on smaller
// ones). Now the lists collapse while typing and the sheet rides the keyboard;
// at rest the sheet is as tall as its content, capped at 65%.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/project_paths.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/new_session/components/directory_picker_sheet.dart';

const _screen = Size(402.0, 874.0);
const _keyboard = 336.0;
const _homeIndicator = 34.0;

List<ProjectPickerEntry> _projects([int count = 6]) => [
      for (var i = 0; i < count; i++)
        ProjectPickerEntry(
          project: {'id': 'id-$i', 'name': 'project $i'},
          path: '/Users/me/src/project-$i',
        ),
    ];

/// The sheet's own box (the AnimatedSize wraps exactly the sheet container).
Rect _sheetRect(WidgetTester tester) => tester.getRect(find.byType(AnimatedSize));

Future<void> _openSheet(WidgetTester tester, {int projectCount = 6}) async {
  tester.view.physicalSize = _screen;
  tester.view.devicePixelRatio = 1.0;
  tester.view.padding = const FakeViewPadding(bottom: _homeIndicator);
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => showDirectoryPickerSheet(
              context: context,
              initial: '~/src/project-0',
              projects: _projects(projectCount),
              selectedProjectId: 'id-0',
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

/// Raise / lower the software keyboard: the inset covers the home indicator,
/// so the safe-area padding goes to zero with it, as on a device.
Future<void> _setKeyboard(WidgetTester tester, {required bool up}) async {
  tester.view.viewInsets = FakeViewPadding(bottom: up ? _keyboard : 0.0);
  tester.view.padding = FakeViewPadding(bottom: up ? 0.0 : _homeIndicator);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('keyboard up: lists collapse, input sits on the keyboard, no overflow',
      (tester) async {
    await _openSheet(tester);
    expect(find.text('Projects'), findsOneWidget);
    expect(find.text('project 0'), findsOneWidget);

    await _setKeyboard(tester, up: true);

    // The overflow used to surface here as a FlutterError from layout.
    expect(tester.takeException(), isNull);
    expect(find.text('Projects'), findsNothing);
    expect(find.text('project 0'), findsNothing);
    expect(find.text('Folder'), findsOneWidget);

    // The input is the last thing before the bottom padding: fully visible,
    // clear of the keyboard.
    final input = tester.getRect(find.byType(TextField));
    expect(input.bottom, lessThanOrEqualTo(_screen.height - _keyboard - 16.0));
  });

  testWidgets('keyboard down again: the projects list comes back',
      (tester) async {
    await _openSheet(tester);
    final resting = _sheetRect(tester);
    await _setKeyboard(tester, up: true);
    await _setKeyboard(tester, up: false);

    expect(tester.takeException(), isNull);
    expect(find.text('Projects'), findsOneWidget);
    expect(find.text('project 0'), findsOneWidget);
    // Back to the resting size, the input clear of the home indicator.
    expect(_sheetRect(tester), resting);
    final input = tester.getRect(find.byType(TextField));
    expect(input.bottom, lessThanOrEqualTo(_screen.height - _homeIndicator - 16.0));
    expect(find.text('Project'), findsOneWidget); // the sheet title
  });

  testWidgets('a couple of projects make a short sheet; no filler below the input',
      (tester) async {
    await _openSheet(tester, projectCount: 2);
    expect(tester.takeException(), isNull);

    final sheet = _sheetRect(tester);
    expect(sheet.height, lessThan(_screen.height * 0.65));
    // The input is the last thing: below the field sit only its own 4px inner
    // padding and the sheet's safe-area padding — no filler.
    final input = tester.getRect(find.byType(TextField));
    expect(sheet.bottom - input.bottom, closeTo(4.0 + 16.0 + _homeIndicator, 0.5));
  });

  testWidgets('a long list hits the 65% cap and scrolls inside it',
      (tester) async {
    await _openSheet(tester, projectCount: 40);
    expect(tester.takeException(), isNull);

    final sheet = _sheetRect(tester);
    expect(sheet.height, closeTo(_screen.height * 0.65, 0.5));
    // The input stays put below the list; the list scrolls to reach the tail.
    final input = tester.getRect(find.byType(TextField));
    expect(find.text('project 39'), findsNothing);
    await tester.drag(find.text('project 0'), const Offset(0.0, -3000.0));
    await tester.pumpAndSettle();
    expect(find.text('project 39'), findsOneWidget);
    expect(tester.getRect(find.byType(TextField)), input);
  });
}
