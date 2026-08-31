// Automatic FlutterFlow imports
import '/flutter_flow/flutter_flow_util.dart';
import '/auth/supabase_auth/auth_util.dart';
import 'index.dart'; // Imports other custom actions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Shared local-session teardown for every sign-out path — logout, account
/// deletion, and the auth-error "sign in again" escape hatch. Centralizing it
/// keeps those paths from drifting apart (e.g. a newly-added on-disk cache
/// that only some paths remember to wipe).
///
/// `signOut` is guarded: a revoked/deleted session can make it throw on the
/// revoke call, and callers depend on the cache + state cleanup running anyway
/// so they never strand a signed-in-looking session whose pollers keep 401ing.
///
/// Context-bound concerns stay at the call site: `prepareAuthEvent` /
/// `clearRedirectLocation`, navigation, FCM handling, and `apiDeleteUser`.
Future<void> signOutAndClearLocalData() async {
  try {
    await authManager.signOut();
  } catch (e) {
    debugPrint('signOut during session teardown failed: $e');
  }
  // Wipe on-disk caches (Files Hive + per-instance chat transcripts) so the
  // next account on this device never reads the previous user's data.
  await FilesCache.wipeStatic();
  await ChatMessagesCache.instance.wipeAll();
  FFAppState().clearAllUserData();
  // Drop the launcher badge — it counts the signed-out user's awaiting
  // sessions and would otherwise linger on the icon after logout.
  await clearAppBadge();
}
