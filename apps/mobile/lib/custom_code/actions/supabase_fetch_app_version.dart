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

import 'dart:io';

Future<String?> supabaseFetchAppVersion() async {
  final supabase = SupaFlow.client;

  // Determine platform
  String platform;
  if (Platform.isIOS) {
    platform = 'ios';
  } else if (Platform.isAndroid) {
    platform = 'android';
  } else {
    debugPrint('Unsupported platform');
    return null;
  }

  try {
    final response = await supabase
        .from('app_versions')
        .select('version')
        .eq('platform', platform)
        .order('created_at', ascending: false)
        .limit(1)
        .maybeSingle();

    if (response != null) {
      return response['version'];
    } else {
      debugPrint('No version found for platform: $platform');
      return null;
    }
  } catch (e) {
    debugPrint('Error fetching app version: $e');
    return null;
  }
}
