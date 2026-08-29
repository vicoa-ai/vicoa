import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'task_chips.dart';
import 'task_glyphs.dart';
import 'task_l10n.dart';

/// Read-only detail sheet for a task: title, an optional parent breadcrumb,
/// description, the status/priority/project/label chips, and (for a parent) a
/// flush list of its sub-tasks. Actions (Start session / Edit / Delete) sit in
/// one row at the bottom. Returns the chosen action ('start' | 'edit' |
/// 'delete') or null if dismissed.
Future<String?> showTaskDetailSheet({
  required BuildContext context,
  required dynamic task,
  required dynamic project,
  dynamic parentTask,
  List<dynamic> subtasks = const [],
}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    enableDrag: true,
    builder: (ctx) => _TaskDetailSheet(
      task: task,
      project: project,
      parentTask: parentTask,
      subtasks: subtasks,
    ),
  );
}

class _TaskDetailSheet extends StatelessWidget {
  const _TaskDetailSheet({
    required this.task,
    required this.project,
    required this.parentTask,
    required this.subtasks,
  });

  final dynamic task;
  final dynamic project;
  final dynamic parentTask;
  final List<dynamic> subtasks;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final status = tutils.taskStatus(task);
    final priority = tutils.taskPriority(task);
    final closed = tutils.taskIsClosed(task);
    final description = tutils.taskDescription(task);
    final labels = tutils.taskLabels(task);
    final showProject = project != null && !tutils.projectIsInbox(project);

    final chips = <Widget>[
      TaskMetaChip(
        glyph: TaskStatusIcon(status: status),
        label: taskStatusLabel(l10n, status),
        color: tutils.taskStatusColor(status, theme),
      ),
      TaskMetaChip(
        glyph: TaskPriorityIcon(priority: priority),
        label: taskPriorityLabel(l10n, priority),
        color: tutils.taskPriorityColor(priority, theme),
      ),
      if (showProject)
        TaskProjectChip(project: project, name: tutils.projectName(project)),
      ...labels.map((l) => TaskLabelChip(label: l)),
    ];

    return Container(
      constraints:
          BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24.0)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          // Stretch children to full width so narrow content (e.g. a leaf
          // sub-task with no sub-task list) is left-aligned rather than
          // centered — the default CrossAxisAlignment.center was what left the
          // "empty space on the left".
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              heightFactor: 1.0,
              child: Container(
                margin: const EdgeInsets.only(top: 12.0, bottom: 8.0),
                width: 40.0,
                height: 4.0,
                decoration: BoxDecoration(
                  color: theme.alternate,
                  borderRadius: BorderRadius.circular(2.0),
                ),
              ),
            ),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16.0, 8.0, 16.0, 16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Parent breadcrumb — "↳ <parent title>", flush with the
                    // rest (no indent), the mobile analogue of the web's chip.
                    if (parentTask != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8.0),
                        child: _ParentChip(
                          title: tutils.taskTitle(parentTask),
                          onTap: () => Navigator.pop(
                              context, 'open:${tutils.taskId(parentTask)}'),
                        ),
                      ),
                    Text(
                      tutils.taskTitle(task),
                      style: theme.titleLarge.override(
                        font: GoogleFonts.sourceSans3(),
                        color: closed ? theme.secondaryText : theme.primaryText,
                        fontSize: 18.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w600,
                        decoration:
                            closed ? TextDecoration.lineThrough : null,
                      ),
                    ),
                    if (description != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 14.0),
                        child: Text(
                          description,
                          style: theme.bodyMedium.override(
                            font: GoogleFonts.sourceSans3(),
                            color: theme.primaryText,
                            letterSpacing: 0.0,
                            lineHeight: 1.4,
                          ),
                        ),
                      ),
                    // Chips go under the description.
                    Padding(
                      padding: const EdgeInsets.only(top: 14.0),
                      child: Wrap(
                        spacing: 14.0,
                        runSpacing: 8.0,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: chips,
                      ),
                    ),
                    if (subtasks.isNotEmpty)
                      _SubtaskList(subtasks: subtasks),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16.0, 22.0, 16.0, 12.0),
              child: Row(
                children: [
                  Expanded(
                    child: _ActionButton(
                      icon: Icons.play_arrow_rounded,
                      label: l10n.tasksStartSession,
                      onTap: () {
                        HapticFeedback.mediumImpact();
                        Navigator.pop(context, 'start');
                      },
                    ),
                  ),
                  const SizedBox(width: 12.0),
                  _ActionButton(
                    icon: Icons.edit_outlined,
                    onTap: () => Navigator.pop(context, 'edit'),
                  ),
                  const SizedBox(width: 10.0),
                  _ActionButton(
                    icon: Icons.delete_outline_rounded,
                    onTap: () => Navigator.pop(context, 'delete'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "↳ <parent title>" pill linking the task to its parent; tap to open it.
class _ParentChip extends StatelessWidget {
  const _ParentChip({required this.title, required this.onTap});

  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return InkWell(
      borderRadius: BorderRadius.circular(8.0),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10.0, vertical: 5.0),
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: BorderRadius.circular(8.0),
          border: Border.all(color: theme.alternate, width: 1.0),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.subdirectory_arrow_right_rounded,
                color: theme.secondaryText, size: 15.0),
            const SizedBox(width: 6.0),
            Flexible(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.labelMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.secondaryText,
                  fontSize: 12.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The task's sub-tasks. Each row keeps the title flush-left (aligned with the
/// rest of the sheet — no leading indent) with the status glyph trailing on the
/// right, mirroring a normal task; tap a row to open that sub-task.
class _SubtaskList extends StatelessWidget {
  const _SubtaskList({required this.subtasks});

  final List<dynamic> subtasks;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final total = subtasks.length;
    final done =
        subtasks.where((s) => tutils.taskStatus(s) == 'done').length;

    return Padding(
      padding: const EdgeInsets.only(top: 18.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${l10n.tasksSubtasks} · $done/$total',
            style: theme.labelMedium.override(
              font: GoogleFonts.sourceSans3(),
              color: theme.secondaryText,
              fontSize: 12.0,
              letterSpacing: 0.4,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4.0),
          for (final st in subtasks)
            InkWell(
              onTap: () =>
                  Navigator.pop(context, 'open:${tutils.taskId(st)}'),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8.0),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        tutils.taskTitle(st),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.bodyMedium.override(
                          font: GoogleFonts.sourceSans3(),
                          color: tutils.taskIsClosed(st)
                              ? theme.secondaryText
                              : theme.primaryText,
                          letterSpacing: 0.0,
                          decoration: tutils.taskIsClosed(st)
                              ? TextDecoration.lineThrough
                              : null,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10.0),
                    TaskStatusIcon(status: tutils.taskStatus(st), size: 15.0),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A flat, neutral outline action button. Same style whether it carries a
/// [label] (Start session) or is icon-only (Edit / Delete).
class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.onTap,
    this.label,
  });

  final IconData icon;
  final VoidCallback onTap;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final iconOnly = label == null;
    return InkWell(
      borderRadius: BorderRadius.circular(12.0),
      onTap: onTap,
      child: Container(
        padding: iconOnly
            ? const EdgeInsets.all(13.0)
            : const EdgeInsets.symmetric(vertical: 12.0, horizontal: 6.0),
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: BorderRadius.circular(12.0),
          border: Border.all(color: theme.alternate, width: 1.0),
        ),
        child: iconOnly
            ? Icon(icon, color: theme.secondaryText, size: 20.0)
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, color: theme.secondaryText, size: 19.0),
                  const SizedBox(width: 6.0),
                  Flexible(
                    child: Text(
                      label!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}
