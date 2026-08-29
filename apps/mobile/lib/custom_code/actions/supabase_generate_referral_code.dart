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

import 'dart:math';

Future<String?> supabaseGenerateReferralCode(String userId) async {
  final supabase = SupaFlow.client;

  String generateCode() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    final random = Random();
    return List.generate(8, (index) => chars[random.nextInt(chars.length)])
        .join();
  }

  String referralCode;
  bool exists;

  try {
    do {
      referralCode = generateCode();
      final response = await supabase
          .from('referral_codes')
          .select('code')
          .eq('code', referralCode)
          .maybeSingle();
      exists = response != null;
    } while (exists);

    // Insert the referral code in the referral_codes table
    await supabase.from('referral_codes').insert({
      'user_id': userId,
      'code': referralCode,
      'created_at': DateTime.now().toIso8601String(),
    });

    FFAppState().updateUserStruct(
      (e) => e..referralCode = referralCode,
    );

    return referralCode;
  } catch (e) {
    print('Error generating or uploading referral code: $e');
    return null;
  }
}
