// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Persist `subscription_status` to BOTH FFAppState and Supabase
/// `profiles.subscription_status`.
///
/// The legacy code only updated FFAppState, which meant the next time
/// `supabaseSyncProfile` ran it wrote whatever stale value was in local
/// state — usually the empty string, since `supabase_create_profile`
/// never set an initial value. Result: hundreds of paying users showed
/// up as `subscription_status=''` in Supabase even though they were
/// actively on Pro (and the dashboard / lock-feature checks read from
/// that empty field).
///
/// Call this anywhere we LEARN the subscription state — Superwall
/// delegate callbacks, post-purchase, post-restore. No-op if the value
/// is unchanged in both places. Safe to call before signup completes
/// (skips the Supabase write when there's no real user id yet).
Future<void> supabasePersistSubscriptionStatus(String status) async {
  if (status.isEmpty) return;

  final user = FFAppState().user;
  final localChanged = user.subscriptionStatus != status;
  if (localChanged) {
    FFAppState().update(() {
      FFAppState().user = user..subscriptionStatus = status;
    });
  }

  final userId = user.id;
  // No Supabase write before signup completes — the row doesn't exist
  // yet, and the alias-prefixed transitional id ("$SuperwallAlias:...") is
  // not a uuid the profiles table will accept. After signup, the value
  // will be persisted by the first `supabasePersistSubscriptionStatus`
  // call following identify.
  if (userId.isEmpty || userId.contains('Superwall')) return;

  try {
    await SupaFlow.client
        .from('profiles')
        .update({'subscription_status': status}).eq('id', userId);
  } catch (e) {
    debugPrint('Failed to persist subscription_status to Supabase: $e');
  }
}
