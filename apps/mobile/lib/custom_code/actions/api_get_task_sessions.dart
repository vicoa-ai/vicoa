import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/tasks/{id}/sessions?related=true: every session the task's
/// record names (filed under it, created it, changed it, commented on it,
/// referenced it), most recently active first. Each row is an agent instance
/// plus `task_relations`, strongest first; the ones with `linked` are the
/// sessions filed under the task. Null on error so a poll keeps the last list.
Future<List<dynamic>?> apiGetTaskSessions(String taskId) async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/tasks/$taskId/sessions?related=true', null);
    return result is List ? List<dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error getting task sessions: $e');
    return null;
  }
}
