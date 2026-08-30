// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiChatWithAgent(
  String instanceId,
  String message, {
  List<String> attachmentIds = const [],
}) async {
  try {
    final body = {
      'content': message,
      if (attachmentIds.isNotEmpty) 'attachment_ids': attachmentIds,
    };

    final result = await vicoaApiRequest('post', '/api/v1/agent-instances/$instanceId/messages', body);
    return result;
  } catch (e) {
    debugPrint('Error chatting with agent: $e');
    return null;
  }
}