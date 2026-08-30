import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

class ChatOptionsMenu extends StatelessWidget {
  const ChatOptionsMenu({
    super.key,
    required this.onInfo,
    required this.onShare,
    required this.onRename,
    required this.onClose,
    required this.onDelete,
    this.onPin,
    this.isPinned = false,
    this.showCloseOption = true,
    this.showShareOption = true,
    this.onResume,
    this.showResumeOption = false,
    this.resumeDisabledReason,
  });

  final VoidCallback onInfo;
  final VoidCallback onShare;
  final VoidCallback onRename;
  final VoidCallback onClose;
  final VoidCallback onDelete;
  final VoidCallback? onPin;
  final bool isPinned;
  final bool showCloseOption;
  final bool showShareOption;
  final VoidCallback? onResume;
  final bool showResumeOption;
  /// Set when Resume is visible but not possible right now (e.g. the computer
  /// is offline). The item stays but is dimmed and reports the reason — hiding
  /// it would read as "unsupported" rather than "not right now".
  final String? resumeDisabledReason;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Container(
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(12.0),
        border: Border.all(
                color: FlutterFlowTheme.of(context)
                    .secondaryText
                    .withValues(alpha: 0.25),
                width: 0.75,
              ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.15),
            blurRadius: 10.0,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Menu items
          _buildMenuItem(
            context,
            icon: Icons.info_outline_rounded,
            title: l10n.chatOptionsInfo,
            onTap: onInfo,
          ),
          if (showResumeOption && onResume != null)
            _buildMenuItem(
              context,
              icon: Icons.play_arrow_rounded,
              title: l10n.chatOptionsResume,
              onTap: onResume!,
              isDisabled: resumeDisabledReason != null,
              disabledReason: resumeDisabledReason,
            ),
          if (onPin != null)
            _buildMenuItem(
              context,
              icon: isPinned ? Icons.push_pin_outlined : Icons.push_pin_rounded,
              title: isPinned ? l10n.chatOptionsUnpin : l10n.chatOptionsPin,
              onTap: onPin!,
            ),
          if (showShareOption)
            _buildMenuItem(
              context,
              icon: Icons.ios_share_rounded,
              title: l10n.commonShare,
              onTap: onShare,
            ),
          _buildMenuItem(
            context,
            icon: Icons.edit_rounded,
            title: l10n.chatOptionsRename,
            onTap: onRename,
          ),
          if (showCloseOption)
            _buildMenuItem(
              context,
              icon: Icons.archive_rounded,
              title: l10n.sessionActionsArchive,
              onTap: onClose,
            ),
          _buildMenuItem(
            context,
            icon: Icons.delete_rounded,
            title: l10n.commonDelete,
            onTap: onDelete,
            isDestructive: true,
            isLast: true,
          ),
        ],
      ),
    );
  }


  Widget _buildMenuItem(
    BuildContext context, {
    required IconData icon,
    required String title,
    required VoidCallback onTap,
    bool isDestructive = false,
    bool isLast = false,
    bool isDisabled = false,
    String? disabledReason,
  }) {
    final theme = FlutterFlowTheme.of(context);
    // Destructive items keep the same color as the rest — the label text
    // ("Delete") carries the signal; no red tint.
    final color = isDisabled ? theme.secondaryText.withValues(alpha: 0.5) : theme.primaryText;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          if (isDisabled) {
            // Explain instead of doing nothing — a dead tap reads as a bug.
            if (disabledReason != null) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(disabledReason)));
            }
            return;
          }
          onTap();
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
              Icon(icon, size: 18, color: color),
              const SizedBox(width: 18),
              Expanded(
                child: Text(
                  title,
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
