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

import 'dart:io' show Platform;

import 'package:superwallkit_flutter/superwallkit_flutter.dart';
import 'vicoa_superwall_delegate.dart';

Future initSuperWall() async {
  // Add your function code here!
  try {
    String apiKey = Platform.isIOS
        ? "pk_8XEslnl5-cR7P1gEeexUe"
        : "pk_y1tIozfGLj65ugeManYk8";

    if (apiKey.isNotEmpty) {
      Superwall.configure(apiKey);
      Superwall.shared.setDelegate(VoaSuperwallDelegate());
    }
  } on Exception catch (e) {
    print("SuperWall initialization failed: $e");
  }
}
