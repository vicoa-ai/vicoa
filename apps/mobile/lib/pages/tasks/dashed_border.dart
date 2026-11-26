import 'package:flutter/material.dart';

/// A dashed rounded-rectangle outline along its box's edge: the web's
/// `border-dashed`, which Flutter's `Border` has no style for.
class DashedBorderPainter extends CustomPainter {
  const DashedBorderPainter({required this.color, required this.radius});

  final Color color;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;
    final outline = Path()..addRRect(RRect.fromRectAndRadius((Offset.zero & size).deflate(0.5), Radius.circular(radius)));
    for (final metric in outline.computeMetrics()) {
      for (var at = 0.0; at < metric.length; at += 7.0) {
        canvas.drawPath(metric.extractPath(at, at + 4.0), paint);
      }
    }
  }

  @override
  bool shouldRepaint(DashedBorderPainter old) => old.color != color || old.radius != radius;
}
