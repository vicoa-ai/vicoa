// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Polls the spawn request status until the instance is ready.
/// Returns the instance data when ready, or a failure map with `error` details.
Future<dynamic> apiGetSpawnRequestStatus(
  String machineId,
  String requestId, {
  int maxAttempts = 10,
  int delayMilliseconds = 2000,
}) async {
  if (machineId.isEmpty || requestId.isEmpty) {
    const errorMessage =
        'Machine ID and request ID are required to poll spawn request status.';
    debugPrint(errorMessage);
    return {
      'success': false,
      'status': 'invalid_request',
      'error': errorMessage,
    };
  }

  for (int attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      debugPrint(
          'Polling spawn request status for machine $machineId (attempt ${attempt + 1}/$maxAttempts)...');

      final result = await vicoaApiRequest(
        'get',
        '/api/v1/machines/$machineId/spawn-requests/$requestId',
        null,
      );

      if (result is Map) {
        final status = result['status']?.toString().toLowerCase();
        debugPrint('Spawn request status: $status');

        // Check if the spawn request is completed
        if (status == 'started') {
          // Return the instance data if available
          final instanceId = result['agent_instance_id'];
          if (instanceId != null) {
            debugPrint('Spawn request completed, instance ID: $instanceId');
            // Fetch the full instance data
            final instanceData = await apiGetInstanceById(instanceId.toString());
            return instanceData;
          }
          // If no instance_id but status is completed, return the result
          return result;
        }

        // Check if the spawn request failed
        if (status == 'failed' || status == 'error') {
          final errorMessage = result['error']?.toString() ??
              result['message']?.toString() ??
              'Unknown error';
          debugPrint('Spawn request failed: $errorMessage');
          return {
            'success': false,
            'status': status,
            'error': errorMessage,
          };
        }

        // Still pending, wait before next attempt
        if (attempt < maxAttempts - 1) {
          await Future.delayed(Duration(milliseconds: delayMilliseconds));
        }
      } else {
        debugPrint('Unexpected response format from spawn request status endpoint');
        return {
          'success': false,
          'status': 'invalid_response',
          'error': 'Unexpected response from server while starting the session.',
        };
      }
    } catch (e) {
      debugPrint('Error polling spawn request status: $e');
      if (attempt == maxAttempts - 1) {
        return {
          'success': false,
          'status': 'polling_error',
          'error': e.toString(),
        };
      }
      if (attempt < maxAttempts - 1) {
        await Future.delayed(Duration(milliseconds: delayMilliseconds));
      }
    }
  }

  debugPrint('Spawn request polling timed out after $maxAttempts attempts');
  return {
    'success': false,
    'status': 'timeout',
    'error': 'Timed out while waiting for the remote machine to start the session.',
  };
}
