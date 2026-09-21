// The queue bar + sheet's Steer affordance. Steer delivers a queued message
// into the agent's *running* turn (the web queue bar's Zap button); it is a
// per-agent capability, so the sheet only shows it when told `canSteer`, and
// a row being steered (POST in flight, or `queue.status == 'steer'` while the
// daemon delivers it) collapses to a spinner with no actions.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/agent_chat/components/queued_messages_bar.dart';

const _steerIcon = Icons.bolt_rounded;
const _revertIcon = Icons.undo_rounded;
const _cancelIcon = Icons.close_rounded;

Widget _app(Widget home) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

/// Pumps a chat-like page with an "open" button that shows the sheet over a
/// live item list, then opens it. [steering] mirrors the chat page's
/// in-flight-steer set; [items] is read through a provider so a test can
/// mutate it and tick [revision] the way a WS patch would.
Future<void> _openSheet(
  WidgetTester tester, {
  required List<QueuedMessageEntry> items,
  required ValueNotifier<int> revision,
  bool canSteer = false,
  Set<String> steering = const {},
  Set<String> cancelling = const {},
  List<String>? steered,
}) async {
  await tester.pumpWidget(_app(
    Scaffold(
      body: Builder(
        builder: (context) => ElevatedButton(
          onPressed: () => showQueuedMessagesSheet(
            context: context,
            revision: revision,
            itemsProvider: () => items,
            isCancelling: cancelling.contains,
            onCancel: (_) async {},
            onRevert: (_, __) async {},
            canSteer: canSteer,
            isSteering: steering.contains,
            onSteer: (id) async => steered?.add(id),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  // Not pumpAndSettle: a steering row's spinner animates forever, so settle
  // never returns. The sheet's slide-in is well under this.
  await _pumpThrough(tester);
}

/// Advance past the bottom-sheet animation without waiting for idle.
Future<void> _pumpThrough(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));
}

void main() {
  group('QueuedMessagesBar', () {
    testWidgets('shows the pending glyph while nothing is being steered',
        (tester) async {
      await tester.pumpWidget(_app(Scaffold(
        body: QueuedMessagesBar(
          items: const [QueuedMessageEntry(id: 'm1', text: 'first')],
          onTap: () {},
        ),
      )));
      expect(find.text('1 queued'), findsOneWidget);
      expect(find.byIcon(Icons.pending_outlined), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('swaps the glyph for a spinner while a row is being steered',
        (tester) async {
      await tester.pumpWidget(_app(Scaffold(
        body: QueuedMessagesBar(
          items: const [
            QueuedMessageEntry(id: 'm1', text: 'first', steering: true),
            QueuedMessageEntry(id: 'm2', text: 'second'),
          ],
          onTap: () {},
        ),
      )));
      await tester.pump();
      expect(find.text('2 queued'), findsOneWidget);
      expect(find.byIcon(Icons.pending_outlined), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });
  });

  group('queued messages sheet', () {
    testWidgets('hides Steer for an agent that only queues', (tester) async {
      await _openSheet(
        tester,
        items: const [QueuedMessageEntry(id: 'm1', text: 'first')],
        revision: ValueNotifier<int>(0),
        canSteer: false,
      );
      expect(find.text('first'), findsOneWidget);
      expect(find.byIcon(_steerIcon), findsNothing);
      expect(find.byIcon(_revertIcon), findsOneWidget);
      expect(find.byIcon(_cancelIcon), findsOneWidget);
    });

    testWidgets('offers Steer per row and reports the tapped id',
        (tester) async {
      final steered = <String>[];
      await _openSheet(
        tester,
        items: const [
          QueuedMessageEntry(id: 'm1', text: 'first'),
          QueuedMessageEntry(id: 'm2', text: 'second'),
        ],
        revision: ValueNotifier<int>(0),
        canSteer: true,
        steered: steered,
      );
      expect(find.byIcon(_steerIcon), findsNWidgets(2));
      // Revert + cancel are still there beside it.
      expect(find.byIcon(_revertIcon), findsNWidgets(2));
      expect(find.byIcon(_cancelIcon), findsNWidgets(2));

      await tester.tap(find.byIcon(_steerIcon).last);
      await tester.pump();
      expect(steered, ['m2']);
    });

    testWidgets('a row with a steer request in flight is spinner-only',
        (tester) async {
      await _openSheet(
        tester,
        items: const [
          QueuedMessageEntry(id: 'm1', text: 'first'),
          QueuedMessageEntry(id: 'm2', text: 'second'),
        ],
        revision: ValueNotifier<int>(0),
        canSteer: true,
        steering: {'m1'},
      );
      await tester.pump();
      // Only the untouched row keeps its three actions.
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.byIcon(_steerIcon), findsOneWidget);
      expect(find.byIcon(_revertIcon), findsOneWidget);
      expect(find.byIcon(_cancelIcon), findsOneWidget);
    });

    testWidgets('a row the daemon is delivering (`steer` status) is spinner-only, '
        'and gets its actions back if it is requeued', (tester) async {
      final revision = ValueNotifier<int>(0);
      final items = <QueuedMessageEntry>[
        const QueuedMessageEntry(id: 'm1', text: 'first', steering: true),
      ];
      await _openSheet(tester, items: items, revision: revision, canSteer: true);
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.byIcon(_steerIcon), findsNothing);
      expect(find.byIcon(_revertIcon), findsNothing);
      expect(find.byIcon(_cancelIcon), findsNothing);

      // The turn could not be steered: the WS patch flips it back to `queued`.
      items[0] = const QueuedMessageEntry(id: 'm1', text: 'first');
      revision.value++;
      await _pumpThrough(tester);
      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.byIcon(_steerIcon), findsOneWidget);
      expect(find.byIcon(_revertIcon), findsOneWidget);
      expect(find.byIcon(_cancelIcon), findsOneWidget);
    });

    testWidgets('closes on its own once the steered message is consumed',
        (tester) async {
      final revision = ValueNotifier<int>(0);
      final items = <QueuedMessageEntry>[
        const QueuedMessageEntry(id: 'm1', text: 'first', steering: true),
      ];
      await _openSheet(tester, items: items, revision: revision, canSteer: true);
      await tester.pump();
      expect(find.text('first'), findsOneWidget);

      items.clear();
      revision.value++;
      // The sheet pops itself on the next frame; ride out the slide-out.
      await _pumpThrough(tester);
      expect(find.text('first'), findsNothing);
      expect(find.text('open'), findsOneWidget);
    });
  });
}
