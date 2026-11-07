// The chat composer's annotations through the real send path: what reaches the
// optimistic bubble, what is left behind, and what survives a return visit.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:vicoa/app_state.dart';
import 'package:vicoa/pages/agent_chat/agent_chat_model.dart';

AgentChatModel _model() {
  final model = AgentChatModel();
  model.messageController = TextEditingController();
  model.itemScrollController = ItemScrollController();
  model.instanceId = 'session-1';
  model.instanceData = <String, dynamic>{'status': 'ACTIVE'};
  return model;
}

/// The text of the bubble a send puts up. The screen is gone by the time the
/// POST fails in the test binding, which skips the failure snack.
Future<String?> _sentContent(WidgetTester tester, AgentChatModel model, String text, {bool isOptionClick = false}) async {
  late BuildContext context;
  await tester.pumpWidget(Builder(builder: (c) {
    context = c;
    return const SizedBox();
  }));
  await tester.pumpWidget(const SizedBox());
  String? content;
  await tester.runAsync(() async {
    final before = model.messages.length;
    final send = model.sendMessage(context, text, isOptionClick: isOptionClick);
    if (model.messages.length > before) content = model.messages.last['content'] as String?;
    await send;
  });
  return content;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FFAppState.reset();
    await FFAppState().initializePersistedState();
  });

  testWidgets('annotations follow the typed text and are gone after the send', (tester) async {
    final model = _model();
    model.addAnnotation('the passage');

    expect(await _sentContent(tester, model, 'fix this'), 'fix this\n\n---\n1. > the passage');
    expect(model.annotations, isEmpty);
    expect(FFAppState().getChatAnnotations('session-1'), isNull);
  });

  testWidgets('an annotation alone is enough to send', (tester) async {
    final model = _model();
    model.addAnnotation('the passage');

    expect(await _sentContent(tester, model, '   '), '1. > the passage');
  });

  testWidgets('an option click neither carries nor consumes them', (tester) async {
    final model = _model();
    model.addAnnotation('the passage');

    expect(await _sentContent(tester, model, 'Yes', isOptionClick: true), 'Yes');
    expect(model.annotations, hasLength(1));
  });

  test('they are still there on a return visit, per session', () {
    final first = _model();
    first.addAnnotation('kept');
    first.updateAnnotationComment(first.annotations.single.id, 'and its note');

    final back = _model();
    back.restoreAnnotations();
    expect(back.annotations.single.quote, 'kept');
    expect(back.annotations.single.comment, 'and its note');

    final other = _model()..instanceId = 'session-2';
    other.restoreAnnotations();
    expect(other.annotations, isEmpty);
  });

  test('sign-out clears them', () {
    final model = _model();
    model.addAnnotation('private');

    FFAppState().clearAllUserData();

    final back = _model();
    back.restoreAnnotations();
    expect(back.annotations, isEmpty);
  });
}
