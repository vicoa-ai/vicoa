// The timestamp under a turn: which clock it is read on, and how it widens as
// the message ages.

import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:vicoa/custom_code/utils/message_time.dart';

String _time(DateTime when) => DateFormat.jm().format(when);

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

  group('formatMessageTime', () {
    final now = DateTime(2026, 9, 23, 14, 0);

    test('today is the bare time', () {
      final when = DateTime(2026, 9, 23, 10, 30);

      expect(
        formatMessageTime(when, yesterdayLabel: 'Yesterday', now: now),
        _time(when),
      );
    });

    test('yesterday is labelled, whatever the hour', () {
      final when = DateTime(2026, 9, 22, 23, 59);

      expect(
        formatMessageTime(when, yesterdayLabel: 'Yesterday', now: now),
        'Yesterday ${_time(when)}',
      );
    });

    test('the label is the caller localized one', () {
      final when = DateTime(2026, 9, 22, 8, 0);

      expect(
        formatMessageTime(when, yesterdayLabel: '昨天', now: now),
        startsWith('昨天 '),
      );
    });

    test('earlier this year gains a date', () {
      final when = DateTime(2026, 9, 15, 10, 30);

      expect(
        formatMessageTime(when, yesterdayLabel: 'Yesterday', now: now),
        '${DateFormat.MMMd().format(when)}, ${_time(when)}',
      );
    });

    test('another year gains the year too', () {
      final when = DateTime(2024, 1, 15, 10, 30);

      expect(
        formatMessageTime(when, yesterdayLabel: 'Yesterday', now: now),
        '${DateFormat.yMMMd().format(when)}, ${_time(when)}',
      );
    });

    test('day boundaries are calendar days, not 24-hour spans', () {
      // 20 hours earlier, but the previous calendar day.
      final when = DateTime(2026, 9, 22, 18, 0);

      expect(
        formatMessageTime(when, yesterdayLabel: 'Yesterday', now: now),
        'Yesterday ${_time(when)}',
      );
      // 2 hours earlier, same day.
      expect(
        formatMessageTime(DateTime(2026, 9, 23, 12, 0), yesterdayLabel: 'Yesterday', now: now),
        _time(DateTime(2026, 9, 23, 12, 0)),
      );
    });
  });
}
