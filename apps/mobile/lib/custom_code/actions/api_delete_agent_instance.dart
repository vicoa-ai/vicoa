// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<bool> apiDeleteAgentInstance(String instanceId) async {
  try {
    await vicoaApiRequest('delete', '/api/v1/agent-instances/$instanceId', null);
    return true;
  } catch (e) {
    debugPrint('Error deleting agent instance: $e');
    return false;
  }
}