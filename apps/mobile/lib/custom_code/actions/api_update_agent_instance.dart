// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiUpdateAgentInstance(
  String instanceId,
  Map<String, dynamic> updates,
) async {
  try {
    final result = await vicoaApiRequest('patch', '/api/v1/agent-instances/$instanceId', updates);
    
    if (result is Map) {
      return result;
    }
    
    return null;
  } catch (e) {
    debugPrint('Error updating agent instance: $e');
    return null;
  }
}