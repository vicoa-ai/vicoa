import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
/// - `failed`: a red circled `!`. Tap → [onTap], which asks "Resend this
///   message?" before anything happens. Never resends directly: a resend can
///   duplicate, and a 44px target beside a bubble is easy to hit while
///   scrolling.
class SendStatusIndicator extends StatefulWidget {
  const SendStatusIndicator({
    super.key,
    required this.status,
    required this.sentAt,
    required this.onTap,
  });

  final String status;
  final DateTime? sentAt;
  final VoidCallback onTap;

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
                widget.onTap();
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
