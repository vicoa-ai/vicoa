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

Future<bool> apiKitSubscription(String email) async {
  try {
    // TODO: Implement it in the backend
    await vicoaApiRequest(
      'post',
      '/api/v1/convertkit/subscribe',
      {'email': email},
    );
    return true;
  } catch (e) {
    debugPrint('Failed to tag ConvertKit user: $e');
    return false;
  }
}
