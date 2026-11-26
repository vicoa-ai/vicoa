import 'package:flutter/foundation.dart';

import 'index.dart';

/// POST /api/v1/tasks/{id}/comments: a new thread, or with [parentCommentId] a
/// reply in one (threads are one level deep; the server re-points a reply to
/// a reply at its root). Answers with the WHOLE timeline, so a reply comes
/// back already spliced under its root: replace local state with it rather
/// than merging the one comment in. Null on error.
Future<Map<String, dynamic>?> apiCreateTaskComment(
  String taskId,
  String body, {
  String? parentCommentId,
}) async {
  try {
    final result = await vicoaApiRequest('post', '/api/v1/tasks/$taskId/comments', {
      'body': body,
      if (parentCommentId != null) 'parent_comment_id': parentCommentId,
    });
    return result is Map ? Map<String, dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error creating task comment: $e');
    return null;
  }
}
