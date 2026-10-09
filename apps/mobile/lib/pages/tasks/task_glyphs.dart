import 'dart:math' as math;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '/backend/supabase/supabase.dart';
import '/custom_code/actions/vicoa_api_config.dart';
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

/// A project's icon, in the web `ProjectIcon`'s fallback order: the uploaded /
/// git-seeded image (`icon_image_uri`, fetched with the bearer like an
/// attachment) → the emoji `icon` → a muted lucide folder → a dashed square
/// when there is no project at all ("No project"; not a dashed circle, which
/// is the Backlog status).
class TaskProjectIcon extends StatelessWidget {
  const TaskProjectIcon({
    super.key,
    required this.project,
    this.size = 14.0,
    this.open = false,
  });

  final dynamic project;
  final double size;

  /// Draws the default folder open, for an expanded Home project group (the
  /// web's `ProjectIcon open`). No effect on an image or emoji.
  final bool open;

  /// The web's 3px radius at its 14px default, scaled with the icon.
  double get _radius => size * 3 / 14;

  @override
  Widget build(BuildContext context) {
    final fallback = _fallback(context);
    final imageUrl = _imageUrl();
    if (imageUrl == null) return fallback;
    final token = SupaFlow.client.auth.currentSession?.accessToken ?? '';
    return ClipRRect(
      borderRadius: BorderRadius.circular(_radius),
      child: CachedNetworkImage(
        imageUrl: imageUrl,
        httpHeaders: {'Authorization': 'Bearer $token'},
        width: size,
        height: size,
        fit: BoxFit.cover,
        // The folder stands in while the bytes load — and stays if they never
        // arrive — since a spinner this small would only flicker.
        placeholder: (context, _) => fallback,
        errorWidget: (context, _, __) => fallback,
      ),
    );
  }

  /// `GET /projects/{id}/icon`, cache-busted with `updated_at` the way the web
  /// does: the served URL is stable across replacements, so the version is
  /// what makes a new upload show up.
  String? _imageUrl() {
    if (tutils.projectIconImageUri(project) == null) return null;
    final id = tutils.projectId(project);
    if (id.isEmpty) return null;
    final version = tutils.projectUpdatedAt(project);
    final query =
        version == null ? '' : '?v=${Uri.encodeQueryComponent(version)}';
    return '${getVicoaApiBaseUrl()}/api/v1/projects/$id/icon$query';
  }

  Widget _fallback(BuildContext context) {
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
    if (project != null) {
      return CustomPaint(
        size: Size.square(size),
        painter: ProjectFolderPainter(open: open, color: theme.secondaryText),
      );
    }
    return CustomPaint(
      size: Size.square(size),
      painter: _DashedSquarePainter(color: theme.secondaryText),
    );
  }
}

/// lucide's `folder` / `folder-open` (the web `ProjectIcon`'s defaults) in
/// their 24×24 space, stroke 2, round caps and joins. Drawn rather than taken
/// from Material, whose open folder is indistinguishable from the closed one
/// at header sizes.
class ProjectFolderPainter extends CustomPainter {
  ProjectFolderPainter({required this.open, required this.color});

  final bool open;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 24;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2 * s
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = Path();
    void move(double x, double y) => path.moveTo(x * s, y * s);
    void line(double x, double y) => path.lineTo(x * s, y * s);
    // A radius-2 corner; `cw` is the SVG sweep flag.
    void arc(double x, double y, {required bool cw}) =>
        path.arcToPoint(Offset(x * s, y * s), radius: Radius.circular(2 * s), clockwise: cw);

    if (open) {
      // m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0
      // 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81
      // 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2
      move(6, 14);
      line(7.5, 11.1);
      arc(9.24, 10, cw: true);
      line(20, 10);
      arc(21.94, 12.5, cw: true);
      line(20.4, 18.5);
      arc(18.45, 20, cw: true);
      line(4, 20);
      arc(2, 18, cw: true);
      line(2, 5);
      arc(4, 3, cw: true);
      line(7.9, 3);
      arc(9.59, 3.9, cw: true);
      line(10.4, 5.1);
      arc(12.07, 6, cw: false);
      line(18, 6);
      arc(20, 8, cw: true);
      line(20, 10);
    } else {
      // M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2
      // 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z
      move(20, 20);
      arc(22, 18, cw: false);
      line(22, 8);
      arc(20, 6, cw: false);
      line(12.1, 6);
      arc(10.41, 5.1, cw: true);
      line(9.6, 3.9);
      arc(7.93, 3, cw: false);
      line(4, 3);
      arc(2, 5, cw: false);
      line(2, 18);
      arc(4, 20, cw: false);
      path.close();
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(ProjectFolderPainter old) =>
      old.open != open || old.color != color;
}

/// lucide's `square-dashed` (the web's "No project" glyph) in its 24×24 space:
/// four rounded corners plus two dashes per side, stroke 2, round caps.
class _DashedSquarePainter extends CustomPainter {
  _DashedSquarePainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / 24;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2 * s
      ..strokeCap = StrokeCap.round;
    Offset p(double x, double y) => Offset(x * s, y * s);
    // Corners: quarter arcs of radius 2 around (5,5), (19,5), (19,19), (5,19).
    for (final (cx, cy, start) in [
      (5.0, 5.0, math.pi),
      (19.0, 5.0, -math.pi / 2),
      (19.0, 19.0, 0.0),
      (5.0, 19.0, math.pi / 2),
    ]) {
      canvas.drawArc(Rect.fromCircle(center: p(cx, cy), radius: 2 * s), start,
          math.pi / 2, false, paint);
    }
    for (final at in [9.0, 14.0]) {
      canvas.drawLine(p(at, 3), p(at + 1, 3), paint);
      canvas.drawLine(p(at, 21), p(at + 1, 21), paint);
      canvas.drawLine(p(3, at), p(3, at + 1), paint);
      canvas.drawLine(p(21, at), p(21, at + 1), paint);
    }
  }

  @override
  bool shouldRepaint(_DashedSquarePainter old) => old.color != color;
}
