// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<List<dynamic>> apiGetMachines() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/machines', null);

    if (result is Map && result['machines'] is List) {
      return List<dynamic>.from(result['machines']);
    }

    return [];
  } on AuthenticationException {
    rethrow; // Let caller handle auth errors
  } on NetworkException {
    rethrow; // Let caller handle network errors
  } catch (e) {
    debugPrint('Error fetching machines: $e');
    return []; // Return empty for unexpected errors
  }
}
