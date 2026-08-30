// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiGetAgentById(String agentId) async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/user-agents/$agentId', null);
    return result;
  } catch (e) {
    debugPrint('Error getting agent by id: $e');
    return null;
  }
}