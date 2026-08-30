import 'package:flutter/foundation.dart';

import 'index.dart';

/// DELETE /api/v1/tasks/{id}. The endpoint returns 204 No Content; the shared
/// request helper flags an empty body as an error, so a *successful* delete
/// still lands in the catch below — we detect that specific case and report
/// success. Callers should still reconcile with a reload.
Future<bool> apiDeleteTask(String taskId) async {
  try {
    await vicoaApiRequest('delete', '/api/v1/tasks/$taskId', null);
    return true;
  } catch (e) {
    // 204 No Content: the delete succeeded even though the helper threw on the
    // empty response body.
    if (e.toString().contains('Empty response')) return true;
    debugPrint('Error deleting task: $e');
    return false;
  }
}
