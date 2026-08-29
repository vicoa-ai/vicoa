// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<bool> apiUpdateInstanceName(
  String instanceId,
  String name,
) async {
  try {
    final body = {
      'name': name,
    };
    
    final result = await vicoaApiRequest('patch', '/api/v1/agent-instances/$instanceId', body);
    return result != null;
  } catch (e) {
    debugPrint('Error updating instance name: $e');
    return false;
  }
}