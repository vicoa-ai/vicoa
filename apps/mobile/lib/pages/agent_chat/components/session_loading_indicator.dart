import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/custom_code/utils/vibing_messages.dart';

/// Centered "the agent is spinning up its first response" state shown in the
/// chat while a freshly-spawned session — one started WITH an initial prompt —
/// has not yet produced its first message. Spawning + the agent's first turn
/// can lag a beat, so this animates (breathing glyph + the app's "vibing" wave
/// text) to read as active work instead of a stalled "Session ready" screen.
///
/// When no initial prompt was provided the chat keeps the static idle empty
/// state instead, since there is genuinely nothing being worked on.
class SessionLoadingIndicator extends StatelessWidget {
  const SessionLoadingIndicator({super.key, required this.vibingMessage});

  /// A vibing word (e.g. "Cooking…") owned by the parent so it stays stable
  /// across rebuilds — same source the in-chat typing indicator uses.
  final String vibingMessage;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Same glyph as the idle empty state, but breathing so the wait
          // reads as progress.
          FaIcon(FontAwesomeIcons.solidCommentDots, size: 48.0, color: theme.secondaryText)
              .animate(onPlay: (c) => c.repeat(reverse: true))
              .fade(begin: 0.45, end: 1.0, duration: 1000.0.ms, curve: Curves.easeInOut)
              .scaleXY(begin: 0.92, end: 1.08, duration: 1000.0.ms, curve: Curves.easeInOut),
          SizedBox(height: 16.0),
          Text(
            AppLocalizations.of(context).agentChatStartingYourSession,
            style: theme.titleMedium.override(
              color: theme.primaryText,
              fontSize: 16.0,
              fontWeight: FontWeight.w500,
            ),
          ),
          SizedBox(height: 8.0),
          // The app's "agent is working" wave-text motion — same language as
          // the in-chat typing indicator.
          VibingTextWidget(
            message: vibingMessage,
            textColor: theme.secondaryText,
            fontSize: 14.0,
          ),
        ],
      ),
    );
  }
}
