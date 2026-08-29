// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiGetMobileSubscriptionStatus() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/billing/mobile/status', null);
    return result;
  } on AuthenticationException {
    rethrow;
  } on NetworkException {
    rethrow;
  } catch (e) {
    debugPrint('Error getting mobile subscription status: $e');
    return null;
  }
}
