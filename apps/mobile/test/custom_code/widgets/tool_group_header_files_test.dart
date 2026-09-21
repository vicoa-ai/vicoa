// The edited-file items flowing in a collapsed tool run / sub-agent header
// and the tappable path on an expanded edit row (`tool_use_group.dart`,
// `subagent_group.dart`, `markdown_text_builder.dart`): what the header
// shows, and that an item's tap opens the file rather than toggling the run.

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:vicoa/custom_code/widgets/subagent_group.dart';
import 'package:vicoa/custom_code/widgets/tool_use_group.dart';

const _bash = 'Using tool: **Bash** - `flutter test`';
const _editA1 = 'Using tool: **Edit** - `lib/a.dart`\n\n```diff\n-x\n+y\n```';
const _editA2 = 'Using tool: **Edit** - `lib/a.dart`\n\n```diff\n+z\n```';
const _writeB = 'Using tool: **Write** - `lib/b.dart`\n\n```diff\n+p\n+q\n```';
const _editOutside = 'Using tool: **Edit** - `/etc/hosts`';

class _Host extends StatefulWidget {
  const _Host({required this.child});
  final Widget Function(BuildContext context, bool expanded, VoidCallback toggle) child;
  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> {
  bool expanded = false;
  int toggles = 0;
  @override
  Widget build(BuildContext context) => widget.child(context, expanded, () {
        setState(() {
          expanded = !expanded;
          toggles++;
        });
      });
}

Future<_HostState> _pump(
  WidgetTester tester, {
  required List<String> contents,
  OpenFileCallback? onOpenFile,
  bool subagent = false,
  double width = 360.0,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: width,
          child: _Host(
            child: (context, expanded, toggle) => subagent
                ? SubagentGroup(
                    subagentType: 'Explore',
                    contents: contents,
                    expanded: expanded,
                    onToggle: toggle,
                    onOpenFile: onOpenFile,
                  )
                : ToolUseGroup(
                    contents: contents,
                    expanded: expanded,
                    onToggle: toggle,
                    onOpenFile: onOpenFile,
                  ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  return tester.state<_HostState>(find.byType(_Host));
}

/// The basenames flowing in the header, in order.
List<String> _listedFiles(WidgetTester tester) => [
      for (final e in find.byType(EditedFilesFlow).evaluate())
        for (final t in find.descendant(of: find.byWidget(e.widget), matching: find.byType(Text)).evaluate())
          if ((t.widget as Text).data case final name? when name.endsWith('.dart') || name == 'hosts') name,
    ];

/// A rendered `+N -M` (one rich text per file).
Finder _stat(String text) =>
    find.byWidgetPredicate((w) => w is RichText && w.text.toPlainText().trim() == text);

/// A listed file's item (the whole item is the tap target).
Finder _fileItem(String name) => find.descendant(of: find.byType(EditedFilesFlow), matching: find.text(name));

/// The rich text containing [substring] — a row header line.
Finder _textWith(String substring) => find.byWidgetPredicate(
      (w) => w is RichText && w.text.toPlainText().contains(substring),
    );

/// Taps the middle of [substring] within the rich text that contains it, so
/// the tap lands on that span's own recognizer.
Future<void> _tapSpan(WidgetTester tester, String substring) async {
  final paragraph = tester.renderObject<RenderParagraph>(_textWith(substring));
  final text = paragraph.text.toPlainText();
  final index = text.indexOf(substring) + substring.length ~/ 2;
  final caret = paragraph.getOffsetForCaret(TextPosition(offset: index), Rect.zero);
  final lineHeight = paragraph.getFullHeightForCaret(TextPosition(offset: index));
  await tester.tapAt(paragraph.localToGlobal(caret + Offset(0, lineHeight / 2)));
  await tester.pump();
}

void main() {
  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  group('collapsed tool run', () {
    testWidgets('keeps its label and flows one item per edited file after '
        'it, repeats folded, stats summed', (tester) async {
      await _pump(
        tester,
        contents: const [_bash, _editA1, _editA2, _writeB],
        onOpenFile: (_, __) {},
      );
      expect(find.text('Run a command, edit a file, write a file'), findsOneWidget);
      // a.dart was edited twice: one item, +2 -1 across both edits; b.dart
      // was written once, +2 and no deletions.
      expect(_listedFiles(tester), ['a.dart', 'b.dart']);
      expect(_stat('+2 -1'), findsOneWidget);
      expect(_stat('+2'), findsOneWidget);
    });

    testWidgets('an all-edit run keeps its label too', (tester) async {
      await _pump(tester, contents: const [_editA1, _writeB], onOpenFile: (_, __) {});
      expect(find.text('Edit a file, write a file'), findsOneWidget);
      expect(_listedFiles(tester), ['a.dart', 'b.dart']);
    });

    testWidgets('a run with no edits keeps its plain one-line label', (tester) async {
      await _pump(tester, contents: const [_bash, 'Using tool: **Read** - `lib/a.dart`'], onOpenFile: (_, __) {});
      expect(find.text('Run a command, read a file'), findsOneWidget);
      expect(find.byType(EditedFilesFlow), findsNothing);
    });

    testWidgets('tapping a file item opens the file (cwd-relative path + '
        'basename) and does not toggle the run', (tester) async {
      final opened = <String>[];
      final host = await _pump(
        tester,
        contents: const [_bash, _editA1, _writeB],
        onOpenFile: (path, name) => opened.add('$path|$name'),
      );
      await tester.tap(_fileItem('b.dart'));
      await tester.pump();
      expect(opened, ['lib/b.dart|b.dart']);
      expect(host.toggles, 0);
      expect(host.expanded, isFalse);
    });

    testWidgets('tapping the label still toggles the run', (tester) async {
      final host = await _pump(
        tester,
        contents: const [_bash, _editA1],
        onOpenFile: (_, __) {},
      );
      await tester.tap(find.text('Run a command, edit a file'));
      await tester.pump();
      expect(host.toggles, 1);
      expect(host.expanded, isTrue);
    });

    testWidgets('with nowhere to open a file the items are inert and a tap '
        'falls through to the run toggle', (tester) async {
      final host = await _pump(tester, contents: const [_bash, _editA1]);
      expect(_listedFiles(tester), ['a.dart']);
      await tester.tap(_fileItem('a.dart'));
      await tester.pump();
      expect(host.toggles, 1);
    });

    testWidgets('a file outside the project is shown but inert', (tester) async {
      final opened = <String>[];
      final host = await _pump(
        tester,
        contents: const [_bash, _editOutside],
        onOpenFile: (path, name) => opened.add(path),
      );
      expect(_listedFiles(tester), ['hosts']);
      await tester.tap(_fileItem('hosts'));
      await tester.pump();
      expect(opened, isEmpty);
      expect(host.toggles, 1);
    });
  });

  group('header flow layout', () {
    testWidgets('an item that fits shares the label\'s line; one that does not '
        'moves whole to the next line', (tester) async {
      // The test font renders every glyph an em wide, so give the fitting
      // case the room a real font would need far less of (the default 800px
      // test surface clamps the host, so widen the surface too).
      tester.view.physicalSize = const Size(1400.0, 800.0);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await _pump(tester, contents: const [_bash, _editA1, _writeB], onOpenFile: (_, __) {}, width: 1100.0);
      final label = tester.getRect(find.text('Run a command, edit a file, write a file'));
      // Same line: centred on the label (the 15pt label is a hair taller).
      expect(tester.getRect(_fileItem('a.dart')).center.dy, closeTo(label.center.dy, 1.0));
      expect(tester.getRect(_fileItem('b.dart')).center.dy, closeTo(label.center.dy, 1.0));

      final long = 'Using tool: **Edit** - `lib/${'a_component_with_a_long_name_' * 2}.dart`';
      await _pump(tester, contents: [_bash, _editA1, long], onOpenFile: (_, __) {});
      final label2 = tester.getRect(find.text('Run a command, edit 2 files'));
      // The whole item (icon + name + stat) wraps, so measure its row.
      final item = tester.getRect(
        find.ancestor(of: find.textContaining('a_component'), matching: find.byType(Row)).first,
      );
      expect(item.top, greaterThan(label2.bottom - 1));
      expect(item.left, closeTo(label2.left, 1.0));
    });

    testWidgets('a basename wider than the header ellipsizes instead of overflowing', (tester) async {
      final long = 'Using tool: **Edit** - `lib/${'very_long_component_name_' * 5}.dart`';
      await _pump(tester, contents: [_bash, long], onOpenFile: (_, __) {});
      expect(tester.takeException(), isNull);
      expect(tester.getRect(find.byType(EditedFilesFlow)).width, lessThanOrEqualTo(360.0));
    });

    testWidgets('items beyond $kMaxInlineFiles fold into "+N more", whose tap '
        'reveals them in place without expanding the run', (tester) async {
      final edits = [
        for (var i = 0; i < kMaxInlineFiles + 3; i++) 'Using tool: **Edit** - `lib/f$i.dart`',
      ];
      final host = await _pump(tester, contents: edits, onOpenFile: (_, __) {});
      expect(_listedFiles(tester), hasLength(kMaxInlineFiles));
      expect(find.text('+3 more'), findsOneWidget);
      await tester.tap(find.text('+3 more'));
      await tester.pumpAndSettle();
      expect(host.toggles, 0);
      expect(host.expanded, isFalse);
      expect(_listedFiles(tester), hasLength(kMaxInlineFiles + 3));
      expect(find.text('+3 more'), findsNothing);
    });
  });

  group('expanded edit row', () {
    testWidgets('the path on an edit row opens the file', (tester) async {
      final opened = <String>[];
      final host = await _pump(
        tester,
        contents: const [_bash, _editA1],
        onOpenFile: (path, name) => opened.add('$path|$name'),
      );
      await tester.tap(find.text('Run a command, edit a file'));
      await tester.pumpAndSettle();
      expect(host.expanded, isTrue);
      // The header item names the file by basename with its +N -M; the tool
      // row carries the full relative path with the same +N -M behind it.
      expect(_stat('+1 -1'), findsOneWidget);
      expect(_textWith('lib/a.dart +1 -1'), findsOneWidget);
      await _tapSpan(tester, 'lib/a.dart');
      expect(opened, ['lib/a.dart|a.dart']);
    });
  });

  group('sub-agent header', () {
    testWidgets('flows the same files after its label', (tester) async {
      final opened = <String>[];
      await _pump(
        tester,
        contents: const [_bash, _editA1, _writeB],
        onOpenFile: (path, name) => opened.add(path),
        subagent: true,
      );
      expect(find.text('Sub-agent: Explore · Run a command, edit a file, write a file'), findsOneWidget);
      expect(_listedFiles(tester), ['a.dart', 'b.dart']);
      await tester.tap(_fileItem('a.dart'));
      await tester.pump();
      expect(opened, ['lib/a.dart']);
    });

    testWidgets('an all-edit sub-agent run keeps its label too', (tester) async {
      await _pump(tester, contents: const [_editA1], onOpenFile: (_, __) {}, subagent: true);
      expect(find.text('Sub-agent: Explore · Edit a file'), findsOneWidget);
      expect(_listedFiles(tester), ['a.dart']);
    });
  });
}
