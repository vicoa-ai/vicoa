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

/// Fetches the latest credit balance from Supabase profiles and updates local state.
/// Returns the updated balance, or null if the fetch failed.
Future<int?> supabaseRefreshCreditBalance() async {
  final userId = FFAppState().user.id;

  if (userId.isEmpty || userId.contains('Superwall')) {
    debugPrint('Skipping credit refresh - user not logged in with real UUID');
    return null;
  }

  try {
    final response = await SupaFlow.client
        .from('profiles')
        .select('credits')
        .eq('id', userId)
        .maybeSingle();

    if (response != null) {
      final balance = response['credits'] as int? ?? FFAppState().credit.balance;
      FFAppState().updateCreditStruct((credit) => credit..balance = balance);
      debugPrint('Credit balance refreshed: $balance');
      return balance;
    }
  } catch (e) {
    debugPrint('Failed to refresh credit balance: $e');
  }

  return null;
}
