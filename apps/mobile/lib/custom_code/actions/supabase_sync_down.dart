// Automatic FlutterFlow imports
import '/auth/supabase_auth/auth_util.dart';
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

Future supabaseSyncDown(DateTime? syncStartTime) async {
  final supabase = SupaFlow.client;
  final userId =
      currentUserUid.isNotEmpty ? currentUserUid : FFAppState().user.id;
  final lastSyncDownAt = FFAppState().setting.lastSyncDownAt;
  final lastSyncDownAtUtc = lastSyncDownAt?.toUtc().toIso8601String();

  Map<String, dynamic> syncResult = {
    'profile': {'downloaded': 0, 'failed': 0},
    'creditTransactions': {'downloaded': 0, 'failed': 0},
  };

  // Skip sync if user is not logged in with real UUID
  if (userId.isEmpty || userId.contains('Superwall')) {
    debugPrint('Skipping sync - user not logged in with real UUID');
    return;
  }

  try {
    // Sync User Profile
    try {
      var profileQuery = supabase.from('profiles').select('*').eq('id', userId);

      if (lastSyncDownAtUtc != null) {
        profileQuery = profileQuery.gte('updated_at', lastSyncDownAtUtc);
      }
      final profileResponse = await profileQuery.maybeSingle();

      if (profileResponse != null) {
        final remoteDisplayName =
            (profileResponse['display_name'] ?? '').toString().trim();

        // Update local user data.
        // Keep existing local name when remote display_name is null/empty
        // (common right after first OAuth login when metadata has the name).
        FFAppState().updateUserStruct((user) => user
          ..name = remoteDisplayName.isNotEmpty ? remoteDisplayName : user.name
          ..subscriptionStatus =
              profileResponse['subscription_status'] ?? user.subscriptionStatus
          ..superWallUserId =
              profileResponse['superwall_id'] ?? user.superWallUserId
          ..revenueCatId =
              profileResponse['revenuecat_id'] ?? user.revenueCatId);

        // Update local credit data
        FFAppState().updateCreditStruct((credit) =>
            credit..balance = profileResponse['credits'] ?? credit.balance);

        syncResult['profile']['downloaded']++;
      }
    } catch (e) {
      debugPrint('Failed to sync user profile: $e');
      syncResult['profile']['failed']++;
    }

    // Sync Credit Transactions (only those created after lastSyncDownAt)
    try {
      var creditTransactionsQuery = supabase
          .from('credit_transactions')
          .select('*')
          .eq('user_id', userId);

      if (lastSyncDownAtUtc != null) {
        creditTransactionsQuery =
            creditTransactionsQuery.gte('created_at', lastSyncDownAtUtc);
      }

      final creditTransactionsResponse =
          await creditTransactionsQuery.order('created_at', ascending: false);

      List<CreditTransactionStruct> remoteCreditTransactions = [];

      for (final transactionData in creditTransactionsResponse) {
        try {
          remoteCreditTransactions.add(CreditTransactionStruct(
            name: transactionData['name'] ?? '',
            type: transactionData['type'] ?? '',
            amount: transactionData['amount'] ?? 0,
            createdAt: transactionData['created_at'] != null
                ? DateTime.tryParse(transactionData['created_at'])?.toLocal()
                : null,
          ));
          syncResult['creditTransactions']['downloaded']++;
        } catch (e) {
          debugPrint('Failed to process credit transaction: $e');
        }
      }
      // Add new transactions from remote
      for (final transaction in remoteCreditTransactions) {
        FFAppState().addToCreditTransactions(transaction);
      }
    } catch (e) {
      debugPrint('Failed to sync credit transactions: $e');
    }

    debugPrint('Remote data sync completed: $syncResult');

    // Update lastSyncDownAt after successful sync
    FFAppState().updateSettingStruct(
        (setting) => setting..lastSyncDownAt = DateTime.now());
    debugPrint('Updated lastSyncDownAt after successful download');
  } catch (error) {
    debugPrint('Failed to sync remote data: $error');
  }
}
