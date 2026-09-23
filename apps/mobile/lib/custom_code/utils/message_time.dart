// When a message happened, on the device's clock — what the chat's date
// separators are grouped by.
//
// Two kinds of `created_at` reach the chat and they are not the same shape.
// The API serialises its own with a trailing `Z` (UTC); a message the app just
// sent optimistically carries `DateTime.now().toIso8601String()`, which has no
// marker at all and is already local. `DateTime.parse` reads the first as UTC
// and the second as local, so a single `.toLocal()` lands both on the device's
// clock — and without it a server row is shown in UTC, which after midnight
// UTC is the wrong day.

/// A message's `created_at` on the device's clock, or null when it is missing
/// or unparseable.
DateTime? parseMessageTimestamp(Object? raw) {
  final text = raw?.toString().trim() ?? '';
  if (text.isEmpty) return null;
  return DateTime.tryParse(text)?.toLocal();
}
