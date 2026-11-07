// The composer's "N annotations" pill and the sheets it hangs off.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/chat_annotations.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/agent_chat/components/annotations_chip.dart';

class _Composer with ChatAnnotationsMixin {
  VoidCallback? listener;

  @override
  VoidCallback? get annotationsOnStateChanged => listener;
}

Future<_Composer> _pump(WidgetTester tester, List<String> quotes) async {
  final composer = _Composer();
  for (final quote in quotes) {
    composer.addAnnotation(quote);
  }
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(
      body: Center(
        child: StatefulBuilder(builder: (context, setState) {
          composer.listener = () => setState(() {});
          return composer.annotations.isEmpty ? const Text('empty') : AnnotationsChip(composer: composer);
        }),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return composer;
}

Future<void> _openList(WidgetTester tester, String label) async {
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('counts its annotations, in the singular too', (tester) async {
    await _pump(tester, ['one']);
    expect(find.text('1 annotation'), findsOneWidget);
  });

  testWidgets('the × drops them all', (tester) async {
    final composer = await _pump(tester, ['one', 'two']);
    expect(find.text('2 annotations'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.close_rounded));
    await tester.pumpAndSettle();

    expect(composer.annotations, isEmpty);
    expect(find.text('empty'), findsOneWidget);
  });

  testWidgets('the list shows each quote; a comment is added in place and saved', (tester) async {
    final composer = await _pump(tester, ['first quote', 'second quote']);
    await _openList(tester, '2 annotations');

    expect(find.text('first quote'), findsOneWidget);
    expect(find.text('second quote'), findsOneWidget);
    expect(find.text('Add comment'), findsNWidgets(2));

    await tester.tap(find.text('Add comment').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '  why this?  ');
    await tester.tap(find.byIcon(Icons.check_rounded));
    await tester.pumpAndSettle();

    expect(composer.annotations.first.comment, 'why this?');
    expect(find.text('why this?'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('tapping a comment edits it; closing the sheet keeps what was typed', (tester) async {
    final composer = await _pump(tester, ['quote']);
    composer.updateAnnotationComment(composer.annotations.single.id, 'old note');
    await tester.pump();
    await _openList(tester, '1 annotation');

    await tester.tap(find.text('old note'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, 'old note'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'new note');

    Navigator.of(tester.element(find.byType(TextField))).pop();
    await tester.pumpAndSettle();

    expect(composer.annotations.single.comment, 'new note');
  });

  testWidgets('starting another row keeps the edit in progress', (tester) async {
    final composer = await _pump(tester, ['one', 'two']);
    await _openList(tester, '2 annotations');

    await tester.tap(find.text('Add comment').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'note on one');
    await tester.tap(find.text('Add comment'));
    await tester.pumpAndSettle();

    expect(composer.annotations.first.comment, 'note on one');
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('deleting a row removes it; deleting the last closes the sheet', (tester) async {
    final composer = await _pump(tester, ['one', 'two']);
    await _openList(tester, '2 annotations');

    await tester.tap(find.byIcon(Icons.delete_outline_rounded).first);
    await tester.pumpAndSettle();
    expect(composer.annotations.single.quote, 'two');
    expect(find.text('one'), findsNothing);

    await tester.tap(find.byIcon(Icons.delete_outline_rounded));
    await tester.pumpAndSettle();
    expect(composer.annotations, isEmpty);
    expect(find.byIcon(Icons.delete_outline_rounded), findsNothing);
  });

  testWidgets('the list rides the keyboard, clear of the status bar, without overflowing', (tester) async {
    tester.view.physicalSize = const Size(1170, 2532);
    tester.view.devicePixelRatio = 3.0;
    tester.view.padding = const FakeViewPadding(top: 180.0);
    tester.view.viewInsets = const FakeViewPadding(bottom: 1000.0);
    addTearDown(tester.view.reset);
    final composer = await _pump(tester, [for (var i = 0; i < 12; i++) 'quote number $i is long enough to wrap onto a second line of the sheet']);
    await _openList(tester, '${composer.annotations.length} annotations');

    await tester.tap(find.text('Add comment').first);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    final screenHeight = tester.view.physicalSize.height / 3.0;
    expect(tester.getBottomLeft(find.byType(TextField)).dy, lessThanOrEqualTo(screenHeight - 1000.0 / 3.0));
    expect(tester.getTopLeft(find.byType(ListView)).dy, greaterThan(180.0 / 3.0));
  });

  group('comment sheet', () {
    Future<AnnotationCommentResult?> open(WidgetTester tester, {required bool canSend, required Future<void> Function() act}) async {
      AnnotationCommentResult? result;
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: Builder(builder: (context) => TextButton(
            onPressed: () async => result = await showAnnotationCommentSheet(context, quote: 'the passage', canSend: canSend),
            child: const Text('open'),
          )),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      expect(find.text('the passage'), findsOneWidget);
      await act();
      await tester.pumpAndSettle();
      return result;
    }

    testWidgets('✓ adds the comment without sending', (tester) async {
      final result = await open(tester, canSend: true, act: () async {
        await tester.enterText(find.byType(TextField), 'why?');
        await tester.tap(find.byIcon(Icons.check_rounded));
      });
      expect(result!.comment, 'why?');
      expect(result.send, isFalse);
    });

    testWidgets('the arrow adds it and asks to send', (tester) async {
      final result = await open(tester, canSend: true, act: () async {
        await tester.enterText(find.byType(TextField), 'why?');
        await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
      });
      expect(result!.comment, 'why?');
      expect(result.send, isTrue);
    });

    testWidgets('tapping away keeps what was typed', (tester) async {
      final result = await open(tester, canSend: true, act: () async {
        await tester.enterText(find.byType(TextField), 'half a thought');
        await tester.tapAt(const Offset(10.0, 10.0));
      });
      expect(result!.comment, 'half a thought');
      expect(result.send, isFalse);
    });

    testWidgets('there is no arrow when the composer cannot send', (tester) async {
      await open(tester, canSend: false, act: () async {
        expect(find.byIcon(Icons.arrow_upward_rounded), findsNothing);
        await tester.tap(find.byIcon(Icons.check_rounded));
      });
    });

    testWidgets('rides the keyboard without overflowing', (tester) async {
      tester.view.physicalSize = const Size(1170, 2532);
      tester.view.devicePixelRatio = 3.0;
      tester.view.viewInsets = const FakeViewPadding(bottom: 1000.0);
      addTearDown(tester.view.reset);
      await open(tester, canSend: true, act: () async {
        final field = tester.getBottomLeft(find.byType(TextField));
        expect(field.dy, lessThan(tester.view.physicalSize.height / 3.0 - 1000.0 / 3.0));
        await tester.tap(find.byIcon(Icons.check_rounded));
      });
      expect(tester.takeException(), isNull);
    });
  });
}
