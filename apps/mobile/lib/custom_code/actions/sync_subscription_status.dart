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

import 'package:superwallkit_flutter/superwallkit_flutter.dart';

DateTime? _lastMobileBillingCheckAt;
Future<bool>? _mobileBillingCheckInFlight;
bool _cachedMobileBillingIsPro = false;
const Duration _mobileBillingCheckTtl = Duration(minutes: 2);

String? _extractPlanType(dynamic response) {
  if (response is Map) {
    final directPlanType = response['plan_type']?.toString().toLowerCase();
    if (directPlanType != null && directPlanType.isNotEmpty) {
      return directPlanType;
    }
    final data = response['data'];
    if (data is Map) {
      return data['plan_type']?.toString().toLowerCase();
    }
  }
  return null;
}

Future<bool> hasActiveSubscription({bool forceRefresh = false}) async {
  // 1. Fast path: trust the locally persisted flag. This is a synchronous
  //    in-memory read, so hot-path gating callers (credit use, message send)
  //    don't pay a Superwall SDK round-trip on every call. Guarded by
  //    !forceRefresh so the profile/usage pages (which pass forceRefresh:true)
  //    always reach the live sources below, detect a cancellation, and write
  //    the corrected value back into this flag — keeping the cache honest.
  if (!forceRefresh && isActiveSubscription(FFAppState().user.subscriptionStatus)) {
    return true;
  }

  // 2. Superwall — a live SDK read of the device's StoreKit/Play entitlement,
  //    so a fresh purchase is reflected immediately and a cancellation is too.
  try {
    final swStatus = await Superwall.shared.getSubscriptionStatus();
    if (swStatus is SubscriptionStatusActive) {
      return true;
    }
  } catch (e) {
    debugPrint('Superwall subscription check failed: $e');
  }

  // 3. Backend billing status (cached) as the final fallback. Covers purchases
  //    Superwall doesn't own (e.g. the RevenueCat paywall on the NoCreditSheet).
  final mobileBillingIsPro = await syncSubscriptionStatus(forceRefresh: forceRefresh);
  return mobileBillingIsPro;
}

Future<bool> syncSubscriptionStatus({bool forceRefresh = false}) async {
  final now = DateTime.now();
  if (!forceRefresh && _mobileBillingCheckInFlight != null) {
    return _mobileBillingCheckInFlight!;
  }
  if (!forceRefresh &&
      _lastMobileBillingCheckAt != null &&
      now.difference(_lastMobileBillingCheckAt!) < _mobileBillingCheckTtl) {
    return _cachedMobileBillingIsPro;
  }

  final future = _checkMobileBillingSubscriptionInternal();
  _mobileBillingCheckInFlight = future;
  try {
    return await future;
  } finally {
    _mobileBillingCheckInFlight = null;
    _lastMobileBillingCheckAt = DateTime.now();
  }
}

Future<bool> _checkMobileBillingSubscriptionInternal() async {
  try {
    final response = await apiGetMobileSubscriptionStatus();
    final planType = _extractPlanType(response);
    _cachedMobileBillingIsPro = planType == 'pro';
  } on AuthenticationException {
    _cachedMobileBillingIsPro = false;
    debugPrint('Skipping mobile billing subscription check: unauthenticated user.');
  } catch (e) {
    debugPrint('Failed to fetch mobile billing subscription status: $e. Using cached value.');
  }
  return _cachedMobileBillingIsPro;
}
