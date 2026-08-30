import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/custom_code/utils/file_mention_utils.dart';

class FileMentionSuggestions extends StatelessWidget {
  const FileMentionSuggestions({
    super.key,
    required this.mixin,
    this.margin = const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 12.0),
    this.onFileSelected,
  });

  final FileMentionMixin mixin;
  final EdgeInsetsGeometry margin;
  final void Function(String)? onFileSelected;

  @override
  Widget build(BuildContext context) {
    if (!mixin.showFileMentionSuggestions || mixin.filteredFileMentions.isEmpty) {
      return const SizedBox.shrink();
    }

    final itemCount = mixin.filteredFileMentions.length;
    if (itemCount == 0) return const SizedBox.shrink();

    final theme = FlutterFlowTheme.of(context);
    final textStyle = theme.bodyMedium.override(
          fontSize: 14.0,
          color: theme.primaryText,
          fontFamily: 'monospace',
        );
    // Captured here (the right place to depend on MediaQuery) and reused for
    // every row's width measurement below.
    final textScaler = MediaQuery.textScalerOf(context);
    // The panel's own horizontal margin — the long-press tooltip is pinned to
    // the same width and inset so it reads as this same panel surface.
    final resolvedMargin = margin.resolve(Directionality.of(context));

    return Container(
      constraints: const BoxConstraints(maxHeight: 210.0),
      margin: margin,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).secondaryBackground,
        borderRadius: BorderRadius.circular(16.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.15),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 8.0,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: ListView.builder(
        shrinkWrap: true,
        padding: EdgeInsets.zero,
        itemCount: itemCount,
        itemBuilder: (context, index) {
          if (index >= mixin.filteredFileMentions.length) {
            return const SizedBox.shrink();
          }
          final filePath = mixin.filteredFileMentions[index];
          final isFirst = index == 0;
          final isLast = index == itemCount - 1;
          final itemRadius = isFirst
              ? const BorderRadius.vertical(top: Radius.circular(16.0))
              : isLast
                  ? const BorderRadius.vertical(bottom: Radius.circular(16.0))
                  : BorderRadius.zero;

          const rowHPad = 18.0;
          // The ListView hands each row the panel's full content width, so this
          // LayoutBuilder's maxWidth IS the panel width — used both to size the
          // long-press tooltip to match and to fit the middle-ellipsis to the
          // text's available width.
          return LayoutBuilder(
            builder: (context, rowConstraints) {
              final panelWidth =
                  rowConstraints.maxWidth.isFinite ? rowConstraints.maxWidth : null;
              // Middle-ellipsize the path instead of tail-truncating it: tail
              // truncation hides the filename (the most identifying part),
              // whereas this keeps BOTH the head — the prefix the user types
              // against — and the tail filename, dropping only the least-useful
              // middle, and only when the path is actually wider than the row.
              // A path that fits is shown in full (see _fitMiddleEllipsis).
              final display = panelWidth == null
                  ? filePath
                  : _fitMiddleEllipsis(
                      filePath, panelWidth - rowHPad * 2, textStyle, textScaler);
              // Long-press reveals the full path. The tooltip mirrors this panel
              // — fixed to the same width and surface color — and wraps to as
              // many lines as it needs; its long-press trigger carries the usual
              // haptic. Tap still inserts the mention.
              return Tooltip(
                message: filePath,
                triggerMode: TooltipTriggerMode.longPress,
                preferBelow: false,
                constraints: panelWidth != null
                    ? BoxConstraints.tightFor(width: panelWidth)
                    : null,
                margin: EdgeInsets.symmetric(horizontal: resolvedMargin.left),
                padding:
                    const EdgeInsets.symmetric(horizontal: rowHPad, vertical: 12.0),
                textStyle: textStyle,
                decoration: BoxDecoration(
                  color: theme.primaryBackground,
                  borderRadius: BorderRadius.circular(16.0)
                ),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: itemRadius,
                    onTap: () {
                      HapticFeedback.lightImpact();
                      mixin.insertFileMention(filePath);
                      onFileSelected?.call(filePath);
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: rowHPad, vertical: 12.0),
                      decoration: BoxDecoration(
                        borderRadius: itemRadius,
                        color: Colors.transparent,
                      ),
                      child: Text(
                        display,
                        style: textStyle,
                        maxLines: 1,
                        softWrap: false,
                        overflow: TextOverflow.clip,
                      ),
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}

/// Middle-ellipsize [text] to the widest string that still fits within
/// [maxWidth] when painted in [style] at [textScaler] — keeping as much of the
/// path as possible, and the whole path (no `…`) when it already fits. Flutter
/// has no built-in middle ellipsis, so we binary-search the number of kept
/// characters (head + tail) and measure each candidate. Width is monotonic in
/// the kept count, so this finds the tightest truncation in O(log n) layouts,
/// and only for rows that actually overflow.
String _fitMiddleEllipsis(
    String text, double maxWidth, TextStyle style, TextScaler textScaler) {
  final painter = TextPainter(
    textDirection: TextDirection.ltr,
    textScaler: textScaler,
    maxLines: 1,
  );
  double widthOf(String s) {
    painter.text = TextSpan(text: s, style: style);
    painter.layout();
    return painter.width;
  }

  try {
    if (widthOf(text) <= maxWidth) return text; // fits whole — no ellipsis
    var lo = 0;
    var hi = text.length - 1; // at least one char must be dropped
    var best = '…';
    while (lo <= hi) {
      final keep = (lo + hi) ~/ 2;
      final candidate = _composeMiddle(text, keep);
      if (widthOf(candidate) <= maxWidth) {
        best = candidate;
        lo = keep + 1; // room for more — keep going
      } else {
        hi = keep - 1;
      }
    }
    return best;
  } finally {
    painter.dispose();
  }
}

/// Keep [keep] characters of [text] split across the head and tail with a `…`
/// between them, biasing the tail so the filename survives.
String _composeMiddle(String text, int keep) {
  if (keep >= text.length) return text;
  if (keep <= 0) return '…';
  final tail = (keep / 2).ceil(); // favour the filename end
  final head = keep - tail;
  final headPart = head <= 0 ? '' : text.substring(0, head);
  return '$headPart…${text.substring(text.length - tail)}';
}
