// What "Continue in new session" does to the new-session composer: the first
// message it sends.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/chat_annotations.dart';
import 'package:vicoa/custom_code/utils/fork_transcript.dart';
import 'package:vicoa/pages/new_session/new_session_model.dart';

const _handoff = ChatAnnotationHandoff(
  annotations: [ChatAnnotation(id: 'a', quote: 'the selected text')],
  machineId: 'm-1',
  directory: '/repo',
  agentType: 'codex',
);

void main() {
  group('composeFirstMessage', () {
    test('the carried text follows what the user typed', () {
      final model = NewSessionModel(annotationHandoff: _handoff);
      model.promptController.text = '  look into this  ';

      expect(model.composeFirstMessage(), 'look into this\n\n---\n1. > the selected text');
    });

    test('the carried text alone is a valid first message', () {
      expect(NewSessionModel(annotationHandoff: _handoff).composeFirstMessage(), '1. > the selected text');
    });

    test('a comment added on this screen goes with it', () {
      final model = NewSessionModel(annotationHandoff: _handoff);
      model.updateAnnotationComment('a', 'start from here');

      expect(model.composeFirstMessage(), '1. > the selected text\n   Comment: start from here');
    });

    test('removing it leaves just the prompt', () {
      final model = NewSessionModel(annotationHandoff: _handoff);
      model.promptController.text = 'start here';

      model.clearAnnotations();

      expect(model.composeFirstMessage(), 'start here');
    });

    test('a fork history still goes on top', () {
      const fork = ForkSessionContext(text: '<chat-history>x</chat-history>', messageCount: 1);
      final model = NewSessionModel(forkContext: fork, annotationHandoff: _handoff);
      model.promptController.text = 'next';

      expect(model.composeFirstMessage(), '<chat-history>x</chat-history>\n\nnext\n\n---\n1. > the selected text');
    });
  });
}
