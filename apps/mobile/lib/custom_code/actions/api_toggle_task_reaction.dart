import 'package:flutter/foundation.dart';

import 'index.dart';

/// PUT /api/v1/tasks/{id}/reactions: add or remove one emoji on the task
/// ([targetType] `task`, [targetId] the task's id) or on one of its comments
/// (`comment`). Idempotent per (user, target, emoji): sending the same one
/// twice lands back where it started. The server checks only that the value
/// is an emoji, not which one. Answers with the whole timeline, or null on
/// error.
Future<Map<String, dynamic>?> apiToggleTaskReaction(
  String taskId, {
  required String targetType,
  required String targetId,
  required String emoji,
}) async {
  try {
    final result = await vicoaApiRequest('put', '/api/v1/tasks/$taskId/reactions', {
      'target_type': targetType,
      'target_id': targetId,
      'emoji': emoji,
    });
    return result is Map ? Map<String, dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error toggling task reaction: $e');
    return null;
  }
}
