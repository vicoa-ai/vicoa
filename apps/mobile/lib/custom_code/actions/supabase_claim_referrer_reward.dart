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

Future<int> supabaseClaimReferrerReward(
    BuildContext context, String referrerId) async {
  final supabase = SupaFlow.client;

  try {
    // Query all referrals where the user is the referrer and hasn't claimed the reward
    final referrals = await supabase
        .from('referrals')
        .select('id')
        .eq('referrer_id', referrerId)
        .eq('grant_referrer_credits', false);

    if (referrals.isEmpty) {
      debugPrint('No pending rewards to claim.');
      return 0;
    }

    int totalCredits = referrals.length * 50; // 50 messages per referral

    action_blocks.grantCredit(context,
        creditGranted: totalCredits, name: "Refer Friends");

    // Mark all referrals as rewarded
    final referralIds = referrals.map((r) => r['id']).toList();
    await supabase.from('referrals').update({
      'grant_referrer_credits': true,
      'updated_at': DateTime.now().toIso8601String(),
    }).inFilter('id', referralIds);

    debugPrint('Rewards claimed successfully!');
    return totalCredits;
  } catch (e) {
    debugPrint('Error claiming referrer reward: $e');
    return 0;
  }
}
