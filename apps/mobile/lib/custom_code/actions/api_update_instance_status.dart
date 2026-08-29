// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<bool> apiUpdateInstanceStatus(String instanceId, String status) async {
  try {
    final body = {
      'status': status,
    };
    
    await vicoaApiRequest('put', '/api/v1/agent-instances/$instanceId/status', body);
    return true;
  } catch (e) {
    debugPrint('Error updating instance status: $e');
    return false;
  }
}