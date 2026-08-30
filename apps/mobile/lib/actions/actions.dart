import 'dart:async';

import '/auth/supabase_auth/auth_util.dart';
import '/backend/posthog/posthog_analytics.dart';
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/profile/version_update_dialog/version_update_dialog_widget.dart';
import '/components/review_dialog/review_dialog_widget.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/custom_functions.dart' as functions;
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:flutter/material.dart';
import 'package:purchases_flutter/purchases_flutter.dart';
import 'package:superwallkit_flutter/superwallkit_flutter.dart';

Future postAuth(
  BuildContext context, {
  String? superWallUserId,
  String? revenueCatUserId,
}) async {
  FFAppState().updateUserStruct(
    (e) => e
      ..id = currentUserUid
      ..email = currentUserEmail
      ..superWallUserId = superWallUserId
      ..revenueCatId = revenueCatUserId,
  );
  final isNewUser = !FFAppState().setting.onboarded;
  if (isNewUser) {
    await actions.supabaseUploadSurveys();
  }
  FFAppState().updateSettingStruct(
    (e) => e
      ..isGuest = false
      ..onboarded = true,
  );
  if (isNewUser) {
    posthogCapture('onboarding_completed');
  }

  // Tell RevenueCat and Superwall about our real user ID so that webhooks
  // for future purchases arrive with our UUID as `app_user_id` and the
  // backend can resolve the user without reverse-lookup. Wrapped so SDK
  // failures never break the auth flow; pre-auth purchases still fall back
  // to the `profiles.{revenuecat,superwall}_id` reverse-lookup path.
  if (currentUserUid.isNotEmpty) {
    try {
      await Purchases.logIn(currentUserUid);
    } catch (e) {
      debugPrint('Purchases.logIn failed: $e');
    }
    try {
      await Superwall.shared.identify(currentUserUid);
    } catch (e) {
      debugPrint('Superwall.identify failed: $e');
    }
  }

  await actions.supabaseSyncProfile();

  // Backfill any subscription that was purchased BEFORE signup (our paywall
  // sits ahead of AuthOptions, so the initial_purchase webhook for a new
  // user arrives with no resolvable user). Backend reads
  // profiles.superwall_id and asks Superwall's V2 API directly. Fire-and-
  // forget — failure must not block post-auth navigation, and the next
  // /billing/mobile/status poll will catch up regardless.
  unawaited(actions.apiReconcileSuperwallSubscription());
}

Future checkVersion(BuildContext context) async {
  String? latestVersion;

  FFAppState().appVersion = '1.7.8';
  if (FFAppState().appVersion == FFAppState().setting.versionNotified) {
    return;
  }
  latestVersion = await actions.supabaseFetchAppVersion();
  if (functions.isNewerVersion(FFAppState().appVersion, latestVersion!)) {
    await showDialog(
      context: context,
      builder: (dialogContext) {
        return Dialog(
          elevation: 0,
          insetPadding: EdgeInsets.zero,
          backgroundColor: Colors.transparent,
          alignment: AlignmentDirectional(0.0, 0.0)
              .resolve(Directionality.of(context)),
          child: Container(
            width: MediaQuery.sizeOf(context).width * 0.8,
            child: VersionUpdateDialogWidget(),
          ),
        );
      },
    );

    FFAppState().updateSettingStruct(
      (e) => e..versionNotified = FFAppState().appVersion,
    );
  }
}

Future grantCredit(
  BuildContext context, {
  required int? creditGranted,
  required String? name,
}) async {
  if (creditGranted! > 0) {
    final timestamp = getCurrentTimestamp;
    FFAppState().updateCreditStruct(
      (e) => e
        ..incrementBalance(creditGranted!)
        ..updatedAt = timestamp,
    );
    FFAppState().addToCreditTransactions(CreditTransactionStruct(
      name: name,
      type: 'debit',
      amount: creditGranted,
      createdAt: timestamp,
    ));

    unawaited(
      _persistCreditChangeBestEffort(
        name: name ?? '',
        type: 'debit',
        amount: creditGranted,
        createdAt: timestamp,
      ),
    );
  }
}

Future useCredit(
  BuildContext context, {
  required int? usedCredit,
  required String? name,
}) async {
  final hasActiveSubscription = await actions.hasActiveSubscription();
  if ((usedCredit! > 0) &&
      (usedCredit! <= FFAppState().credit.balance) &&
      !hasActiveSubscription) {
    final timestamp = getCurrentTimestamp;
    FFAppState().updateCreditStruct(
      (e) => e
        ..incrementBalance(-(usedCredit!))
        ..updatedAt = timestamp,
    );
    FFAppState().addToCreditTransactions(CreditTransactionStruct(
      name: name,
      type: 'credit',
      amount: usedCredit,
      createdAt: timestamp,
    ));

    unawaited(
      _persistCreditChangeBestEffort(
        name: name ?? '',
        type: 'credit',
        amount: usedCredit,
        createdAt: timestamp,
      ),
    );

    // Prompt for review when user's credit drops below 40 for the first time
    final newBalance = FFAppState().credit.balance;
    if (!FFAppState().setting.hasPromptedReviewForUsingMessages &&
        newBalance < 40) {
      // Show review prompt after a short delay
      Future.delayed(Duration(milliseconds: 500), () async {
        await showDialog(
          context: context,
          builder: (context) {
            return Dialog(
              backgroundColor: Colors.transparent,
              insetPadding: EdgeInsets.symmetric(horizontal: 24.0),
              child: ReviewDialogWidget(),
            );
          },
        );

        // Mark as prompted so we don't show again
        FFAppState().updateSettingStruct(
            (setting) => setting.hasPromptedReviewForUsingMessages = true);
      });
    }
  }
}

Future<void> _persistCreditChangeBestEffort({
  required String name,
  required String type,
  required int amount,
  required DateTime createdAt,
}) async {
  final userId = currentUserUid;
  if (userId.isEmpty || userId.contains('Superwall')) {
    return;
  }

  final nowUtc = DateTime.now().toUtc().toIso8601String();
  final createdAtUtc = createdAt.toUtc().toIso8601String();
  final localBalance = FFAppState().credit.balance;
  final txPayload = {
    'user_id': userId,
    'name': name,
    'type': type,
    'amount': amount,
    'created_at': createdAtUtc,
  };
  final profilePayload = {
    'id': userId,
    'credits': localBalance,
    'updated_at': nowUtc,
  };

  try {
    // Non-blocking write-through: transaction + latest balance snapshot.
    await SupaFlow.client.from('credit_transactions').insert(txPayload);
    await SupaFlow.client.from('profiles').upsert(profilePayload);
  } catch (e, st) {
    logFirebaseEvent(
      'credit_sync_failed',
      parameters: {
        'name': name,
        'type': type,
        'amount': amount,
      },
    );
    unawaited(FirebaseCrashlytics.instance.recordError(
      e,
      st,
      reason: 'Async credit sync failed',
      fatal: false,
    ));

    // One lightweight retry to reduce temporary network loss.
    Future.delayed(const Duration(seconds: 3), () async {
      try {
        await SupaFlow.client.from('credit_transactions').insert(txPayload);
        await SupaFlow.client.from('profiles').upsert(profilePayload);
      } catch (_) {}
    });
  }
}
