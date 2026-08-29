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

import '/auth/supabase_auth/auth_util.dart';

Future supabaseCreateProfile(String id, String? superwallId, String? revenueCatId) async {
  try {
    final now = DateTime.now().toUtc().toIso8601String();
    // Seed subscription_status from whatever local state already knows:
    // Superwall's delegate may have already flipped it to "active" if the
    // user has a pre-existing entitlement (App Store family share, restored
    // purchase, returning user). Otherwise default to "inactive" so the
    // column isn't empty — readers like the dashboard / lockFeature checks
    // treat empty as ambiguous and were the root cause of paying users
    // showing up as non-Pro in Supabase.
    final localStatus = FFAppState().user.subscriptionStatus;
    final initialStatus = localStatus.isNotEmpty ? localStatus : 'inactive';
    await SupaFlow.client.from('profiles').insert({
      'id': id,
      'created_at': now,
      'updated_at': now,
      'superwall_id': superwallId,
      'revenuecat_id': revenueCatId,
      'display_name': currentUserDisplayName,
      'subscription_status': initialStatus,
    });
  } catch (e) {
    print('Failed to create profile: $e');
  }
}
