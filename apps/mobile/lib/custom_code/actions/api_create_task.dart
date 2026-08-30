import 'package:flutter/foundation.dart';

import 'index.dart';

/// POST /api/v1/tasks. Omitting [projectId] sends the task to the user's Inbox
/// ("No project") bucket, exactly like the web client. Returns the created task
/// map, or null on error.
Future<dynamic> apiCreateTask({
  required String title,
  String? description,
  String? projectId,
  String? status,
  String? priority,
  List<String>? labelIds,
}) async {
  try {
    final body = <String, dynamic>{
      'title': title,
      if (description != null) 'description': description,
      if (projectId != null) 'project_id': projectId,
      if (status != null) 'status': status,
      if (priority != null) 'priority': priority,
      if (labelIds != null) 'label_ids': labelIds,
    };
    final result = await vicoaApiRequest('post', '/api/v1/tasks', body);
    return result;
  } catch (e) {
    debugPrint('Error creating task: $e');
    return null;
  }
}
