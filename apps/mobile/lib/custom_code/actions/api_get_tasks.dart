import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/tasks — the user's human-authored task backlog. Optional
/// project/status filters mirror the web dashboard's query params. Returns a
/// bare list of task maps (or [] on error), matching the backend's
/// `list[TaskResponse]` shape.
Future<List<dynamic>> apiGetTasks({String? projectId, String? status}) async {
  try {
    final query = <String>[];
    if (projectId != null && projectId.isNotEmpty) {
      query.add('project_id=$projectId');
    }
    if (status != null && status.isNotEmpty) {
      query.add('status=$status');
    }
    final endpoint =
        query.isEmpty ? '/api/v1/tasks' : '/api/v1/tasks?${query.join('&')}';
    final result = await vicoaApiRequest('get', endpoint, null);
    if (result is List) return result;
    return [];
  } catch (e) {
    debugPrint('Error getting tasks: $e');
    return [];
  }
}
