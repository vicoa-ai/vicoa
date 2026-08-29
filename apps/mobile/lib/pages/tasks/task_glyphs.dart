import 'dart:math' as math;

import 'package:flutter/material.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';

/// Faithful Flutter ports of the web dashboard's task glyphs
/// (`vicoa-web/components/dashboard/task-ui.tsx`). Status is a ring + pie /
/// dotted-ring / check / slash / X in a 14×14 space; priority is a 4-bar
/// ascending chart in a 16×16 space. Both are `currentColor`-driven, so each
/// gets a single accent color.

class TaskStatusIcon extends StatelessWidget {
  const TaskStatusIcon({super.key, required this.status, this.size = 14.0});

  final String status;
  final double size;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _StatusPainter(status, tutils.taskStatusColor(status, theme)),
      ),
    );
  }
}

class _StatusPainter extends CustomPainter {
  _StatusPainter(this.status, this.color);

  final String status;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 14.0; // web viewBox is 0 0 14 14
    final cx = 7.0 * s, cy = 7.0 * s;
    final outerR = 6.0 * s, fillR = 3.5 * s;
    final strokeW = 1.5 * s;

    final fill = Paint()
      ..color = color
      ..style = PaintingStyle.fill
      ..isAntiAlias = true;
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeW
      ..strokeCap = StrokeCap.round
      ..isAntiAlias = true;

    void ring() =>
        canvas.drawCircle(Offset(cx, cy), outerR, stroke);

    void pie(double progress) {
      final angle = 2 * math.pi * progress;
      final path = Path()
        ..moveTo(cx, cy)
        ..lineTo(cx, cy - fillR)
        ..arcToPoint(
          Offset(cx + fillR * math.sin(angle), cy - fillR * math.cos(angle)),
          radius: Radius.circular(fillR),
          clockwise: true,
          largeArc: progress > 0.5,
        )
        ..close();
      canvas.drawPath(path, fill);
    }

    switch (status) {
      case 'backlog':
        // 16 small dots evenly placed on the ring.
        for (var i = 0; i < 16; i++) {
          final a = (i / 16) * math.pi * 2 - math.pi / 2;
          canvas.drawCircle(
            Offset(cx + outerR * math.cos(a), cy + outerR * math.sin(a)),
            0.55 * s,
            fill,
          );
        }
        break;
      case 'in_progress':
        ring();
        pie(0.5);
        break;
      case 'in_review':
        ring();
        pie(0.75);
        break;
      case 'done':
        canvas.drawCircle(Offset(cx, cy), outerR, fill);
        final check = Path()
          ..moveTo(3.95 * s, 7.25 * s)
          ..lineTo(5.35 * s, 8.65 * s)
          ..lineTo(9.75 * s, 4.25 * s);
        canvas.drawPath(
          check,
          Paint()
            ..color = Colors.white
            ..style = PaintingStyle.stroke
            ..strokeWidth = strokeW
            ..strokeCap = StrokeCap.round
            ..strokeJoin = StrokeJoin.round
            ..isAntiAlias = true,
        );
        break;
      case 'blocked':
        ring();
        // Diagonal "\" from 135° to -45° at radius 3.5.
        canvas.drawLine(
          Offset(cx + fillR * math.cos(math.pi * 0.75),
              cy - fillR * math.sin(math.pi * 0.75)),
          Offset(cx + fillR * math.cos(-math.pi * 0.25),
              cy - fillR * math.sin(-math.pi * 0.25)),
          stroke,
        );
        break;
      case 'cancelled':
        ring();
        canvas.drawLine(Offset(5 * s, 5 * s), Offset(9 * s, 9 * s), stroke);
        canvas.drawLine(Offset(9 * s, 5 * s), Offset(5 * s, 9 * s), stroke);
        break;
      case 'todo':
      default:
        ring();
        break;
    }
  }

  @override
  bool shouldRepaint(_StatusPainter old) =>
      old.status != status || old.color != color;
}

class TaskPriorityIcon extends StatelessWidget {
  const TaskPriorityIcon({super.key, required this.priority, this.size = 14.0});

  final String priority;
  final double size;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _PriorityPainter(
          tutils.taskPriorityBars(priority),
          tutils.taskPriorityColor(priority, theme),
          theme.secondaryText,
        ),
      ),
    );
  }
}

class _PriorityPainter extends CustomPainter {
  _PriorityPainter(this.bars, this.color, this.mutedColor);

  final int bars;
  final Color color;
  final Color mutedColor;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 16.0; // web viewBox is 0 0 16 16

    // "No priority" is a single horizontal dash.
    if (bars == 0) {
      canvas.drawLine(
        Offset(3 * s, 8 * s),
        Offset(13 * s, 8 * s),
        Paint()
          ..color = mutedColor
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5 * s
          ..strokeCap = StrokeCap.round
          ..isAntiAlias = true,
      );
      return;
    }

    for (var i = 0; i < 4; i++) {
      final on = i < bars;
      final paint = Paint()
        ..color = color.withValues(alpha: on ? 1.0 : 0.2)
        ..style = PaintingStyle.fill
        ..isAntiAlias = true;
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(
          (1 + i * 4) * s,
          (12 - (i + 1) * 3) * s,
          3 * s,
          (i + 1) * 3 * s,
        ),
        Radius.circular(0.5 * s),
      );
      canvas.drawRRect(rect, paint);
    }
  }

  @override
  bool shouldRepaint(_PriorityPainter old) =>
      old.bars != bars || old.color != color;
}

/// A project's emoji `icon`, or a muted inbox/folder line icon when it has none
/// (mirrors the web `ProjectIcon`).
class TaskProjectIcon extends StatelessWidget {
  const TaskProjectIcon({super.key, required this.project, this.size = 14.0});

  final dynamic project;
  final double size;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final emoji = tutils.projectIcon(project);
    if (emoji != null) {
      return SizedBox(
        width: size,
        height: size,
        child: Center(
          child: Text(emoji,
              style: TextStyle(fontSize: size * 0.85, height: 1.0)),
        ),
      );
    }
    final isInbox = tutils.projectIsInbox(project);
    return Icon(
      isInbox ? Icons.inbox_rounded : Icons.folder_outlined,
      size: size,
      color: theme.secondaryText,
    );
  }
}
