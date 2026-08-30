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

Future supabaseSyncUp() async {
  final supabase = SupaFlow.client;
  final userId = FFAppState().user.id;
  final nowUtc = DateTime.now().toUtc().toIso8601String();
  final lastSyncUpAt = FFAppState().setting.lastSyncUpAt;

  Map<String, dynamic> syncResult = {
    'profile': {'uploaded': 0, 'failed': 0},
    'creditTransactions': {'uploaded': 0, 'failed': 0},
    'surveys': {'uploaded': 0, 'failed': 0},
  };

  // Skip sync if user is not logged in with real UUID
  if (userId.isEmpty || userId.contains('Superwall')) {
    debugPrint('Skipping sync - user not logged in with real UUID');
    return;
  }

  try {
    // Sync User Profile (only if updated after lastSyncUpAt)
    try {
      final userUpdatedAt = FFAppState().user.updatedAt;

      if (lastSyncUpAt == null ||
          (userUpdatedAt != null && userUpdatedAt.isAfter(lastSyncUpAt))) {
        // Only persist anonymous SDK aliases — see supabase_sync_profile.dart.
        // Case-insensitive Superwall prefix check so the actual
        // `$SuperwallAlias:` value isn't dropped.
        final swId = FFAppState().user.superWallUserId;
        final rcId = FFAppState().user.revenueCatId;
        final swIdAnon = swId.toLowerCase().startsWith(r'$superwallalias') ? swId : null;
        final rcIdAnon = rcId.startsWith(r'$RC') ? rcId : null;

        await supabase.from('profiles').upsert({
          'id': userId,
          'display_name': FFAppState().user.name,
          'subscription_status': FFAppState().user.subscriptionStatus,
          if (swIdAnon != null) 'superwall_id': swIdAnon,
          if (rcIdAnon != null) 'revenuecat_id': rcIdAnon,
          'credits': FFAppState().credit.balance,
          'created_at':
              FFAppState().user.createdAt?.toUtc().toIso8601String() ?? nowUtc,
          'updated_at':
              FFAppState().user.updatedAt?.toUtc().toIso8601String() ?? nowUtc,
        });
        syncResult['profile']['uploaded']++;
      }
    } catch (e) {
      debugPrint('Failed to sync user profile: $e');
      syncResult['profile']['failed']++;
    }

    // Sync Credit Transactions (only those created after lastSyncUpAt)
    final creditTransactionsToSync = lastSyncUpAt != null
        ? FFAppState()
            .creditTransactions
            .where((transaction) =>
                transaction.createdAt?.isAfter(lastSyncUpAt) ?? false)
            .toList()
        : FFAppState().creditTransactions;
    for (final transaction in creditTransactionsToSync) {
      try {
        await supabase.from('credit_transactions').insert({
          'user_id': userId,
          'name': transaction.name,
          'type': transaction.type,
          'amount': transaction.amount,
          'created_at':
              transaction.createdAt?.toUtc().toIso8601String() ?? nowUtc,
        });
        syncResult['creditTransactions']['uploaded']++;
      } catch (e) {
        debugPrint('Failed to sync credit transaction ${transaction.name}: $e');
        syncResult['creditTransactions']['failed']++;
      }
    }

    // // Sync Surveys (already handled by existing supabaseUploadSurveys function)
    // try {
    //   await supabaseUploadSurveys();
    //   syncResult['surveys']['uploaded'] = FFAppState().surveys.length;
    // } catch (e) {
    //   debugPrint('Failed to sync surveys: $e');
    //   syncResult['surveys']['failed'] = FFAppState().surveys.length;
    // }


    debugPrint('Local data sync completed: $syncResult');

    // Update lastSyncUpAt after successful sync
    FFAppState().updateSettingStruct(
        (setting) => setting..lastSyncUpAt = DateTime.now());
    debugPrint('Updated lastSyncUpAt after successful upload');
  } catch (error) {
    debugPrint('Failed to sync local data: $error');
  }
}
