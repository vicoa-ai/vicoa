import 'package:flutter/foundation.dart';

import 'index.dart';

/// PATCH /api/v1/tasks/{id}/comments/{commentId}: rewrite a comment's body.
/// Author only (the server holds the line). Answers with the whole timeline,
/// or null on error.
Future<Map<String, dynamic>?> apiUpdateTaskComment(String taskId, String commentId, String body) async {
  try {
    final result = await vicoaApiRequest('patch', '/api/v1/tasks/$taskId/comments/$commentId', {'body': body});
    return result is Map ? Map<String, dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error updating task comment: $e');
    return null;
  }
}
