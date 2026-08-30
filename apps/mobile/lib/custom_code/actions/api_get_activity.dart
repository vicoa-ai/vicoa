// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Fetches the signed-in user's all-time activity summary from the backend
/// (`GET /api/v1/activity`). The map includes `total_user_messages` — a
/// per-user, server-side count of messages the user has actually sent to a
/// real agent. Unlike the device-level `hasSentFirstMobileMessage` flag, this
/// is scoped to the account (correct for a new user on a used device) and is
/// never inflated by the local welcome-demo sample chat (those messages never
/// reach the server).
Future<Map<String, dynamic>> apiGetActivity() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/activity', null);

    if (result is Map) {
      return Map<String, dynamic>.from(result);
    }

    return {};
  } on AuthenticationException {
    rethrow; // Let caller handle auth errors
  } on NetworkException {
    rethrow; // Let caller handle network errors
  } catch (e) {
    debugPrint('Error fetching activity: $e');
    return {}; // Return empty for unexpected errors
  }
}
