// What a selection in the transcript yields: the text it quotes and copies, and
// the toolbar it opens.

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/widgets/syntax_highlighted_code_block.dart';
import 'package:vicoa/custom_code/widgets/transcript_selection.dart';
import 'package:vicoa/l10n/app_localizations.dart';

const _addToChat = 'Add to chat';
const _continue = 'Continue in new session';

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  ValueChanged<String>? onAddToChat,
  ValueChanged<String>? onContinue,
  bool scoped = true,
}) async {
  final body = scoped ? TranscriptSelectionActions(onAddToChat: onAddToChat, onContinueInNewSession: onContinue, child: child) : child;
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: body),
  ));
  await tester.pumpAndSettle();
}

/// Long-press selects the first word of [text] and opens the toolbar, as on a
/// phone. Not the centre: that can be past the glyphs, or on a space.
Future<void> _longPress(WidgetTester tester, String text) async {
  final gesture = await tester.startGesture(tester.getTopLeft(find.text(text)) + const Offset(4.0, 4.0), kind: PointerDeviceKind.touch);
  await tester.pump(const Duration(milliseconds: 600));
  await gesture.up();
  await tester.pumpAndSettle();
}

/// Taps the toolbar's Select all, the way to take a whole message on a phone.
Future<void> _selectAll(WidgetTester tester) async {
  await tester.tap(find.text('Select all'));
  await tester.pumpAndSettle();
}

Future<String?> _clipboardAfterCopy(WidgetTester tester) async {
  String? copied;
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'Clipboard.setData') copied = (call.arguments as Map)['text'] as String;
    return null;
  });
  addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
  await tester.tap(find.text('Copy'));
  await tester.pumpAndSettle();
  return copied;
}

void main() {
  group('selected text keeps its blocks', () {
    testWidgets('stacked blocks are a line apart, not run together', (tester) async {
      String? quote;
      await _pump(
        tester,
        const TranscriptSelectionArea(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('First paragraph.'), SizedBox(height: 12.0), Text('Second paragraph.')])),
        onAddToChat: (text) => quote = text,
      );
      await _longPress(tester, 'First paragraph.');
      await _selectAll(tester);
      await tester.tap(find.text(_addToChat));
      await tester.pumpAndSettle();

      expect(quote, 'First paragraph.\nSecond paragraph.');
    });

    testWidgets('a bullet and its text share a line, and Copy gets the same text', (tester) async {
      await _pump(
        tester,
        const TranscriptSelectionArea(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [Text('•'), Expanded(child: Text('one'))]),
            Row(children: [Text('•'), Expanded(child: Text('two'))]),
          ]),
        ),
        onAddToChat: (_) {},
      );
      await _longPress(tester, 'one');
      await _selectAll(tester);

      expect(await _clipboardAfterCopy(tester), '• one\n• two');
    });
  });

  group('the toolbar', () {
    testWidgets('offers both actions after Copy, and hands over the normalised quote', (tester) async {
      String? continued;
      await _pump(tester, const TranscriptSelectionArea(child: Text('hello world')), onAddToChat: (_) {}, onContinue: (text) => continued = text);
      await _longPress(tester, 'hello world');

      final labels = tester.widgetList<Text>(find.descendant(of: find.byType(AdaptiveTextSelectionToolbar), matching: find.byType(Text))).map((t) => t.data).toList();
      expect(labels.indexOf('Copy'), lessThan(labels.indexOf(_addToChat)));
      expect(labels.indexOf(_addToChat), lessThan(labels.indexOf(_continue)));

      await tester.tap(find.text(_continue));
      await tester.pumpAndSettle();

      expect(continued, isNotEmpty);
      expect('hello world'.contains(continued!), isTrue);
      expect(find.byType(AdaptiveTextSelectionToolbar), findsNothing, reason: 'the menu is gone once it acted');
    });

    testWidgets('a null action hides its row: an ended session cannot add to chat', (tester) async {
      await _pump(tester, const TranscriptSelectionArea(child: Text('hello')), onContinue: (_) {});
      await _longPress(tester, 'hello');

      expect(find.text(_addToChat), findsNothing);
      expect(find.text(_continue), findsOneWidget);
    });

    testWidgets('outside a chat it is the plain system menu', (tester) async {
      await _pump(tester, const TranscriptSelectionArea(child: Text('hello')), scoped: false);
      await _longPress(tester, 'hello');

      expect(find.text('Copy'), findsOneWidget);
      expect(find.text(_addToChat), findsNothing);
      expect(find.text(_continue), findsNothing);
    });

    testWidgets('a code block offers the actions too, on its own selection', (tester) async {
      String? quote;
      await _pump(tester, SelectableHighlightView('const answer = 42;', language: 'plaintext', theme: const {}), onAddToChat: (text) => quote = text);

      final gesture = await tester.startGesture(tester.getCenter(find.byType(SelectableHighlightView)), kind: PointerDeviceKind.touch);
      await tester.pump(const Duration(milliseconds: 600));
      await gesture.up();
      await tester.pumpAndSettle();
      await tester.tap(find.text(_addToChat));
      await tester.pumpAndSettle();

      expect(quote, isNotEmpty);
      expect('const answer = 42;'.contains(quote!), isTrue);
    });
  });
}
