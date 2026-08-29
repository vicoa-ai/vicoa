import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import 'task_chips.dart';
import 'task_glyphs.dart';

/// One row in the tasks list: the title on top, then a second row carrying the
/// priority glyph, an optional status glyph, the project chip and label chips.
/// Which of priority/status/project appear is controlled by the Display toggles
/// in the header filter. Tapping opens the task detail sheet.
class TaskCard extends StatelessWidget {
  const TaskCard({
    super.key,
    required this.task,
    required this.project,
    required this.onTap,
    required this.showStatus,
    required this.showPriority,
    required this.showProject,
    required this.showLabels,
  });

  final dynamic task;

  /// The resolved project for [task] (or null / inbox → no project chip).
  final dynamic project;
  final VoidCallback onTap;
  final bool showStatus;
  final bool showPriority;
  final bool showProject;
  final bool showLabels;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final closed = tutils.taskIsClosed(task);
    final labels = tutils.taskLabels(task);
    final status = tutils.taskStatus(task);
    final showProjectChip =
        showProject && project != null && !tutils.projectIsInbox(project);

    final metaRow = <Widget>[
      if (showPriority) TaskPriorityIcon(priority: tutils.taskPriority(task)),
      if (showStatus) TaskStatusIcon(status: status),
      if (showProjectChip)
        TaskProjectChip(project: project, name: tutils.projectName(project)),
      if (showLabels) ...labels.map((l) => TaskLabelChip(label: l)),
    ];

    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 7.0, 16.0, 7.0),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(14.0),
          onTap: onTap,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 10.0),
            decoration: BoxDecoration(
              color: theme.primaryBackground,
              borderRadius: BorderRadius.circular(14.0),
              border: Border.all(color: theme.alternate, width: 1.0),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  tutils.taskTitle(task),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyLarge.override(
                    font: GoogleFonts.sourceSans3(),
                    color: closed ? theme.secondaryText : theme.primaryText,
                    fontSize: 16.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w500,
                    decoration: closed ? TextDecoration.lineThrough : null,
                  ),
                ),
                if (metaRow.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8.0),
                    child: Wrap(
                      spacing: 8.0,
                      runSpacing: 8.0,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: metaRow,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
