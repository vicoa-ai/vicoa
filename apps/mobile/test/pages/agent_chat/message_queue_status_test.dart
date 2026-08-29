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

    test('reads consumed status', () {
      final message = {
        'message_metadata': {
          'queue': {'status': 'consumed', 'consumed_at': '2026-07-18T00:00:00Z'},
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
}
