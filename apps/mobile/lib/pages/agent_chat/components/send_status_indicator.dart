import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'message_queue_status.dart';

/// The small status mark to the left of a user bubble that is still sending
/// or failed to send. Sits outside the bubble so the bubble itself renders
/// exactly as a sent one.
///
/// - `sending`: nothing until [kSendIndicatorDelay] has passed since
///   [sentAt] (wall-clock, so a background/resume can't desync it), then a
///   thin grey spinner.
/// - `failed`: a red circled `!`. Tap → [onRetry]; long-press → [onMore]
///   (edit / delete).
class SendStatusIndicator extends StatefulWidget {
  const SendStatusIndicator({
    super.key,
    required this.status,
    required this.sentAt,
    required this.onRetry,
    required this.onMore,
  });

  final String status;
  final DateTime? sentAt;
  final VoidCallback onRetry;
  final VoidCallback onMore;

  @override
  State<SendStatusIndicator> createState() => _SendStatusIndicatorState();
}

class _SendStatusIndicatorState extends State<SendStatusIndicator> {
  Timer? _revealTimer;
  bool _revealed = false;

  @override
  void initState() {
    super.initState();
    _scheduleReveal();
  }

  @override
  void didUpdateWidget(SendStatusIndicator oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A retry restamps sentAt; start the quiet window again.
    if (oldWidget.sentAt != widget.sentAt || oldWidget.status != widget.status) {
      _revealed = false;
      _scheduleReveal();
    }
  }

  void _scheduleReveal() {
    _revealTimer?.cancel();
    _revealTimer = null;
    if (widget.status != kSendStatusSending) return;
    final started = widget.sentAt ?? DateTime.now();
    final remaining = kSendIndicatorDelay - DateTime.now().difference(started);
    if (remaining <= Duration.zero) {
      _revealed = true;
      return;
    }
    _revealTimer = Timer(remaining, () {
      if (mounted) setState(() => _revealed = true);
    });
  }

  @override
  void dispose() {
    _revealTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    if (widget.status == kSendStatusFailed) {
      return Semantics(
        button: true,
        label: AppLocalizations.of(context).agentChatNotSentTapToRetry,
        child: Tooltip(
          message: AppLocalizations.of(context).agentChatNotSentTapToRetry,
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(22.0),
              onTap: () {
                HapticFeedback.lightImpact();
                widget.onRetry();
              },
              onLongPress: () {
                HapticFeedback.mediumImpact();
                widget.onMore();
              },
              // 44px hit target around a 22px glyph.
              child: SizedBox(
                width: 44.0,
                height: 44.0,
                child: Icon(
                  Icons.error_rounded,
                  color: theme.error,
                  size: 22.0,
                ),
              ),
            ),
          ),
        ),
      );
    }

    // Take no space while quiet: the common 200–800ms send must lay out
    // exactly like a sent bubble. A long message may re-wrap when the spinner
    // does appear at 2s — that's the rare path, and the right trade.
    if (!_revealed) return const SizedBox.shrink();
    return SizedBox(
      width: 44.0,
      height: 44.0,
      child: Center(
        child: SizedBox(
          width: 14.0,
          height: 14.0,
          child: CircularProgressIndicator(
            strokeWidth: 1.5,
            color: theme.secondaryText.withValues(alpha: 0.6),
          ),
        ),
      ),
    );
  }
}

/// Long-press menu for a failed bubble: resend, edit in input, delete.
Future<void> showUnsentMessageSheet({
  required BuildContext context,
  required VoidCallback onResend,
  required VoidCallback onEdit,
  required VoidCallback onDelete,
}) {
  final theme = FlutterFlowTheme.of(context);
  final l10n = AppLocalizations.of(context);
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.transparent,
    builder: (ctx) => Container(
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24.0)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8.0),
            _UnsentAction(
              icon: Icons.refresh_rounded,
              label: l10n.agentChatResend,
              onTap: () {
                Navigator.of(ctx).pop();
                onResend();
              },
            ),
            _UnsentAction(
              icon: Icons.edit_rounded,
              label: l10n.agentChatRevertQueuedMessageTooltip,
              onTap: () {
                Navigator.of(ctx).pop();
                onEdit();
              },
            ),
            _UnsentAction(
              icon: Icons.delete_outline_rounded,
              label: l10n.commonDelete,
              color: theme.error,
              onTap: () {
                Navigator.of(ctx).pop();
                onDelete();
              },
            ),
            const SizedBox(height: 8.0),
          ],
        ),
      ),
    ),
  );
}

class _UnsentAction extends StatelessWidget {
  const _UnsentAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final tint = color ?? theme.primaryText;
    return InkWell(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(20.0, 14.0, 20.0, 14.0),
        child: Row(
          children: [
            Icon(icon, size: 22.0, color: tint),
            const SizedBox(width: 14.0),
            Text(
              label,
              style: theme.bodyLarge.override(
                font: GoogleFonts.sourceSans3(),
                color: tint,
                letterSpacing: 0.0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
