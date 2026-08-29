import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/projects — the user's projects, including the non-deletable
/// Inbox ("No project") bucket. Used read-only on mobile to resolve a task's
/// project chip and to populate the project picker. Returns [] on error.
Future<List<dynamic>> apiGetProjects() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/projects', null);
    if (result is List) return result;
    return [];
  } catch (e) {
    debugPrint('Error getting projects: $e');
    return [];
  }
}
