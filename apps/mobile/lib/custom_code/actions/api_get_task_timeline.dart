import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/tasks/{id}/timeline: the task's comments (in thread order),
/// activity, task-level reactions, the sessions those rows name and the people
/// who can see the task, in one payload (`TaskTimelineResponse`). The same
/// object the web renders. Returns the map, or null on error so a poll keeps
/// what is on screen.
Future<Map<String, dynamic>?> apiGetTaskTimeline(String taskId) async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/tasks/$taskId/timeline', null);
    return result is Map ? Map<String, dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error getting task timeline: $e');
    return null;
  }
}
