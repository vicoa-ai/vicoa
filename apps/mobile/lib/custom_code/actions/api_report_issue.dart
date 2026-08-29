// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'vicoa_api_request.dart';

Future<bool> apiReportIssue(String message) async {
  try {
    await vicoaApiRequest('post', '/api/v1/support/report-issue', {
      'message': message,
    });
    return true;
  } catch (_) {
    return false;
  }
}
