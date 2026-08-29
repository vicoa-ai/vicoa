// Automatic FlutterFlow imports

// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter/foundation.dart';
import '/custom_code/actions/vicoa_api_request.dart';

Future<void> apiUnregisterFcmToken(String? fcmToken) async {
  if (fcmToken == null || fcmToken.isEmpty) {
    if (kDebugMode) {
      print('FCM token is null or empty, cannot unregister');
    }
    return;
  }

  try {
    // Unregister FCM token via API
    await vicoaApiRequest(
      'delete',
      '/api/v1/push/deactivate/$fcmToken',
      null,
    );

    if (kDebugMode) {
      print('FCM token unregistered successfully');
    }
  } catch (e) {
    if (kDebugMode) {
      print('Error unregistering FCM token: $e');
    }
  }
}