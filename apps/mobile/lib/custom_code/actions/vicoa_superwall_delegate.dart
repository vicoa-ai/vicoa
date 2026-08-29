// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart';
import '/flutter_flow/custom_functions.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:async';

import 'package:superwallkit_flutter/superwallkit_flutter.dart';
import '/backend/posthog/posthog_analytics.dart';

class VoaSuperwallDelegate extends SuperwallDelegate {
  // didDismissPaywall fires for every dismissal but doesn't carry the cause;
  // we capture the most recent user-intent event here so the dismissal can
  // be tagged (close / decline / purchased / silent / etc.).
  DateTime? _presentedAt;
  String? _exitIntent;

  @override
  Future<void> handleSuperwallEvent(SuperwallEventInfo eventInfo) async {
    final event = eventInfo.event;
    final product = event.product;
    final paywallInfo = event.paywallInfo;

    switch (event.type) {
      case EventType.paywallOpen:
        posthogCapture('paywall_opened', properties: {
          if (paywallInfo?.name != null) 'paywall_name': paywallInfo!.name as Object,
          if (paywallInfo?.presentedByPlacementWithName != null)
            'placement': paywallInfo!.presentedByPlacementWithName! as Object,
        });
        break;

      case EventType.paywallClose:
        _exitIntent = 'close';
        posthogCapture('paywall_close_button_tapped', properties: {
          if (paywallInfo?.name != null) 'paywall_name': paywallInfo!.name as Object,
        });
        break;

      case EventType.paywallDecline:
        _exitIntent = 'decline';
        posthogCapture('paywall_declined', properties: {
          if (paywallInfo?.name != null) 'paywall_name': paywallInfo!.name as Object,
        });
        break;

      case EventType.transactionComplete:
        _exitIntent = 'purchased';
        posthogCapture('subscription_purchased', properties: {
          if (product?.productIdentifier != null)
            'product_id': product!.productIdentifier as Object,
          if (product?.localizedPrice != null) 'price': product!.localizedPrice as Object,
          if (product?.period != null) 'period': product!.period as Object,
          if (paywallInfo?.name != null) 'paywall_name': paywallInfo!.name as Object,
        });
        // Only identify when the user is authenticated — pre-auth purchases are
        // tracked under PostHog's anonymous ID and merged after sign-in.
        final userId = FFAppState().user.id;
        if (userId.isNotEmpty && !userId.contains('Superwall')) {
          posthogIdentify(
            userId: userId,
            userProperties: {
              'subscription_status': 'active',
              if (product?.productIdentifier != null)
                'product_id': product!.productIdentifier as Object,
            },
          );
        }
        break;

      case EventType.subscriptionStart:
        posthogCapture('subscription_started', properties: {
          if (product?.productIdentifier != null)
            'product_id': product!.productIdentifier as Object,
          if (product?.period != null) 'period': product!.period as Object,
        });
        break;

      case EventType.freeTrialStart:
        _exitIntent = 'trial_started';
        posthogCapture('free_trial_started', properties: {
          if (product?.productIdentifier != null)
            'product_id': product!.productIdentifier as Object,
          if (product?.period != null) 'period': product!.period as Object,
        });
        break;

      case EventType.transactionRestore:
        _exitIntent = 'restored';
        posthogCapture('subscription_restored', properties: {
          if (product?.productIdentifier != null)
            'product_id': product!.productIdentifier as Object,
        });
        break;

      case EventType.transactionFail:
        // Paywall stays open after a failed purchase — do not set _exitIntent.
        // `error_category` groups Apple's localized error strings into a small
        // set of actionable buckets so we can size each failure mode without
        // hand-reading 50+ unique strings/week. English-only matching by
        // design — non-English locales fall to 'unknown' until volume justifies
        // a code-based classifier (would need Superwall to surface NSError.code).
        posthogCapture('subscription_purchase_error', properties: {
          'error_category': _classifyPurchaseError(event.error),
          if (event.error != null) 'error': event.error! as Object,
          if (product?.productIdentifier != null)
            'product_id': product!.productIdentifier as Object,
        });
        break;

      default:
        break;
    }
  }

  // Required abstract methods — no-op implementations
  @override
  void subscriptionStatusDidChange(SubscriptionStatus newValue) {
    // Superwall fires this the moment entitlement changes — including the
    // async confirmation right after a purchase, and when the SDK resolves
    // entitlements on launch. Mirror it into BOTH local state and Supabase
    // (profiles.subscription_status) so any UI / SQL reading that field
    // updates without a refresh. Only ever upgrade here; downgrades are
    // left to setSubscriptionStatus / backend sync so a transient
    // `Unknown` / `Inactive` on launch can't strip Pro from a paid user.
    // The message gate itself reads Superwall live, so it doesn't depend
    // on this.
    if (newValue is SubscriptionStatusActive) {
      final user = FFAppState().user;
      if (user.subscriptionStatus.isEmpty ||
          user.subscriptionStatus == 'inactive') {
        // Fire and forget — failure to PATCH Supabase shouldn't block the
        // UI tick that just learned the entitlement changed.
        unawaited(supabasePersistSubscriptionStatus('active'));
      }
    }
  }

  @override
  void handleCustomPaywallAction(String name) {}

  @override
  void willDismissPaywall(PaywallInfo paywallInfo) {}

  @override
  void willPresentPaywall(PaywallInfo paywallInfo) {
    _presentedAt = DateTime.now();
    _exitIntent = null;
  }

  @override
  void didDismissPaywall(PaywallInfo paywallInfo) {
    // reason ∈ {close, decline, purchased, trial_started, restored, silent}.
    // 'silent' means no preceding user-intent event — system back, swipe
    // down, app dismiss — the bucket we want to make visible.
    final reason = _exitIntent ?? 'silent';
    final timeOnScreenMs = _presentedAt == null
        ? null
        : DateTime.now().difference(_presentedAt!).inMilliseconds;
    posthogCapture('paywall_dismissed', properties: {
      'reason': reason,
      if (timeOnScreenMs != null) 'time_on_screen_ms': timeOnScreenMs,
      if (paywallInfo.name != null) 'paywall_name': paywallInfo.name as Object,
    });
    _presentedAt = null;
    _exitIntent = null;
  }

  @override
  void didPresentPaywall(PaywallInfo paywallInfo) {}

  @override
  void paywallWillOpenURL(Uri url) {}

  @override
  void paywallWillOpenDeepLink(Uri url) {}

  @override
  void handleLog(String level, String scope, String? message,
      Map<dynamic, dynamic>? info, String? error) {}

  @override
  void handleSuperwallDeepLink(Uri fullURL, List<String> pathComponents,
      Map<String, String> queryParameters) {}
}

String _classifyPurchaseError(String? error) {
  if (error == null || error.isEmpty) return 'missing';
  final s = error.toLowerCase();
  bool has(List<String> needles) => needles.any(s.contains);
  if (has(['cannot connect', 'connection', 'network', 'internet', 'itunes store'])) return 'network';
  // 'play_unavailable' must come before 'declined' — Play's "Billing unavailable"
  // contains "billing" and would otherwise match the declined bucket.
  if (has(['billing unavailable', 'billing is unavailable', 'google play', 'play services', 'play store'])) return 'play_unavailable';
  if (has(['not allowed', 'screen time', 'restricted', 'parental', 'ask permission', 'ask to buy'])) return 'parental';
  if (has(['deferred', 'pending', 'awaiting'])) return 'deferred';
  if (has(['declined', 'invalid', 'card', 'billing', 'expired'])) return 'declined';
  if (s.contains('cancel')) return 'cancelled';
  return 'unknown';
}
