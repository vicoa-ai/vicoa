import '/l10n/app_localizations.dart';

/// Localized display names for the task status and priority vocabularies.
/// Kept separate from `task_utils.dart` so that file stays free of l10n deps.

String taskStatusLabel(AppLocalizations l10n, String status) {
  switch (status) {
    case 'backlog':
      return l10n.tasksStatusBacklog;
    case 'todo':
      return l10n.tasksStatusTodo;
    case 'in_progress':
      return l10n.tasksStatusInProgress;
    case 'in_review':
      return l10n.tasksStatusInReview;
    case 'done':
      return l10n.tasksStatusDone;
    case 'blocked':
      return l10n.tasksStatusBlocked;
    case 'cancelled':
      return l10n.tasksStatusCancelled;
    default:
      return status;
  }
}

String taskPriorityLabel(AppLocalizations l10n, String priority) {
  switch (priority) {
    case 'urgent':
      return l10n.tasksPriorityUrgent;
    case 'high':
      return l10n.tasksPriorityHigh;
    case 'medium':
      return l10n.tasksPriorityMedium;
    case 'low':
      return l10n.tasksPriorityLow;
    default:
      return l10n.tasksPriorityNone;
  }
}
