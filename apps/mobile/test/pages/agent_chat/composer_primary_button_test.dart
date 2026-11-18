// The composer's primary button: Send, doubling as Stop while a turn runs and
// nothing is typed (the web's `shouldShowStopButton` rule). Typing mid-turn
// must bring Send back so a follow-up can still be queued.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/agent_chat/components/composer_primary_button.dart';

Widget _app(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: Center(child: child)),
    );

void main() {
  group('shouldShowComposerStop', () {
    test('stop only while working with an empty composer', () {
      expect(shouldShowComposerStop(canSend: true, agentWorking: true, hasContent: false), isTrue);
    });
    test('typing mid-turn brings Send back', () {
      expect(shouldShowComposerStop(canSend: true, agentWorking: true, hasContent: true), isFalse);
    });
    test('idle agent shows Send', () {
      expect(shouldShowComposerStop(canSend: true, agentWorking: false, hasContent: false), isFalse);
    });
    test('closed session never shows Stop', () {
      expect(shouldShowComposerStop(canSend: false, agentWorking: true, hasContent: false), isFalse);
    });
  });

  group('ComposerPrimaryButton', () {
    Future<List<String>> tapButton(WidgetTester tester, {required bool showStop, bool isSending = false}) async {
      final taps = <String>[];
      await tester.pumpWidget(_app(ComposerPrimaryButton(
        isSending: isSending,
        showStop: showStop,
        onSend: () => taps.add('send'),
        onStop: () => taps.add('stop'),
      )));
      await tester.tap(find.byType(ComposerPrimaryButton));
      return taps;
    }

    testWidgets('Stop state shows the stop icon and interrupts', (tester) async {
      final taps = await tapButton(tester, showStop: true);
      expect(find.byIcon(Icons.stop_rounded), findsOneWidget);
      expect(find.byIcon(Icons.arrow_upward_rounded), findsNothing);
      expect(find.byTooltip('Stop current task'), findsOneWidget);
      expect(taps, ['stop']);
    });

    testWidgets('Send state shows the arrow and sends', (tester) async {
      final taps = await tapButton(tester, showStop: false);
      expect(find.byIcon(Icons.arrow_upward_rounded), findsOneWidget);
      expect(find.byIcon(Icons.stop_rounded), findsNothing);
      expect(taps, ['send']);
    });

    testWidgets('a send in flight shows a spinner and ignores taps', (tester) async {
      final taps = await tapButton(tester, showStop: true, isSending: true);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.byIcon(Icons.stop_rounded), findsNothing);
      expect(taps, isEmpty);
    });
  });
}
