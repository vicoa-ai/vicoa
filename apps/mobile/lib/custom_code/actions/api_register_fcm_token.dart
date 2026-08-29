// Automatic FlutterFlow imports
import 'dart:io';

// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter/foundation.dart';
import '/custom_code/actions/vicoa_api_request.dart';

/// Registers the FCM token with the backend.
///
/// Returns `true` only when the backend accepted the token (HTTP 2xx).
/// `vicoaApiRequest` throws on any non-2xx / auth / network error, so a
/// non-throwing await here means the token is persisted server-side. Callers
/// use this to avoid marking a token as registered when the POST actually
/// failed (previously the failure was swallowed and never retried).
Future<bool> apiRegisterFcmToken(String? fcmToken) async {
  if (fcmToken == null || fcmToken.isEmpty) {
    if (kDebugMode) {
      print('FCM token is null or empty, cannot register');
    }
    return false;
  }

  try {
    // Register FCM token via API
    await vicoaApiRequest(
      'post',
      '/api/v1/push/register',
      {
        'token': fcmToken,
        'platform': Platform.isIOS ? 'ios' : 'android',
      },
    );

    if (kDebugMode) {
      print('FCM token registered successfully');
    }
    return true;
  } catch (e) {
    if (kDebugMode) {
      print('Error registering FCM token: $e');
    }
    return false;
  }
}