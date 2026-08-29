// Anchored dropdown menu for the Files-tab surfaces (FilesScreen and
// FileViewer). The panel hovers below-and-right-aligned to a button.
// Style mirrors `chat_options_menu.dart` so the menus read consistently.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_theme.dart';

class FileDropdownMenuItem {
  const FileDropdownMenuItem({
    required this.icon,
    required this.label,
    required this.onTap,
    this.isDestructive = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool isDestructive;
}

/// Show a dropdown menu anchored to the widget identified by [anchorKey].
///
/// Positions the panel below the button's bottom edge and right-aligned to
/// its right (with screen-edge clamping). Placement mirrors the logic in
/// `agent_chat_widget._showChatOptionsMenu` so the menu reads identically.
Future<void> showFileDropdownMenu({
  required BuildContext context,
  required GlobalKey anchorKey,
  required List<FileDropdownMenuItem> items,
  double menuWidth = 170,
}) async {
  final RenderBox? buttonBox =
      anchorKey.currentContext?.findRenderObject() as RenderBox?;
  final OverlayState? overlayState = Overlay.of(context);
  if (buttonBox == null || overlayState == null) return;

  final RenderBox overlayBox = overlayState.context.findRenderObject() as RenderBox;
  final Offset buttonTopRight = buttonBox.localToGlobal(
    buttonBox.size.topRight(Offset.zero),
    ancestor: overlayBox,
  );
  final Offset buttonBottomRight = buttonBox.localToGlobal(
    buttonBox.size.bottomRight(Offset.zero),
    ancestor: overlayBox,
  );

  const double verticalGap = 8.0;
  const double screenPadding = 16.0;

  final double overlayWidth = overlayBox.size.width;
  // Right-anchor by default: panel's right edge aligns with the button's right.
  double left = buttonTopRight.dx - menuWidth;
  final double top = buttonBottomRight.dy + verticalGap;
  if (left + menuWidth > overlayWidth - screenPadding) {
    left = overlayWidth - menuWidth - screenPadding;
  }
  if (left < screenPadding) left = screenPadding;

  await showGeneralDialog<void>(
    context: context,
    barrierDismissible: true,
    barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
    barrierColor: Colors.transparent,
    transitionDuration: const Duration(milliseconds: 180),
    pageBuilder: (dialogContext, _, __) {
      return Stack(
        children: [
          Positioned(
            left: left,
            top: top,
            width: menuWidth,
            child: Material(
              color: Colors.transparent,
              child: _FileDropdownMenuPanel(items: items, dialogContext: dialogContext),
            ),
          ),
        ],
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
          scale: Tween<double>(begin: 0.88, end: 1.0).animate(curved),
          alignment: Alignment.topRight,
          child: child,
        ),
      );
    },
  );
}

class _FileDropdownMenuPanel extends StatelessWidget {
  const _FileDropdownMenuPanel({required this.items, required this.dialogContext});
  final List<FileDropdownMenuItem> items;
  final BuildContext dialogContext;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(12.0),
        border: Border.all(color: theme.secondaryText.withValues(alpha: 0.25), width: 0.75),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 10.0, offset: const Offset(0, 4)),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (int i = 0; i < items.length; i++)
            _Item(item: items[i], isLast: i == items.length - 1, dialogContext: dialogContext),
        ],
      ),
    );
  }
}

class _Item extends StatelessWidget {
  const _Item({required this.item, required this.isLast, required this.dialogContext});
  final FileDropdownMenuItem item;
  final bool isLast;
  final BuildContext dialogContext;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final color = item.isDestructive ? theme.error : theme.primaryText;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          // Close the menu first so item handlers can pop/push the underlying
          // route without fighting the dialog.
          Navigator.of(dialogContext).pop();
          item.onTap();
        },
        child: Container(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 8.0, 16.0, 8.0),
          decoration: BoxDecoration(
            border: isLast
                ? null
                : Border(bottom: BorderSide(color: theme.secondaryText.withValues(alpha: 0.1), width: 0.5)),
          ),
          child: Row(
            children: [
              Icon(item.icon, size: 18, color: color),
              const SizedBox(width: 18),
              Expanded(
                child: Text(
                  item.label,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 16,
                    color: color,
                    letterSpacing: 0.0,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
