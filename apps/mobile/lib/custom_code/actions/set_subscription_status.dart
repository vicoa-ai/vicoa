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

import 'package:superwallkit_flutter/superwallkit_flutter.dart';

Future setSubscriptionStatus() async {
  SubscriptionStatus status = await Superwall.shared.getSubscriptionStatus();

  final user = FFAppState().user;
  String? next;

  if ((user.subscriptionStatus.isEmpty ||
          user.subscriptionStatus == "inactive") &&
      status is SubscriptionStatusActive) {
    next = "active";
  } else if (user.subscriptionStatus == "active" &&
      (status is SubscriptionStatusInactive ||
          status is SubscriptionStatusUnknown)) {
    next = "inactive";
  }

  if (next != null) {
    // Push to BOTH FFAppState and Supabase. Updating only FFAppState used
    // to leave Supabase carrying an empty string forever — every "is the
    // user Pro?" check that reads profiles.subscription_status would say no.
    await supabasePersistSubscriptionStatus(next);
    print("Update subscription status to $next");
  }
}
