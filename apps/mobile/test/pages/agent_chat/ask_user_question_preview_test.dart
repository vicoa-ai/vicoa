import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

import 'package:vicoa/pages/agent_chat/components/ask_user_question_preview.dart';

const _expandIcon = Icons.open_in_full_rounded;

Future<void> _pumpPane(WidgetTester tester, String preview) async {
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: Center(child: SizedBox(width: 300, child: AskUserQuestionPreviewPane(preview: preview))))));
  await tester.pump();
}

void main() {
  // No network in tests; the mono font falls back to the default family.
  GoogleFonts.config.allowRuntimeFetching = false;

  final wideTable = ['┌${'─' * 120}┐', '│ Region │ Plan │ Seats │ Active │ Exports │ Search queries │ Errors │ p95 latency │ Uptime │ Owner │ Notes │', '└${'─' * 120}┘'].join('\n');

  testWidgets('a grid wider than the pane offers the full-screen view', (tester) async {
    await _pumpPane(tester, wideTable);
    expect(find.byIcon(_expandIcon), findsOneWidget);

    await tester.tap(find.byIcon(_expandIcon));
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsOneWidget);

    await tester.tap(find.byIcon(Icons.close_rounded));
    await tester.pumpAndSettle();
    expect(find.byType(InteractiveViewer), findsNothing);
  });

  testWidgets('prose wraps in place with no expand button', (tester) async {
    await _pumpPane(tester, 'Lumen 2.4 makes search update as you type, keeps CSV exports in column order, and fixes the export that dropped its last row.');
    expect(find.byIcon(_expandIcon), findsNothing);
    expect(find.byType(SingleChildScrollView), findsNothing);
  });

  testWidgets('a grid that fits needs no expand button', (tester) async {
    await _pumpPane(tester, '┌──────┐\n│ Tile │\n└──────┘');
    expect(find.byIcon(_expandIcon), findsNothing);
  });
}
