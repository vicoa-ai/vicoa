import 'package:flutter/foundation.dart';

import 'index.dart';

/// DELETE /api/v1/tasks/{id}/comments/{commentId}: a soft delete. The row stays
/// (its `body` comes back null, `deleted_at` set) so its replies keep their
/// thread. Author only. Answers with the whole timeline, or null on error.
Future<Map<String, dynamic>?> apiDeleteTaskComment(String taskId, String commentId) async {
  try {
    final result = await vicoaApiRequest('delete', '/api/v1/tasks/$taskId/comments/$commentId', null);
    return result is Map ? Map<String, dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error deleting task comment: $e');
    return null;
  }
}
