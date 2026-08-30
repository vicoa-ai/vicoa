// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiUpdateAgent(
  String agentId,
  String name,
  String? webhookUrl,
  String? webhookApiKey,
  bool? isActive,
) async {
  try {
    final body = {
      'name': name,
      if (webhookUrl != null) 'webhook_url': webhookUrl,
      if (webhookApiKey != null) 'webhook_api_key': webhookApiKey,
      'is_active': isActive ?? true,
    };
    
    final result = await vicoaApiRequest('patch', '/api/v1/user-agents/$agentId', body);
    return result;
  } catch (e) {
    debugPrint('Error updating agent: $e');
    return null;
  }
}