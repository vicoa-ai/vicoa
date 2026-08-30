// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<int> supabaseGetReferralCount(
    BuildContext context, String referrerId) async {
  final supabase = SupaFlow.client;

  try {
    // Query all successful referrals where the user is the referrer
    final referrals = await supabase
        .from('referrals')
        .select('id')
        .eq('referrer_id', referrerId);

    return referrals.length;
  } catch (e) {
    debugPrint('Error getting referral count: $e');
    return 0;
  }
}