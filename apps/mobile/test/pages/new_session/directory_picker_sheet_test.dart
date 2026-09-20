// The project picker sheet under a keyboard. A fixed 65%-height column used
// to keep its lists and just push everything up by the keyboard inset, which
// on a tall keyboard left less room than the fixed rows needed — a RenderFlex
// overflow (by a fraction of a pixel on a 402×874 screen, by more on smaller
// ones). Now the lists collapse while typing and the sheet rides the keyboard.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/project_paths.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/new_session/components/directory_picker_sheet.dart';

const _screen = Size(402.0, 874.0);
const _keyboard = 336.0;
const _homeIndicator = 34.0;

List<ProjectPickerEntry> _projects() => [
      for (var i = 0; i < 6; i++)
        ProjectPickerEntry(
          project: {'id': 'id-$i', 'name': 'project $i'},
          path: '/Users/me/src/project-$i',
        ),
    ];

Future<void> _openSheet(WidgetTester tester) async {
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
              projects: _projects(),
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

  testWidgets('keyboard down again: the projects list comes back at full height',
      (tester) async {
    await _openSheet(tester);
    await _setKeyboard(tester, up: true);
    await _setKeyboard(tester, up: false);

    expect(tester.takeException(), isNull);
    expect(find.text('Projects'), findsOneWidget);
    expect(find.text('project 0'), findsOneWidget);
    // Back to the resting 65% height, the input clear of the home indicator.
    final input = tester.getRect(find.byType(TextField));
    expect(input.bottom, lessThanOrEqualTo(_screen.height - _homeIndicator - 16.0));
    expect(find.text('Project'), findsOneWidget); // the sheet title
  });
}
