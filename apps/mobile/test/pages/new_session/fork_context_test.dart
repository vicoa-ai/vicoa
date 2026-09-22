// What a fork does to the new-session composer: the first message it sends,
// and the chip that says what is attached.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/fork_transcript.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/new_session/fork_context_chip.dart';
import 'package:vicoa/pages/new_session/new_session_model.dart';

const _fork = ForkSessionContext(
  text: '<chat-history>\nearlier conversation\n</chat-history>',
  messageCount: 7,
  omittedCount: 2,
  sourceTitle: 'Earlier session',
);

Future<void> _pumpChip(
  WidgetTester tester, {
  required VoidCallback onRemove,
  ForkSessionContext fork = _fork,
}) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: ForkContextChip(fork: fork, onRemove: onRemove)),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('composeFirstMessage', () {
    test('puts the forked history above what the user typed', () {
      final model = NewSessionModel(forkContext: _fork);
      model.promptController.text = '  now finish the refactor  ';

      expect(
        model.composeFirstMessage(),
        '${_fork.text}\n\nnow finish the refactor',
      );
    });

    test('a fork alone is a valid first message', () {
      final model = NewSessionModel(forkContext: _fork);

      expect(model.composeFirstMessage(), _fork.text);
    });

    test('without a fork it is just the typed prompt', () {
      final model = NewSessionModel();
      model.promptController.text = 'start here';

      expect(model.composeFirstMessage(), 'start here');
    });

    test('removing the fork drops the history from the message', () {
      final model = NewSessionModel(forkContext: _fork);
      model.promptController.text = 'start here';

      model.removeForkContext();

      expect(model.forkContext, isNull);
      expect(model.composeFirstMessage(), 'start here');
    });
  });

  group('ForkContextChip', () {
    testWidgets('says how much history came along and where from',
        (tester) async {
      await _pumpChip(tester, onRemove: () {});

      expect(find.textContaining('7 messages'), findsOneWidget);
      expect(find.textContaining('Earlier session'), findsOneWidget);
      expect(find.textContaining('2 earlier messages omitted'), findsOneWidget);
    });

    testWidgets('opens the block itself on tap', (tester) async {
      await _pumpChip(tester, onRemove: () {});

      await tester.tap(find.byType(ForkContextChip));
      await tester.pumpAndSettle();

      expect(find.textContaining('earlier conversation'), findsOneWidget);
    });

    testWidgets('the × removes it', (tester) async {
      var removed = 0;
      await _pumpChip(tester, onRemove: () => removed++);

      await tester.tap(find.byIcon(Icons.close_rounded));
      await tester.pumpAndSettle();

      expect(removed, 1);
    });
  });
}
