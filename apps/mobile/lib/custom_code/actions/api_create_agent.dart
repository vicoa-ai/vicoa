// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiCreateAgent(
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
    
    final result = await vicoaApiRequest('post', '/api/v1/user-agents', body);
    return result;
  } catch (e) {
    debugPrint('Error creating agent: $e');
    return null;
  }
}