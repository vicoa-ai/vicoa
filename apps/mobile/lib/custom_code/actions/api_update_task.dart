import 'package:flutter/foundation.dart';

import 'index.dart';

/// PATCH /api/v1/tasks/{id}. [updates] is applied as-is — only the keys present
/// are changed (the backend uses `exclude_unset`). Returns the updated task map,
/// or null on error.
Future<dynamic> apiUpdateTask(
    String taskId, Map<String, dynamic> updates) async {
  try {
    final result =
        await vicoaApiRequest('patch', '/api/v1/tasks/$taskId', updates);
    if (result is Map) return result;
    return null;
  } catch (e) {
    debugPrint('Error updating task: $e');
    return null;
  }
}
