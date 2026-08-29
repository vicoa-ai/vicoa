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
import 'package:uuid/uuid.dart';

Future<String> getSuperWallUserId() async {
  // Add your function code here!

  try {
    String userId = await Superwall.shared.getUserId();
    print("Superwall user id, $userId");
    return userId;
  } on Exception catch (e) {
    print("Superwall failed to user id: $e");
    return Uuid().v4();
  }
}
