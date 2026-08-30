// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<bool> apiDeleteAgent(String agentId) async {
  try {
    await vicoaApiRequest('delete', '/api/v1/user-agents/$agentId', null);
    return true;
  } catch (e) {
    debugPrint('Error deleting agent: $e');
    return false;
  }
}