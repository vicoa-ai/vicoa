import 'package:flutter/material.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

/// Should the composer's primary button act as Stop rather than Send?
///
/// Mirrors the web's `shouldShowStopButton` (`apps/web/lib/chat-composer.ts`).
/// The empty-composer condition is deliberate: typing mid-turn still queues a
/// follow-up (the queued-messages bar), and a stale ACTIVE status can never
/// lock the user out of sending, since one character brings Send back.
bool shouldShowComposerStop({required bool canSend, required bool agentWorking, required bool hasContent}) =>
    canSend && agentWorking && !hasContent;

/// The round button at the composer's right edge: Send, doubling as Stop
/// while a turn is running and nothing is typed. A spinner while a send is
/// in flight.
class ComposerPrimaryButton extends StatelessWidget {
  const ComposerPrimaryButton({
    super.key,
    required this.isSending,
    required this.showStop,
    required this.onSend,
    required this.onStop,
  });

  final bool isSending;
  final bool showStop;
  final VoidCallback onSend;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final Widget child;
    if (isSending) {
      child = Center(
        child: SizedBox(
          width: 20.0,
          height: 20.0,
          child: CircularProgressIndicator(strokeWidth: 2.0, valueColor: AlwaysStoppedAnimation<Color>(theme.secondaryText)),
        ),
      );
    } else if (showStop) {
      child = Icon(Icons.stop_rounded, color: theme.primaryText, size: 22.0);
    } else {
      child = Icon(Icons.arrow_upward_rounded, color: theme.primaryText, size: 22.0);
    }
    final button = Container(
      width: 40.0,
      height: 40.0,
      decoration: BoxDecoration(
        color: theme.secondaryText.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(20.0),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20.0),
          onTap: isSending ? null : (showStop ? onStop : onSend),
          child: SizedBox(width: 40.0, height: 40.0, child: child),
        ),
      ),
    );
    if (!showStop || isSending) return button;
    return Tooltip(message: AppLocalizations.of(context).chatInputStopTask, child: button);
  }
}
