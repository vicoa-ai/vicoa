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

Future<bool> supabaseValidateReferralCode(String referralCode) async {
  // Validate inputs
  if (referralCode.isEmpty) {
    debugPrint('Error: referralCode must not be empty');
    return false;
  }

  final supabase = SupaFlow.client;

  try {
    final referralCodeData = await supabase
        .from('referral_codes')
        .select('user_id')
        .eq('code', referralCode)
        .maybeSingle();

    if (referralCodeData != null) {
      return true;
    } else {
      debugPrint('Failed to validate referral code $referralCode');
      return false;
    }
  } catch (e) {
    debugPrint('Error validating referral code: $e');
    return false;
  }
}
