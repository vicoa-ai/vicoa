import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/keyboard_utils.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';

/// A rounded outline pill showing a property's current value (glyph + text),
/// tapped to open an anchored dropdown — the mobile analogue of the web's
/// `PillButton` / `PickerPopover` pattern in the task dialog.
class PillButton extends StatelessWidget {
  const PillButton({
    super.key,
    required this.leading,
    required this.label,
    required this.onTap,
    this.labelColor,
  });

  final Widget leading;
  final String label;
  final VoidCallback onTap;
  final Color? labelColor;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return InkWell(
      borderRadius: BorderRadius.circular(20.0),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10.0, vertical: 6.0),
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: BorderRadius.circular(20.0),
          border: Border.all(color: theme.alternate, width: 1.0),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            leading,
            const SizedBox(width: 6.0),
            Text(
              label,
              style: theme.bodyMedium.override(
                font: GoogleFonts.sourceSans3(),
                color: labelColor ?? theme.primaryText,
                fontSize: 13.0,
                letterSpacing: 0.0,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class PickerOption<T> {
  const PickerOption({
    required this.value,
    required this.leading,
    required this.label,
  });

  final T value;
  final Widget leading;
  final String label;
}

/// A dropdown list anchored under (or above, if low on screen) the widget that
/// holds [anchorKey]. Dismisses on an outside tap. Shared by the single- and
/// multi-select pickers below.
Future<R?> _showAnchoredDropdown<R>({
  required BuildContext context,
  required GlobalKey anchorKey,
  required Widget Function(BuildContext dialogCtx, StateSetter setDrop)
      contentBuilder,
  bool alignRight = false,
  double width = 224.0,
}) async {
  // Dismiss the keyboard and wait for the sheet to settle before measuring the
  // anchor: otherwise the panel is positioned against the keyboard-lifted
  // layout and floats away once the sheet drops. Also stops the keyboard from
  // popping back up after the panel is dismissed.
  await dismissKeyboardAndSettle(context);
  if (!context.mounted) return null;
  final box = anchorKey.currentContext?.findRenderObject() as RenderBox?;
  if (box == null) return null;
  final offset = box.localToGlobal(Offset.zero);
  final size = box.size;
  final screen = MediaQuery.of(context).size;
  final dropWidth = width;
  // alignRight pins the panel's right edge to the anchor's right edge (for
  // value-on-the-right rows); default pins left edge to anchor's left.
  final rawLeft =
      alignRight ? offset.dx + size.width - dropWidth : offset.dx;
  final left = rawLeft.clamp(8.0, screen.width - dropWidth - 8.0);
  final placeAbove = (screen.height - (offset.dy + size.height)) < 240.0;

  return showGeneralDialog<R>(
    context: context,
    barrierDismissible: true,
    barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
    barrierColor: Colors.transparent,
    transitionDuration: const Duration(milliseconds: 140),
    pageBuilder: (dialogCtx, _, __) {
      final theme = FlutterFlowTheme.of(dialogCtx);
      return StatefulBuilder(
        builder: (dialogCtx, setDrop) {
          final panel = Material(
            color: Colors.transparent,
            child: Container(
              constraints: const BoxConstraints(maxHeight: 320.0),
              decoration: BoxDecoration(
                color: theme.primaryBackground,
                borderRadius: BorderRadius.circular(14.0),
                border: Border.all(
                  color: theme.secondaryText.withValues(alpha: 0.25),
                  width: 0.75,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.16),
                    blurRadius: 24.0,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(14.0),
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(vertical: 4.0),
                  child: contentBuilder(dialogCtx, setDrop),
                ),
              ),
            ),
          );
          return Stack(
            children: [
              if (placeAbove)
                Positioned(
                  left: left,
                  bottom: screen.height - offset.dy + 4.0,
                  width: dropWidth,
                  child: panel,
                )
              else
                Positioned(
                  left: left,
                  top: offset.dy + size.height + 4.0,
                  width: dropWidth,
                  child: panel,
                ),
            ],
          );
        },
      );
    },
    transitionBuilder: (ctx, animation, _, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: Curves.easeOutCubic,
        reverseCurve: Curves.easeInCubic,
      );
      return FadeTransition(
        opacity: curved,
        child: ScaleTransition(
          scale: Tween<double>(begin: 0.9, end: 1.0).animate(curved),
          alignment: placeAbove
              ? (alignRight ? Alignment.bottomRight : Alignment.bottomLeft)
              : (alignRight ? Alignment.topRight : Alignment.topLeft),
          child: child,
        ),
      );
    },
  );
}

Widget _row({
  required Widget leading,
  required String label,
  required bool selected,
  required VoidCallback onTap,
}) {
  return Builder(
    builder: (context) {
      final theme = FlutterFlowTheme.of(context);
      return InkWell(
        onTap: onTap,
        child: Padding(
          padding:
              const EdgeInsets.symmetric(horizontal: 14.0, vertical: 10.0),
          child: Row(
            children: [
              leading,
              const SizedBox(width: 10.0),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.primaryText,
                    letterSpacing: 0.0,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
              if (selected)
                Icon(Icons.check_rounded,
                    color: theme.primaryText, size: 18.0),
            ],
          ),
        ),
      );
    },
  );
}

/// Single-select dropdown anchored to [anchorKey]. Returns the chosen value or
/// null if dismissed.
Future<T?> showAnchoredSingleSelect<T>({
  required BuildContext context,
  required GlobalKey anchorKey,
  required List<PickerOption<T>> options,
  T? selected,
  bool alignRight = false,
  double width = 224.0,
}) {
  return _showAnchoredDropdown<T>(
    context: context,
    anchorKey: anchorKey,
    alignRight: alignRight,
    width: width,
    contentBuilder: (dialogCtx, setDrop) => Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final o in options)
          _row(
            leading: o.leading,
            label: o.label,
            selected: o.value == selected,
            onTap: () => Navigator.pop(dialogCtx, o.value),
          ),
      ],
    ),
  );
}

/// Multi-select dropdown anchored to [anchorKey]. Toggles apply live via
/// [onToggle] (the caller mutates its own selection set); the dropdown reads
/// [selected] to render check marks and stays open until dismissed.
Future<void> showAnchoredMultiSelect({
  required BuildContext context,
  required GlobalKey anchorKey,
  required List<dynamic> labels,
  required Set<String> selected,
  required void Function(String id) onToggle,
}) {
  return _showAnchoredDropdown<void>(
    context: context,
    anchorKey: anchorKey,
    contentBuilder: (dialogCtx, setDrop) => Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final l in labels)
          _row(
            leading: Container(
              width: 10.0,
              height: 10.0,
              decoration: BoxDecoration(
                color: tutils.hexToColor(tutils.labelColorHex(l)),
                shape: BoxShape.circle,
              ),
            ),
            label: tutils.labelName(l),
            selected: selected.contains(tutils.labelId(l)),
            onTap: () {
              onToggle(tutils.labelId(l));
              setDrop(() {});
            },
          ),
      ],
    ),
  );
}
