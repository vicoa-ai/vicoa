import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/ws_protocol.dart';

void main() {
  group('createAppendTracker', () {
    test('accepts the first row for an id, rejects a later row with same id', () {
      final tracker = createAppendTracker();
      expect(tracker.accept({'id': 'm1'}), isTrue);
      expect(tracker.accept({'id': 'm1'}), isFalse);
    });
  });

  group('createMutableTracker', () {
    test('accepts the first row for an id', () {
      final tracker = createMutableTracker();
      expect(
        tracker.accept({'id': 'i1', 'updated_at': '2026-05-21T10:00:00Z'}),
        isTrue,
      );
    });

    test('accepts a row whose updated_at is strictly newer than the last seen', () {
      final tracker = createMutableTracker();
      tracker.accept({'id': 'i1', 'updated_at': '2026-05-21T10:00:00Z'});
      expect(
        tracker.accept({'id': 'i1', 'updated_at': '2026-05-21T10:00:01Z'}),
        isTrue,
      );
    });

    test('rejects a row whose updated_at equals or precedes the last seen', () {
      final tracker = createMutableTracker();
      tracker.accept({'id': 'i1', 'updated_at': '2026-05-21T10:00:05Z'});
      expect(
        tracker.accept({'id': 'i1', 'updated_at': '2026-05-21T10:00:05Z'}),
        isFalse,
      );
      expect(
        tracker.accept({'id': 'i1', 'updated_at': '2026-05-21T10:00:01Z'}),
        isFalse,
      );
    });
  });

  group('CatchUpBuffer', () {
    test('holds live rows back until the catch-up fetch completes', () {
      final buffer = CatchUpBuffer(createAppendTracker());
      buffer.beginCatchUp();
      expect(buffer.bufferLive({'id': 'm2'}), isEmpty);
    });

    test('on fetch completion delivers fetch rows first, then buffered live', () {
      final buffer = CatchUpBuffer(createAppendTracker());
      buffer.beginCatchUp();
      buffer.bufferLive({'id': 'm3'});
      expect(
        buffer.completeFetch([
          {'id': 'm1'},
          {'id': 'm2'},
        ]),
        [
          {'id': 'm1'},
          {'id': 'm2'},
          {'id': 'm3'},
        ],
      );
    });

    test('delivers live rows immediately once the fetch has completed', () {
      final buffer = CatchUpBuffer(createAppendTracker());
      buffer.beginCatchUp();
      buffer.completeFetch([]);
      expect(buffer.bufferLive({'id': 'm9'}), [
        {'id': 'm9'},
      ]);
    });

    test('dedupes a buffered live row already present in the fetch rows', () {
      final buffer = CatchUpBuffer(createAppendTracker());
      buffer.beginCatchUp();
      buffer.bufferLive({'id': 'm1'});
      expect(buffer.completeFetch([
        {'id': 'm1'},
      ]), [
        {'id': 'm1'},
      ]);
    });

    test('keeps tracker seen-state across cycles so a reconnect re-fetch does not re-deliver', () {
      final buffer = CatchUpBuffer(createAppendTracker());
      buffer.beginCatchUp();
      buffer.completeFetch([
        {'id': 'm1'},
      ]);
      buffer.beginCatchUp();
      expect(buffer.completeFetch([
        {'id': 'm1'},
        {'id': 'm2'},
      ]), [
        {'id': 'm2'},
      ]);
    });
  });

  group('applyMessageMetadataUpdate', () {
    test('replaces message_metadata on the message with matching id', () {
      final messages = [
        {
          'id': 'm1',
          'content': 'hi',
          'message_metadata': {'old': true},
        },
        {'id': 'm2', 'content': 'bye'},
      ];
      final patched = applyMessageMetadataUpdate(messages, {
        'id': 'm1',
        'message_metadata': {'new': true},
      });
      expect(patched, isTrue);
      expect(messages[0], {
        'id': 'm1',
        'content': 'hi',
        'message_metadata': {'new': true},
      });
      // Untouched message is left exactly as it was.
      expect(messages[1], {'id': 'm2', 'content': 'bye'});
    });

    test('keeps key order unchanged — only the value is replaced', () {
      final messages = [
        {
          'id': 'm1',
          'message_metadata': {'old': true},
          'content': 'hi',
        },
      ];
      applyMessageMetadataUpdate(messages, {
        'id': 'm1',
        'message_metadata': {'new': true},
      });
      expect(
        (messages[0] as Map).keys.toList(),
        ['id', 'message_metadata', 'content'],
      );
    });

    test('no-ops when the id is not present in the message list', () {
      final messages = [
        {'id': 'm1', 'content': 'hi'},
      ];
      final patched = applyMessageMetadataUpdate(messages, {
        'id': 'unknown',
        'message_metadata': {'x': 1},
      });
      expect(patched, isFalse);
      expect(messages, [
        {'id': 'm1', 'content': 'hi'},
      ]);
    });

    test('no-ops when the update frame has no id', () {
      final messages = [
        {'id': 'm1', 'content': 'hi'},
      ];
      final patched = applyMessageMetadataUpdate(messages, {
        'message_metadata': {'x': 1},
      });
      expect(patched, isFalse);
    });

    test(
        'no-ops when the frame is missing the message_metadata key '
        '(does not wipe existing metadata)', () {
      final messages = [
        {
          'id': 'm1',
          'content': 'hi',
          'message_metadata': {'old': true},
        },
      ];
      final patched = applyMessageMetadataUpdate(messages, {'id': 'm1'});
      expect(patched, isFalse);
      expect(messages[0], {
        'id': 'm1',
        'content': 'hi',
        'message_metadata': {'old': true},
      });
    });
  });

  group('reconnectDelayMs', () {
    test('jitters from the first attempt — attempt 0 can be below the base', () {
      final samples = List.generate(200, (_) => reconnectDelayMs(0));
      expect(samples.reduce((a, b) => a < b ? a : b), lessThan(1000));
      expect(samples.every((d) => d >= 0 && d <= 1000), isTrue);
    });

    test('grows the jitter window exponentially but clamps it to the cap', () {
      expect(reconnectDelayMs(2), lessThanOrEqualTo(4000));
      final capped = List.generate(100, (_) => reconnectDelayMs(20));
      expect(capped.every((d) => d >= 0 && d <= 30000), isTrue);
    });
  });

  group('latestTimestamp', () {
    test('returns the maximum value of the field across the rows', () {
      final rows = [
        {'id': 'a', 'created_at': '2026-05-21T10:00:00Z'},
        {'id': 'b', 'created_at': '2026-05-21T10:00:09Z'},
        {'id': 'c', 'created_at': '2026-05-21T10:00:04Z'},
      ];
      expect(latestTimestamp(null, rows, 'created_at'), '2026-05-21T10:00:09Z');
    });

    test('never regresses below the current watermark', () {
      final rows = [
        {'id': 'a', 'created_at': '2026-05-21T09:00:00Z'},
      ];
      expect(
        latestTimestamp('2026-05-21T10:00:00Z', rows, 'created_at'),
        '2026-05-21T10:00:00Z',
      );
    });

    test('returns the current watermark unchanged for an empty row set', () {
      expect(latestTimestamp('2026-05-21T10:00:00Z', [], 'created_at'),
          '2026-05-21T10:00:00Z');
      expect(latestTimestamp(null, [], 'created_at'), isNull);
    });
  });
}
