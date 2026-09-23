// When a message happened, as the chat says it: the timestamp under a turn
// and the date separator above it.
//
// Two kinds of `created_at` reach the chat and they are not the same shape.
// The API serialises its own with a trailing `Z` (UTC); a message the app just
// sent optimistically carries `DateTime.now().toIso8601String()`, which has no
// marker at all and is already local. `DateTime.parse` reads the first as UTC
// and the second as local, so a single `.toLocal()` lands both on the device's
// clock — and without it a server row is shown in UTC, which after midnight
// UTC is the wrong day.

import 'package:intl/intl.dart';

/// A message's `created_at` on the device's clock, or null when it is missing
/// or unparseable.
DateTime? parseMessageTimestamp(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  if (text.isEmpty) return null;
  return DateTime.tryParse(text)?.toLocal();
}

/// The label under a turn: bare `10:30 AM` today, widening to
/// `Yesterday 10:30 AM`, `Sep 15, 10:30 AM` and `Sep 15, 2024, 10:30 AM` as
/// the message ages. Mirrors the dashboard's message footer so a session reads
/// the same on both.
///
/// [now] is injectable for tests; it defaults to the current time.
String formatMessageTime(
  DateTime when, {
  required String yesterdayLabel,
  DateTime? now,
}) {
  final today = now ?? DateTime.now();
  final time = DateFormat.jm().format(when);
  final startOfToday = DateTime(today.year, today.month, today.day);
  final startOfMessageDay = DateTime(when.year, when.month, when.day);
  final days = startOfToday.difference(startOfMessageDay).inDays;

  if (days == 0) return time;
  if (days == 1) return '$yesterdayLabel $time';
  final date = when.year == today.year
      ? DateFormat.MMMd().format(when)
      : DateFormat.yMMMd().format(when);
  return '$date, $time';
}
