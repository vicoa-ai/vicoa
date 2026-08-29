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
import '/flutter_flow/internationalization.dart';

Future registerSuperWallEvent(BuildContext context, String eventName,
    String nextPageRoute, bool justDismiss) async {
  void proceed() {
    if (!justDismiss && nextPageRoute.isNotEmpty && context.mounted) {
      context.pushNamed(nextPageRoute);
    }
  }

  try {
    final hasSubscription = await hasActiveSubscription();
    if (hasSubscription) {
      proceed();
      return;
    }

    // Simplified-Chinese (mainland) users get the localized `<placement>_cn`
    // paywall when that campaign exists in Superwall; otherwise they fall back to
    // the base placement. `getPresentationResult` is a local dry-run against the
    // cached config (no extra network call) and, unlike onSkip, doesn't present
    // or run the feature block, so probing is side-effect-free. Traditional
    // Chinese (TW/HK/MO) and everyone else always use the base placement.
    var placement = eventName;
    if (isSimplifiedChineseLocale(FFAppState().appLanguage)) {
      final cnPlacement = '${eventName}_cn';
      try {
        final probe = await Superwall.shared.getPresentationResult(cnPlacement);
        if (probe is PaywallPresentationResult) placement = cnPlacement;
      } catch (_) {
        // Probe failed (e.g. config not yet loaded) — keep the base placement.
      }
    }

    final handler = PaywallPresentationHandler();
    handler.onSkip((reason) => proceed());
    handler.onError((error) => proceed());

    Superwall.shared.registerPlacement(placement, handler: handler,
        feature: () async {
      if (justDismiss == true) {
        Superwall.shared.dismiss();
        await setSubscriptionStatus();
      } else {
        await setSubscriptionStatus();
        if (context.mounted) context.pushNamed(nextPageRoute);
      }
    });
  } on Exception catch (e) {
    print("Superwall failed to register event: $e");
    proceed();
  }
}
