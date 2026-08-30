import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/task-labels — the user's labels ({id, name, #rrggbb color}).
/// Used read-only on mobile to populate the label picker in the task editor
/// (a task already carries its own embedded label objects for display).
/// Returns [] on error.
Future<List<dynamic>> apiGetTaskLabels() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/task-labels', null);
    if (result is List) return result;
    return [];
  } catch (e) {
    debugPrint('Error getting task labels: $e');
    return [];
  }
}
