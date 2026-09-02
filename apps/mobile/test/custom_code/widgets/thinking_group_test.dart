// Spec for the model-reasoning ("thinking") card helpers
// (`lib/custom_code/widgets/thinking_group.dart`). Covers the metadata reader
// `isThinkingMessage` and the display-body normalizer `thinkingDisplayBody`.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/widgets/thinking_group.dart';

Map<String, dynamic> _thinkingMsg(String source, {String content = 'weighing options'}) => {
      'sender_type': 'AGENT',
      'content': content,
      'message_metadata': {
        'thinking': {'source': source},
      },
    };

void main() {
  group('isThinkingMessage', () {
    test('true for a thinking-tagged message', () {
      expect(isThinkingMessage(_thinkingMsg('claude')), isTrue);
      expect(isThinkingMessage(_thinkingMsg('codex')), isTrue);
    });

    test('false without thinking metadata', () {
      expect(isThinkingMessage({'content': 'hi', 'message_metadata': null}), isFalse);
      expect(
        isThinkingMessage({
          'content': 'hi',
          'message_metadata': {
            'subagent': {'tool_use_id': 't'},
          },
        }),
        isFalse,
      );
      expect(isThinkingMessage('not a map'), isFalse);
      expect(
        isThinkingMessage({
          'message_metadata': {'thinking': 'not-a-map'},
        }),
        isFalse,
      );
    });
  });

  group('thinkingDisplayBody', () {
    test('strips a leading Codex reasoning label', () {
      expect(thinkingDisplayBody('Reasoning:\nconsidered A and B'), 'considered A and B');
    });

    test('strips a legacy emoji reasoning label', () {
      expect(thinkingDisplayBody('🧠 Reasoning:\nconsidered A and B'), 'considered A and B');
    });

    test('leaves Claude-style plain reasoning untouched', () {
      expect(thinkingDisplayBody('let me think about this'), 'let me think about this');
    });

    test('falls back to trimmed content when stripping empties it', () {
      expect(thinkingDisplayBody('Reasoning:'), 'Reasoning:');
    });
  });
}
