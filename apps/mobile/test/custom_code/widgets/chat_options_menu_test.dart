// The session actions menu (long-press on the list, or the chat page's top
// right dots). Unread puts the blue "needs a reply" dot back on a reviewed
// session, so the item only exists when the caller passes `onUnread`.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/widgets/chat_options_menu.dart';
import 'package:vicoa/l10n/app_localizations.dart';

const _unreadIcon = Icons.mark_chat_unread_rounded;

Future<void> _pumpMenu(WidgetTester tester, {VoidCallback? onUnread}) {
  return tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(
      body: ChatOptionsMenu(
        onInfo: () {},
        onShare: () {},
        onRename: () {},
        onClose: () {},
        onDelete: () {},
        onUnread: onUnread,
      ),
    ),
  ));
}

void main() {
  testWidgets('hides Unread when the caller does not offer it', (tester) async {
    await _pumpMenu(tester);

    expect(find.byIcon(_unreadIcon), findsNothing);
    expect(find.text('Unread'), findsNothing);
    // The rest of the menu is untouched.
    expect(find.text('Archive'), findsOneWidget);
  });

  testWidgets('shows Unread before Archive and fires onUnread on tap', (tester) async {
    var taps = 0;
    await _pumpMenu(tester, onUnread: () => taps++);

    expect(find.text('Unread'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Unread')).dy,
      lessThan(tester.getTopLeft(find.text('Archive')).dy),
    );

    await tester.tap(find.text('Unread'));
    expect(taps, 1);
  });
}
