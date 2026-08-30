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

// Set your action name, define your arguments and return parameter,
// and then add the boilerplate code using the green button on the right!

Future<String?> supabaseGetReferrerId(String referralCode) async {
  // Validate inputs
  if (referralCode.isEmpty) {
    debugPrint('Error: referralCode must not be empty');
    return null;
  }

  final supabase = SupaFlow.client;

  try {
    final referralCodeData = await supabase
        .from('referral_codes')
        .select('user_id')
        .eq('code', referralCode)
        .maybeSingle();

    if (referralCodeData != null) {
      return referralCodeData['user_id'];
    } else {
      debugPrint('Failed to get referrer id with refereral code $referralCode');
      return null;
    }
  } catch (e) {
    debugPrint('Error getting referrer ID: $e');
    return null;
  }
}
