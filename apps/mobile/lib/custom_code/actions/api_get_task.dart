import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/tasks/{id}: one task as `TaskResponse`, or null on error.
/// [taskId] may be the UUID or the `VIC-42` identifier.
Future<Map<String, dynamic>?> apiGetTask(String taskId) async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/tasks/$taskId', null);
    return result is Map ? Map<String, dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error getting task: $e');
    return null;
  }
}
