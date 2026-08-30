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

Future supabaseSyncProfile() async {
  final userId = FFAppState().user.id;
  final nowUtc = DateTime.now().toUtc().toIso8601String();

  if (userId.isEmpty || userId.contains('Superwall')) {
    debugPrint('Skipping profile sync - user not logged in with real UUID');
    return;
  }

  // Only persist anonymous SDK aliases — uuid is already in profiles.id, and
  // overwriting an existing anon ID with a uuid would break reverse-lookup
  // for any pre-identify webhook that arrives with the original alias.
  // Superwall's getUserId() returns the current (post-identify) id, so this
  // guard matters; RC's originalAppUserId is immutable but we apply the same
  // rule for symmetry. The Superwall alias prefix is `$SuperwallAlias:` —
  // case-insensitive compare so a casing change upstream doesn't drop the
  // write silently the way the original lowercase-only check did.
  final swId = FFAppState().user.superWallUserId;
  final rcId = FFAppState().user.revenueCatId;
  final swIdAnon = swId.toLowerCase().startsWith(r'$superwallalias') ? swId : null;
  final rcIdAnon = rcId.startsWith(r'$RC') ? rcId : null;

  try {
    await SupaFlow.client.from('profiles').upsert({
      'id': userId,
      'display_name': FFAppState().user.name,
      'subscription_status': FFAppState().user.subscriptionStatus,
      if (swIdAnon != null) 'superwall_id': swIdAnon,
      if (rcIdAnon != null) 'revenuecat_id': rcIdAnon,
      'created_at': FFAppState().user.createdAt?.toUtc().toIso8601String() ?? nowUtc,
      'updated_at': FFAppState().user.updatedAt?.toUtc().toIso8601String() ?? nowUtc,
    });
  } catch (e) {
    debugPrint('Failed to sync profile: $e');
  }
}
