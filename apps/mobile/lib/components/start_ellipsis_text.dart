import 'package:flutter/material.dart';

/// Shows the END of [text], ellipsizing the START when it overflows the
/// available width (e.g. a long path → "…/projects/vicoa-ai"). The Flutter
/// analog of vicoa-web's `StartEllipsisText`: it measures with a [TextPainter]
/// and binary-searches the longest tail that fits behind a leading ellipsis.
///
/// Use inside a width-bounded parent (it relies on [LayoutBuilder] constraints);
/// when the text fits, it renders unchanged so [textAlign] still applies.
class StartEllipsisText extends StatelessWidget {
  const StartEllipsisText(
    this.text, {
    super.key,
    this.style,
    this.textAlign = TextAlign.start,
  });

  final String text;
  final TextStyle? style;
  final TextAlign textAlign;

  static const String _ellipsis = '…';

  @override
  Widget build(BuildContext context) {
    final effectiveStyle = DefaultTextStyle.of(context).style.merge(style);
    final textScaler = MediaQuery.textScalerOf(context);
    final textDirection = Directionality.of(context);

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = constraints.maxWidth;
        var display = text;

        if (maxWidth.isFinite && maxWidth > 0) {
          double widthOf(String value) {
            final painter = TextPainter(
              text: TextSpan(text: value, style: effectiveStyle),
              textDirection: textDirection,
              textScaler: textScaler,
              maxLines: 1,
            )..layout();
            return painter.width;
          }

          if (widthOf(text) > maxWidth) {
            // Binary-search the longest tail that fits behind the ellipsis.
            var low = 0;
            var high = text.length;
            var best = '';
            while (low <= high) {
              final mid = (low + high) >> 1;
              final candidate = '$_ellipsis${text.substring(text.length - mid)}';
              if (widthOf(candidate) <= maxWidth) {
                best = candidate;
                low = mid + 1;
              } else {
                high = mid - 1;
              }
            }
            display = best.isEmpty ? _ellipsis : best;
          }
        }

        return Text(
          display,
          maxLines: 1,
          softWrap: false,
          overflow: TextOverflow.clip,
          textAlign: textAlign,
          style: style,
        );
      },
    );
  }
}
