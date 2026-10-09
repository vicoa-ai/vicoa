import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import 'task_glyphs.dart';

/// Reusable chips shared by the task card, detail sheet and editor. The status
/// and priority *glyphs* themselves live in `task_glyphs.dart`.

/// A colored pill for a single task label ({name, #rrggbb color}).
class TaskLabelChip extends StatelessWidget {
  const TaskLabelChip({super.key, required this.label});

  final dynamic label;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final color = tutils.hexToColor(tutils.labelColorHex(label));
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 3.0),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6.0),
        border: Border.all(color: color.withValues(alpha: 0.35), width: 1.0),
      ),
      child: Text(
        tutils.labelName(label),
        style: theme.labelSmall.override(
          font: GoogleFonts.sourceSans3(),
          color: theme.primaryText,
          fontSize: 11.0,
          letterSpacing: 0.0,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}

/// A task's project — its icon (image / emoji / generated initial) plus its
/// name, shown plain (no border/background) inline with the other chips.
class TaskProjectChip extends StatelessWidget {
  const TaskProjectChip({super.key, required this.project, required this.name});

  final dynamic project;
  final String name;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        TaskProjectIcon(project: project, size: 13.0),
        const SizedBox(width: 5.0),
        Text(
          name,
          style: theme.labelSmall.override(
            font: GoogleFonts.sourceSans3(),
            color: theme.secondaryText,
            fontSize: 11.0,
            letterSpacing: 0.0,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

/// A glyph + label in an accent color — used for the status and priority chips
/// in the task detail sheet. Shown plain (no border/background); the color is
/// carried by the label text.
class TaskMetaChip extends StatelessWidget {
  const TaskMetaChip({
    super.key,
    required this.glyph,
    required this.label,
    required this.color,
  });

  final Widget glyph;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        glyph,
        const SizedBox(width: 5.0),
        Text(
          label,
          style: theme.labelMedium.override(
            font: GoogleFonts.sourceSans3(),
            color: color,
            fontSize: 12.0,
            letterSpacing: 0.0,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

/// "VIC-42", the task's identifier, wherever a task is listed. Mirrors the
/// web's `TaskIdentifier`: always shown (not behind the Display toggles), since
/// it is the task's name, the thing you type into chat or a commit message.
/// Renders nothing for a task without one (unfiled, or its project has no key
/// yet); a placeholder would read as a reference that doesn't resolve.
class TaskIdentifier extends StatelessWidget {
  const TaskIdentifier({super.key, required this.task, this.fontSize = 11.0});

  final dynamic task;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final identifier = tutils.taskIdentifier(task);
    if (identifier == null) return const SizedBox.shrink();
    final theme = FlutterFlowTheme.of(context);
    return Text(
      identifier,
      maxLines: 1,
      style: GoogleFonts.jetBrainsMono(
        color: theme.secondaryText.withValues(alpha: 0.8),
        fontSize: fontSize,
        fontWeight: FontWeight.w500,
        letterSpacing: 0.0,
      ),
    );
  }
}
