final RegExp _taskNotificationPattern = RegExp(
  r'<task-notification>([\s\S]*?)</task-notification>',
  caseSensitive: false,
);
final RegExp _taskNotificationStatus = RegExp(
  r'<status>([\s\S]*?)</status>',
  caseSensitive: false,
);
final RegExp _taskNotificationSummary = RegExp(
  r'<summary>([\s\S]*?)</summary>',
  caseSensitive: false,
);

// Collapse <task-notification> harness blocks to a two-line summary —
// `Task <status>  \n<summary>` — ignoring task-id / output-file / result /
// usage. The trailing two-space + newline forces a markdown hard break so
// the lines render adjacent rather than as separate paragraphs.
String formatTaskNotifications(String content) {
  if (!content.contains('<task-notification>')) return content;
  return content.replaceAllMapped(_taskNotificationPattern, (match) {
    final body = match.group(1) ?? '';
    final status = _taskNotificationStatus.firstMatch(body)?.group(1)?.trim() ?? '';
    final summary = _taskNotificationSummary.firstMatch(body)?.group(1)?.trim() ?? '';
    return 'Task $status  \n$summary';
  });
}
