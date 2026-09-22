// The `<chat-history>` block a forked session opens with: what it keeps
// (prose, and the files each turn edited), what it drops (tool trail,
// reasoning, control messages), and how it stays inside its budget.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/fork_transcript.dart';

Map<String, dynamic> _user(String id, String content) =>
    {'id': id, 'sender_type': 'user', 'content': content};

Map<String, dynamic> _agent(String id, String content) =>
    {'id': id, 'sender_type': 'assistant', 'content': content};

Map<String, dynamic> _thinking(String id, String content) => {
      'id': id,
      'sender_type': 'assistant',
      'content': content,
      'message_metadata': {
        'thinking': {'signature': 'x'}
      },
    };

ForkTranscript _build(
  List<dynamic> messages, {
  String? boundary,
  String? title,
  String? directory,
}) =>
    buildForkTranscript(
      messages: messages,
      boundaryMessageId: boundary ?? (messages.last as Map)['id'].toString(),
      sourceTitle: title,
      sourceDirectory: directory,
    );

void main() {
  group('buildForkTranscript', () {
    test('keeps the conversation and labels each side', () {
      final t = _build([
        _user('1', 'add a test'),
        _agent('2', 'Added one.'),
      ]);

      expect(t.text, contains('User: add a test'));
      expect(t.text, contains('Agent: Added one.'));
      expect(t.messageCount, 2);
      expect(t.omittedCount, 0);
    });

    test('wraps the block and names the source', () {
      final t = _build(
        [_user('1', 'hi')],
        title: 'Session title',
        directory: '/repo',
      );

      expect(t.text, startsWith('<chat-history>\n'));
      expect(t.text, endsWith('\n</chat-history>'));
      expect(t.text, contains('Tool outputs are not included'));
      expect(t.text, contains('Source session: Session title'));
      expect(t.text, contains('Source directory: /repo'));
    });

    test('drops the tool trail but names the files a turn edited', () {
      final t = _build([
        _user('1', 'fix it'),
        _agent('2', 'Looking.'),
        _agent('3', 'Using tool: **Bash** - `flutter test`'),
        _agent('4', 'Using tool: **Read** - `lib/a.dart`'),
        _agent('5', 'Using tool: **Edit** - `lib/a.dart`\n\n```diff\n-x\n+y\n```'),
        _agent('6', 'Using tool: **Write** - `lib/b.dart`'),
        _agent('7', 'Done.'),
      ]);

      expect(t.text, isNot(contains('Bash')));
      expect(t.text, isNot(contains('flutter test')));
      // The edited line rides on the turn's last line of prose.
      expect(t.text, contains('Agent: Done.\n  [edited: lib/a.dart, lib/b.dart]'));
      // A read is not an edit.
      expect(t.text, isNot(contains('Using tool')));
      expect(t.messageCount, 3);
    });

    test('reads the Codex shapes too, not just the Claude ones', () {
      final t = _build([
        _user('1', 'patch it'),
        _agent('2', '**Exec:** `bash -lc ls`'),
        _agent('3', '✏️ Applying patch to 1 file (+3 -1)\n└ lib/a.dart\n**lib/a.dart**'),
        _agent('4', 'Patched.'),
      ]);

      expect(t.text, contains('Agent: Patched.\n  [edited: lib/a.dart]'));
      expect(t.text, isNot(contains('bash -lc ls')));
    });

    test('lists a file edited several times in a turn once', () {
      final t = _build([
        _user('1', 'fix it'),
        _agent('2', 'Using tool: **Edit** - `lib/a.dart`'),
        _agent('3', 'Using tool: **Edit** - `lib/a.dart`'),
        _agent('4', 'Done.'),
      ]);

      expect(t.text, contains('[edited: lib/a.dart]'));
    });

    test('a turn that only edited still gets its line', () {
      final t = _build([
        _user('1', 'rename it'),
        _agent('2', 'Using tool: **Edit** - `lib/a.dart`'),
      ]);

      expect(t.text, contains('[edited: lib/a.dart]'));
      // The standalone line is not a message.
      expect(t.messageCount, 1);
    });

    test('caps the edited list and counts the rest', () {
      final messages = <dynamic>[_user('1', 'touch everything')];
      for (var i = 0; i < kForkMaxEditedPaths + 3; i++) {
        messages.add(_agent('e$i', 'Using tool: **Edit** - `lib/f$i.dart`'));
      }
      messages.add(_agent('last', 'Done.'));

      final t = _build(messages);

      expect(t.text, contains('lib/f0.dart'));
      expect(t.text, contains('… +3 more'));
      expect(t.text, isNot(contains('lib/f22.dart')));
    });

    test('shortens a path that is still under the source folder', () {
      final t = _build(
        [
          _user('1', 'fix it'),
          _agent('2', 'Using tool: **Edit** - `/repo/lib/a.dart`'),
        ],
        directory: '/repo',
      );

      expect(t.text, contains('[edited: lib/a.dart]'));
    });

    test('drops reasoning', () {
      final t = _build([
        _user('1', 'think'),
        _thinking('2', 'The user wants me to…'),
        _agent('3', 'Here.'),
      ]);

      expect(t.text, isNot(contains('The user wants me to')));
      expect(t.messageCount, 2);
    });

    test('drops messages the chat itself hides', () {
      // `sanitize` is the chat's own filter; anything it empties is gone.
      final t = buildForkTranscript(
        messages: [
          _user('1', 'go'),
          _agent('2', '{"type":"control","setting":"interrupt"}'),
          _agent('3', 'Stopped.'),
        ],
        boundaryMessageId: '3',
        sanitize: (content) => content.startsWith('{"type":"control"') ? '' : content,
      );

      expect(t.text, isNot(contains('control')));
      expect(t.messageCount, 2);
    });

    test('stops at the boundary message', () {
      final t = _build([
        _user('1', 'first'),
        _agent('2', 'answer one'),
        _user('3', 'second'),
        _agent('4', 'answer two'),
      ], boundary: '2');

      expect(t.text, contains('answer one'));
      expect(t.text, isNot(contains('second')));
      expect(t.text, isNot(contains('answer two')));
    });

    test('an unknown boundary keeps the whole timeline', () {
      final t = _build([
        _user('1', 'first'),
        _agent('2', 'answer one'),
      ], boundary: 'gone');

      expect(t.text, contains('first'));
      expect(t.text, contains('answer one'));
    });

    test('elides an entry that is too long on its own', () {
      final t = _build([
        _user('1', 'x' * (kForkMaxEntryChars + 500)),
      ]);

      expect(t.text, contains('… (truncated)'));
      expect(t.text.length, lessThan(kForkMaxEntryChars + 500));
    });

    test('trims from the front and says how many it dropped', () {
      final chunk = 'y' * 5000;
      final messages = <dynamic>[];
      for (var i = 0; i < 40; i++) {
        messages.add(_user('u$i', 'ask $i $chunk'));
        messages.add(_agent('a$i', 'answer $i $chunk'));
      }

      final t = _build(messages);

      expect(t.omittedCount, greaterThan(0));
      expect(t.text, contains('earlier message'));
      expect(t.text, contains('omitted'));
      // The tail — what the new session actually needs — survives.
      expect(t.text, contains('answer 39'));
      expect(t.text, isNot(contains('ask 0 ')));
      expect(t.text.length, lessThan(kForkMaxTotalChars + 2000));
    });

    test('an empty timeline still renders a block', () {
      final t = buildForkTranscript(messages: const [], boundaryMessageId: 'x');

      expect(t.text, contains('No chat history to display.'));
      expect(t.messageCount, 0);
    });
  });

  group('ForkSessionContext', () {
    test('round-trips through JSON', () {
      const context = ForkSessionContext(
        text: '<chat-history>…</chat-history>',
        messageCount: 12,
        omittedCount: 3,
        sourceInstanceId: 'abc',
        sourceTitle: 'Session title',
        machineId: 'machine-1',
        directory: '/repo',
        agentType: 'claude',
      );

      final back = ForkSessionContext.fromJson(context.toJson())!;

      expect(back.text, context.text);
      expect(back.messageCount, 12);
      expect(back.omittedCount, 3);
      expect(back.sourceInstanceId, 'abc');
      expect(back.sourceTitle, 'Session title');
      expect(back.machineId, 'machine-1');
      expect(back.directory, '/repo');
      expect(back.agentType, 'claude');
    });

    test('a payload with no history is not a fork', () {
      expect(ForkSessionContext.fromJson(null), isNull);
      expect(ForkSessionContext.fromJson(const {'text': '  '}), isNull);
      expect(ForkSessionContext.fromJson(const {'messageCount': 3}), isNull);
    });

    test('blank fields read back as absent, not empty strings', () {
      final back = ForkSessionContext.fromJson(
          const {'text': 'x', 'machineId': '', 'directory': '  '})!;

      expect(back.machineId, isNull);
      expect(back.directory, isNull);
    });
  });
}
