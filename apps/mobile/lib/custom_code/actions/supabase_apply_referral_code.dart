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

Future<bool> supabaseApplyReferralCode(
    String referreeId, String referralCode) async {
  // Validate inputs
  if (referreeId.isEmpty || referralCode.isEmpty) {
    debugPrint('Error: referreeId and referralCode must not be empty');
    return false;
  }

  final supabase = SupaFlow.client;

  try {
    // Check if referral code exists
    final referralCodeData = await supabase
        .from('referral_codes')
        .select('user_id')
        .eq('code', referralCode)
        .maybeSingle();

    if (referralCodeData != null) {
      final referrerId = referralCodeData['user_id'];

      final now = DateTime.now().toIso8601String();
      // Create a new referral record
      await supabase.from('referrals').insert({
        'referral_code': referralCode,
        'referrer_id': referrerId,
        'referree_id': referreeId,
        'grant_referrer_credits': false,
        'grant_referree_credits': true,
        'created_at': now,
        'updated_at': now,
      });

      debugPrint('Referral applied successfully!');
      return true;
    } else {
      debugPrint('Failed to apply referral code $referralCode');
      return false;
    }
  } catch (e) {
    debugPrint('Error applying referral code: $e');
    return false;
  }
}
