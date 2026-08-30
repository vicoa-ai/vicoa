// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<String> apiGetDeepgramToken() async {
  try {
    final result = await vicoaApiRequest('post', '/api/v1/deepgram/token', {});
    if (result is Map<String, dynamic>) {
      final token = result['token']?.toString().trim() ?? '';
      if (token.isNotEmpty) {
        return token;
      }
    }
    throw const FormatException('Deepgram token missing from API response.');
  } on AuthenticationException {
    rethrow;
  } on ApiException {
    rethrow;
  } on NetworkException {
    rethrow;
  } on ServiceUnavailableException {
    rethrow;
  } catch (error) {
    debugPrint('Error fetching Deepgram token: $error');
    rethrow;
  }
}
