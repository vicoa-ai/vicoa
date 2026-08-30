// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'vicoa_api_request.dart';

/// Sends a scenario-driven transactional email via the backend.
///
/// The client only describes *what happened* (a [scenario] plus optional
/// [context]); the backend picks the template and recipient. Supported
/// scenarios today: `get_started` (emails the user a CLI setup link) and
/// `waitlist_signup` (notifies the team with the user's choice/notes).
///
/// Returns true when the backend reports the email was sent.
Future<bool> apiSendEmail(
  String scenario, [
  Map<String, dynamic>? context,
]) async {
  try {
    await vicoaApiRequest('post', '/api/v1/emails/send', {
      'scenario': scenario,
      if (context != null) 'context': context,
    });
    return true;
  } catch (_) {
    return false;
  }
}
