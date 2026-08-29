// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:convert';

import 'vicoa_api_request.dart' show vicoaApiRequestComputed;

/// Top-level parser used by [compute] (via [vicoaApiRequestComputed]) so the
/// JSON decode runs in a background isolate. Custom command lists can be
/// large (600+ entries for some agent types) — parsing on the UI thread
/// stutters the chat scroll on open.
List<dynamic> _decodeSlashCommands(String body) {
  final decoded = json.decode(body);
  if (decoded is Map && decoded['commands'] is List) {
    return decoded['commands'] as List;
  }
  return const [];
}

/// Fetches available slash commands for an agent type from the backend API.
///
/// [agentType] The agent type name (e.g., from agent_type_name in instance details)
///
/// Returns a list of slash command objects with the following structure:
/// ```dart
/// [
///   {
///     'name': '/clear',        // Command name (with slash prefix)
///     'description': 'Clear the chat history'  // Optional description
///   },
///   ...
/// ]
/// ```
///
/// Returns an empty list if the request fails or no commands are available.
Future<List<dynamic>> apiGetSlashCommands(String agentType) async {
  try {
    return await vicoaApiRequestComputed<List<dynamic>>(
      'get',
      '/api/v1/commands/$agentType',
      null,
      _decodeSlashCommands,
    );
  } catch (e) {
    debugPrint('Error fetching slash commands: $e');
    return const [];
  }
}
