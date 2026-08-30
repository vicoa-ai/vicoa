// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<List<dynamic>> apiGetAgents() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/user-agents', null);

    if (result is List) {
      return result;
    } else if (result is Map && result.containsKey('agents')) {
      return result['agents'] as List<dynamic>;
    }

    return [];
  } on AuthenticationException {
    rethrow; // Let caller handle auth errors
  } on NetworkException {
    rethrow; // Let caller handle network errors
  } catch (e) {
    debugPrint('Error getting agents: $e');
    return []; // Return empty for unexpected errors
  }
}