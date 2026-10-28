import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/pages/agent_chat/components/ask_user_question_panel.dart';
import 'package:vicoa/pages/agent_chat/components/ask_user_question_preview.dart';

Map<String, dynamic> _message(List<Map<String, dynamic>> options) => {
      'message_metadata': {
        'ask_user_question': {
          'tool_use_id': 'toolu_1',
          'questions': [
            {'question': 'Which draft should go out?', 'header': 'Draft', 'options': options, 'multi_select': false},
          ],
        },
      },
    };

void main() {
  // parseAskUserQuestionPayload localizes its fallback header via tr().
  TestWidgetsFlutterBinding.ensureInitialized();

  group('parseAskUserQuestionPayload', () {
    test('keeps an option preview verbatim', () {
      final payload = parseAskUserQuestionPayload(_message([
        {'label': 'Short', 'description': 'Two bullets', 'preview': '## v1.9.13\n\n  - Fixes'},
        {'label': 'Long', 'description': 'Every change'},
      ]));
      final options = payload!.questions.first.options;
      expect(options[0].preview, '## v1.9.13\n\n  - Fixes');
      expect(options[1].preview, isNull);
    });

    test('drops a blank or non-string preview', () {
      final payload = parseAskUserQuestionPayload(_message([
        {'label': 'A', 'description': '', 'preview': '   '},
        {'label': 'B', 'description': '', 'preview': 42},
      ]));
      expect(payload!.questions.first.options.map((o) => o.preview), [null, null]);
    });
  });

  group('isGridPreview', () {
    test('keeps box drawings and markdown tables on one line per row', () {
      expect(isGridPreview('┌──────┐\n│ Tile │\n└──────┘'), isTrue);
      expect(isGridPreview('| Plan | Seats |\n| --- | --- |\n| Team | 48 |'), isTrue);
    });

    test('lets prose and code wrap', () {
      expect(isGridPreview('Lumen 2.4 makes search update as you type, and fixes exports.'), isFalse);
      expect(isGridPreview('const total = a || b;\nif (x | y) return;'), isFalse);
    });
  });
}
