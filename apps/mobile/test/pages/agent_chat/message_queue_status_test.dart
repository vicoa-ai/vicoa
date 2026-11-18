import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/pages/agent_chat/components/message_queue_status.dart';

void main() {
  group('queueStatus', () {
    test('reads queued status', () {
      final message = {
        'sender_type': 'user',
        'message_metadata': {
          'queue': {'status': 'queued'},
        },
      };
      expect(queueStatus(message), kQueueStatusQueued);
    });

    test('reads steer status (Steer pressed, daemon delivering)', () {
      final message = {
        'sender_type': 'user',
        'message_metadata': {
          'queue': {'status': 'steer', 'steer_requested_at': '2026-07-18T00:00:00Z'},
        },
      };
      expect(queueStatus(message), kQueueStatusSteer);
    });

    test('reads consumed status', () {
      final message = {
        'message_metadata': {
          'queue': {'status': 'consumed', 'consumed_at': '2026-07-18T00:00:00Z'},
        },
      };
      expect(queueStatus(message), kQueueStatusConsumed);
    });

    test('reads consumed status on a steered message', () {
      final message = {
        'message_metadata': {
          'queue': {'status': 'consumed', 'steered': true},
        },
      };
      expect(queueStatus(message), kQueueStatusConsumed);
    });

    test('reads cancelled status', () {
      final message = {
        'message_metadata': {
          'queue': {'status': 'cancelled', 'cancelled_at': '2026-07-18T00:00:00Z'},
        },
      };
      expect(queueStatus(message), kQueueStatusCancelled);
    });

    test('returns null when message has no message_metadata', () {
      final message = {'sender_type': 'user', 'content': 'hi'};
      expect(queueStatus(message), isNull);
    });

    test('returns null when queue metadata is absent', () {
      final message = {
        'message_metadata': {'attachments': []},
      };
      expect(queueStatus(message), isNull);
    });

    test('returns null for malformed message_metadata (not a Map)', () {
      final message = {'message_metadata': 'not-a-map'};
      expect(queueStatus(message), isNull);
    });

    test('returns null for malformed queue (not a Map)', () {
      final message = {
        'message_metadata': {'queue': 'not-a-map'},
      };
      expect(queueStatus(message), isNull);
    });

    test('returns null for malformed status (not a String)', () {
      final message = {
        'message_metadata': {
          'queue': {'status': 42},
        },
      };
      expect(queueStatus(message), isNull);
    });

    test('returns null for empty status string', () {
      final message = {
        'message_metadata': {
          'queue': {'status': ''},
        },
      };
      expect(queueStatus(message), isNull);
    });

    test('returns null when message itself is not a Map', () {
      expect(queueStatus('not-a-message'), isNull);
      expect(queueStatus(null), isNull);
      expect(queueStatus(42), isNull);
    });
  });

  group('isPendingQueueStatus', () {
    test('treats queued and steer as still in the bar', () {
      expect(isPendingQueueStatus(kQueueStatusQueued), isTrue);
      expect(isPendingQueueStatus(kQueueStatusSteer), isTrue);
    });

    test('treats terminal states and no status as not pending', () {
      expect(isPendingQueueStatus(kQueueStatusConsumed), isFalse);
      expect(isPendingQueueStatus(kQueueStatusCancelled), isFalse);
      expect(isPendingQueueStatus(null), isFalse);
      expect(isPendingQueueStatus(''), isFalse);
    });
  });

  // The AskUserQuestion answer summary, built the way both pickers build it:
  // "Q:/A:" lines, a newline, then the persist_only control token.
  String answerSummary(String question, String label) {
    final payload = base64UrlEncode(utf8.encode(jsonEncode({
      'message_id': 'prompt-message-id',
      'answers': [
        {'mode': 'option', 'option_index': 0},
      ],
      'display_answers': [
        {'question': question, 'header': 'Q1', 'label': label},
      ],
    }))).replaceAll('=', '');
    final control = jsonEncode({
      'type': 'control',
      'action': 'persist_only',
      'kind': 'ask_user_question_summary',
      'value': 'v1:$payload',
    });
    return 'Q: $question\nA: $label\n$control';
  }

  final declined =
      'Declined to answer\n${jsonEncode({'type': 'control', 'action': 'persist_only'})}';

  Map<String, dynamic> userMessage(String content, {String? status}) => {
        'id': 'm1',
        'sender_type': 'user',
        'content': content,
        if (status != null)
          'message_metadata': {
            'queue': {'status': status},
          },
      };

  group('isPersistOnlyArtifact', () {
    test('matches the answer summary and the decline note', () {
      expect(isPersistOnlyArtifact(userMessage(answerSummary('Which db?', 'Postgres'))), isTrue);
      expect(isPersistOnlyArtifact(userMessage(declined)), isTrue);
    });

    test('ignores prose that quotes a persist_only token mid-body', () {
      final quoted = userMessage(
          'what does {"type":"control","action":"persist_only"} mean here?');
      expect(isPersistOnlyArtifact(quoted), isFalse);
    });

    test('ignores other control messages and plain text', () {
      final submit = userMessage('Submit AskUserQuestion answers. '
          '{"type":"control","setting":"ask_user_question","value":"submit:e30"}');
      expect(isPersistOnlyArtifact(submit), isFalse);
      expect(isPersistOnlyArtifact(userMessage('keep going')), isFalse);
      expect(isPersistOnlyArtifact(userMessage('')), isFalse);
      expect(isPersistOnlyArtifact('not-a-message'), isFalse);
    });
  });

  group('isHiddenByQueueStatus', () {
    test('a queued answer summary stays in the transcript', () {
      final summary = answerSummary('Which db?', 'Postgres');
      expect(isHiddenByQueueStatus(userMessage(summary, status: kQueueStatusQueued)), isFalse);
      expect(isHiddenByQueueStatus(userMessage(summary, status: kQueueStatusSteer)), isFalse);
      expect(isHiddenByQueueStatus(userMessage(declined, status: kQueueStatusQueued)), isFalse);
    });

    test('a queued or steering ordinary message is still hidden', () {
      expect(isHiddenByQueueStatus(userMessage('later', status: kQueueStatusQueued)), isTrue);
      expect(isHiddenByQueueStatus(userMessage('now', status: kQueueStatusSteer)), isTrue);
    });

    test('a cancelled message is hidden, artifact or not', () {
      expect(isHiddenByQueueStatus(userMessage('oops', status: kQueueStatusCancelled)), isTrue);
      expect(isHiddenByQueueStatus(userMessage(declined, status: kQueueStatusCancelled)), isTrue);
    });

    test('consumed, unqueued and agent messages are never hidden', () {
      expect(isHiddenByQueueStatus(userMessage('done', status: kQueueStatusConsumed)), isFalse);
      expect(isHiddenByQueueStatus(userMessage('idle send')), isFalse);
      final agent = {
        'sender_type': 'agent',
        'content': 'working',
        'message_metadata': {
          'queue': {'status': kQueueStatusQueued},
        },
      };
      expect(isHiddenByQueueStatus(agent), isFalse);
      expect(isHiddenByQueueStatus(null), isFalse);
    });

    test('a queued summary stays out of the queue bar', () {
      // The bar filters control messages, so the transcript is the only
      // place a queued summary can show.
      final summary = userMessage(answerSummary('Which db?', 'Postgres'),
          status: kQueueStatusQueued);
      expect(isControlOrArtifactMessage(summary), isTrue);
    });
  });
}
