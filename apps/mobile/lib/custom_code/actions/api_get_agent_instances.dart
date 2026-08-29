// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<List<dynamic>> apiGetAgentInstances(String agentId) async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/user-agents/$agentId/instances', null);
    
    if (result is List) {
      return result;
    }
    
    return [];
  } catch (e) {
    debugPrint('Error getting agent instances: $e');
    return [];
  }
}