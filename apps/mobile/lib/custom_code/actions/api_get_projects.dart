import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/projects — the user's projects. "No project" is not a row but a
/// null `project_id` on the task. Used read-only on mobile to resolve a task's
/// project chip and to populate the project picker. [includeArchived] adds the
/// archived rows (Home needs them to hide those projects' sessions, like the
/// web sidebar). Returns [] on error.
Future<List<dynamic>> apiGetProjects({bool includeArchived = false}) async {
  try {
    final path = includeArchived
        ? '/api/v1/projects?include_archived=true'
        : '/api/v1/projects';
    final result = await vicoaApiRequest('get', path, null);
    if (result is List) return result;
    return [];
  } catch (e) {
    debugPrint('Error getting projects: $e');
    return [];
  }
}
