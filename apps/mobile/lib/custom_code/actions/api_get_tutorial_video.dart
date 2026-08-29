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

Future<String> apiGetTutorialVideo() async {
  // Add your function code here!
  String endpoint = '/tutorial-video';
  String defaultVideo = 'https://i.imgur.com/V4EpW3y.mp4';

  try {
    final result = await vicoaApiRequest('get', endpoint, null);
    debugPrint("Tutorial video result: $result");
    final url = result['url'] as String?;
    if (url == null || url.isEmpty) {
      return defaultVideo;
    }
    return url;
  } catch (e) {
    debugPrint("Failed to get tutorial video: $e");
    return defaultVideo;
  }
}
