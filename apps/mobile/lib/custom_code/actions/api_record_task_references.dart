import 'package:flutter/foundation.dart';

import 'index.dart';

/// POST /api/v1/agent-instances/{id}/references: note on each task a sent
/// message `#`-referenced that this session named it (one `referenced` row
/// in the task's activity per session), so the session shows on that task's
/// Sessions list. It never files the session under the task or moves the
/// task's status; that is starting a session FROM the task. Fire-and-forget:
/// a task the server can't record is skipped, and a failure is only logged.
Future<void> apiRecordTaskReferences(String instanceId, List<String> taskIds) async {
  if (taskIds.isEmpty) return;
  try {
    await vicoaApiRequest('post', '/api/v1/agent-instances/$instanceId/references', {'task_ids': taskIds});
  } catch (e) {
    debugPrint('Error recording referenced tasks: $e');
  }
}
