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

import 'dart:io' show Platform;

/// Ask the backend to reconcile the caller's subscription across all mobile
/// providers and upgrade the local subscription row if active. Two upgrade-only
/// legs run server-side:
///   - Superwall: recovers a purchase made BEFORE signup (the paywall fires
///     before AuthOptions, so the `initial_purchase` webhook arrives with no
///     resolvable user; the backend matches the pre-identify alias stored in
///     `profiles.superwall_id`).
///   - RevenueCat: re-fetches the live entitlement, recovering transferred or
///     restored subscriptions (RevenueCat "transfer to new App User ID") and
///     any purchase whose webhook was missed.
///
/// Sends the current platform as a hint (used by the Superwall leg). It is
/// idempotent and safe to call on every login.
///
/// Failures are swallowed: this is a best-effort backfill, not a blocker.
Future<void> apiReconcileSuperwallSubscription() async {
  String? platform;
  if (Platform.isIOS) {
    platform = 'ios';
  } else if (Platform.isAndroid) {
    platform = 'android';
  }
  try {
    final result = await vicoaApiRequest(
      'post',
      '/api/v1/billing/mobile/reconcile',
      {if (platform != null) 'platform': platform},
    );
    debugPrint('Subscription reconcile result: $result');
  } catch (e) {
    debugPrint('Subscription reconcile failed: $e');
  }
}
