import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:vicoa/custom_code/utils/task_mentions.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/tasks/task_comment_composer.dart';

const _agentId = '11111111-1111-1111-1111-111111111111';

Future<void> _pump(WidgetTester tester, TextEditingController controller, FocusNode focus, {TaskComposerTarget target = TaskComposerTarget.comment}) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(
      body: Align(
        alignment: Alignment.bottomCenter,
        child: TaskCommentComposer(
          controller: controller,
          focusNode: focus,
          target: target,
          targetName: 'Ada',
          wake: const WakeContext(inThread: false, assigneeAgentId: _agentId),
          agents: const [{'id': _agentId, 'name': 'Codex'}],
          people: const [],
          agentNames: const {_agentId: 'Codex'},
          viewerId: 'u1',
          onSubmit: (_) async => true,
          onClearTarget: () {},
        ),
      ),
    ),
  ));
  await tester.pump();
}

/// What the phone's keyboard does: write into whatever field it is connected
/// to. (`enterText` would reconnect first and hide a dropped connection.)
Future<void> _keyboardWrites(WidgetTester tester, String text) async {
  tester.testTextInput.updateEditingValue(TextEditingValue(text: text, selection: TextSelection.collapsed(offset: text.length)));
  await tester.pump();
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  for (final target in [TaskComposerTarget.comment, TaskComposerTarget.reply]) {
    testWidgets('the keyboard stays connected while the @ picker opens and closes ($target)', (tester) async {
      final controller = TextEditingController();
      final focus = FocusNode();
      addTearDown(controller.dispose);
      addTearDown(focus.dispose);
      await _pump(tester, controller, focus, target: target);

      await tester.tap(find.byType(TextField));
      await tester.pump();
      final field = tester.state(find.byType(EditableText));

      await _keyboardWrites(tester, '@');
      expect(find.text('Codex'), findsOneWidget);
      expect(tester.state(find.byType(EditableText)), same(field));
      expect(tester.testTextInput.isVisible, isTrue);

      await tester.tap(find.text('Codex'));
      await tester.pump();
      expect(controller.text, '@Codex ');

      await _keyboardWrites(tester, '@Codex please look');
      expect(controller.text, '@Codex please look');

      await _keyboardWrites(tester, '/note just for me');
      expect(tester.state(find.byType(EditableText)), same(field));
    });
  }
}
