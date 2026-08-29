// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Spawns a remote session with an optional initial prompt.
Future<Map<String, dynamic>> apiSpawnSessionWithPrompt(
  String machineId,
  String directory, {
  String agent = 'claude',
  String prompt = '',
}) async {
  try {
    final trimmedPrompt = prompt.trim();
    final body = <String, dynamic>{
      'directory': directory,
      'agent': agent,
      if (trimmedPrompt.isNotEmpty) 'prompt': trimmedPrompt,
    };

    final result = await vicoaApiRequest(
      'post',
      '/api/v1/machines/$machineId/spawn-requests',
      body,
    );

    if (result is Map && result['request_id'] is String) {
      return {
        'success': true,
        'requestId': result['request_id'],
        'machineId': machineId,
        'agentInstanceId': result['agent_instance_id'],
      };
    }

    return {
      'success': false,
      'error': 'Unexpected response from server',
    };
  } catch (e) {
    debugPrint('Error spawning remote session: $e');
    return {
      'success': false,
      'error': e.toString(),
    };
  }
}
