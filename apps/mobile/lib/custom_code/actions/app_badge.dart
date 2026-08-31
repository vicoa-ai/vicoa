// Automatic FlutterFlow imports
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter/foundation.dart';
import 'package:app_badge_plus/app_badge_plus.dart';
import '/custom_code/actions/vicoa_api_request.dart';

/// App-icon (launcher) badge helpers.
///
/// The badge shows how many of the user's sessions are currently awaiting
/// their input. In the background the OS renders it straight from the push
/// payload (iOS `aps.badge`, Android `notification_count`); these helpers cover
/// the cases the OS can't: mirroring the count while the app is foregrounded,
/// and reconciling with server truth on resume (e.g. after the user answered on
/// the web/desktop, so a badge a push had set must be cleared/decremented).
///
/// Every function swallows its own errors — a badge is cosmetic and must never
/// break notification handling or app lifecycle.

/// Set the launcher badge to [count] (clamped at 0; 0 clears it).
Future<void> setAppBadge(int count) async {
  final int value = count < 0 ? 0 : count;
  try {
    if (!await AppBadgePlus.isSupported()) return;
    await AppBadgePlus.updateBadge(value);
  } catch (e) {
    if (kDebugMode) {
      print('setAppBadge($value) failed: $e');
    }
  }
}

/// Clear the launcher badge.
Future<void> clearAppBadge() => setAppBadge(0);

/// Fetch the authoritative badge count (sessions awaiting input) from the
/// backend. Returns null if the request fails so callers can leave the badge
/// untouched rather than wrongly zeroing it on a transient error.
Future<int?> apiGetBadgeCount() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/push/badge-count', null);
    final count = (result is Map) ? result['count'] : null;
    if (count is int) return count;
    if (count is num) return count.toInt();
    return null;
  } catch (e) {
    if (kDebugMode) {
      print('apiGetBadgeCount failed: $e');
    }
    return null;
  }
}

/// Reconcile the launcher badge with the server's live awaiting-input count.
/// No-op when the backend can't be reached (leaves the last-known badge).
Future<void> refreshAppBadge() async {
  final count = await apiGetBadgeCount();
  if (count == null) return;
  await setAppBadge(count);
}
