// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// PATCH /machines/{id} — rename a machine. Returns the updated machine
/// summary map on success, or null on failure.
Future<dynamic> apiRenameMachine(
  String machineId,
  String displayName,
) async {
  try {
    final result = await vicoaApiRequest(
      'patch',
      '/api/v1/machines/$machineId',
      {'display_name': displayName},
    );
    return result is Map ? result : null;
  } catch (e) {
    debugPrint('Error renaming machine: $e');
    return null;
  }
}
