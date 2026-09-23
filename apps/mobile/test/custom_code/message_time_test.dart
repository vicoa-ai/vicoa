// Which clock a message's `created_at` is read on.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/message_time.dart';

void main() {
  group('parseMessageTimestamp', () {
    test('a server row carries Z and lands on the device clock', () {
      final parsed = parseMessageTimestamp('2026-09-23T15:04:05.123456Z');

      expect(parsed, isNotNull);
      expect(parsed!.isUtc, isFalse);
      expect(parsed, DateTime.utc(2026, 9, 23, 15, 4, 5, 123, 456).toLocal());
    });

    test('an optimistic row has no marker and is already local', () {
      final now = DateTime(2026, 9, 23, 7, 30);

      expect(parseMessageTimestamp(now.toIso8601String()), now);
    });

    test('an offset is honoured', () {
      expect(
        parseMessageTimestamp('2026-09-23T17:04:05+02:00'),
        DateTime.utc(2026, 9, 23, 15, 4, 5).toLocal(),
      );
    });

    test('nothing usable reads as null', () {
      expect(parseMessageTimestamp(null), isNull);
      expect(parseMessageTimestamp(''), isNull);
      expect(parseMessageTimestamp('   '), isNull);
      expect(parseMessageTimestamp('not a date'), isNull);
    });
  });
}
