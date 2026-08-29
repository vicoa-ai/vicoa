// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// DELETE /machines/{id} — forget a machine. The endpoint returns 204 No
/// Content, which vicoaApiRequest surfaces as an "empty response" ApiException;
/// any 2xx status is treated as success.
Future<bool> apiRemoveMachine(String machineId) async {
  try {
    await vicoaApiRequest('delete', '/api/v1/machines/$machineId', null);
    return true;
  } on ApiException catch (e) {
    if (e.statusCode >= 200 && e.statusCode < 300) return true;
    debugPrint('Error removing machine: $e');
    return false;
  } catch (e) {
    debugPrint('Error removing machine: $e');
    return false;
  }
}
