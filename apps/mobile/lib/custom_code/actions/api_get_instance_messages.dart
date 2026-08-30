// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:convert';

import 'vicoa_api_request.dart' show vicoaApiRequestComputed;

/// Top-level parser run via [compute] (through [vicoaApiRequestComputed]) so
/// the JSON decode + filter for a long chat history (`?limit=10000`) runs in
/// a background isolate. A chat with hundreds of messages × multi-KB bodies
/// can easily produce several MB of JSON; decoding that on the UI thread
/// blocks the chat scroll for 100–500 ms on every open.
List<dynamic> _decodeInstanceMessages(String body) {
  final decoded = json.decode(body);

  List<dynamic> messages = const [];
  if (decoded is List) {
    messages = decoded;
  } else if (decoded is Map && decoded['messages'] is List) {
    messages = decoded['messages'] as List;
  }

  // Filter out empty or invalid messages.
  final result = <dynamic>[];
  for (final message in messages) {
    if (message == null || message is! Map) continue;
    final content = message['content']?.toString().trim() ?? '';
    if (content.isEmpty) continue;
    result.add(message);
  }
  return result;
}

Future<List<dynamic>> apiGetInstanceMessages(String instanceId) async {
  try {
    return await vicoaApiRequestComputed<List<dynamic>>(
      'get',
      '/api/v1/agent-instances/$instanceId/messages?limit=10000',
      null,
      _decodeInstanceMessages,
    );
  } catch (e) {
    debugPrint('Error getting instance messages: $e');
    return const [];
  }
}
