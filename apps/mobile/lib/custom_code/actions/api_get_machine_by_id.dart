// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// GET /machines/{id} — fetch a single machine summary (deep-link target from
/// the session info sheet). Returns the machine map, or null if not found /
/// on error. Auth and network errors are rethrown so the caller can react.
Future<dynamic> apiGetMachineById(String machineId) async {
  try {
    final result =
        await vicoaApiRequest('get', '/api/v1/machines/$machineId', null);
    return result is Map ? result : null;
  } on AuthenticationException {
    rethrow;
  } on NetworkException {
    rethrow;
  } catch (e) {
    debugPrint('Error fetching machine $machineId: $e');
    return null;
  }
}
