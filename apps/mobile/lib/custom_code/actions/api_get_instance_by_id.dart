// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiGetInstanceById(String instanceId) async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/agent-instances/$instanceId', null);
    
    if (result is Map) {
      return result;
    }
    
    return null;
  } catch (e) {
    debugPrint('Error getting instance by ID: $e');
    return null;
  }
}