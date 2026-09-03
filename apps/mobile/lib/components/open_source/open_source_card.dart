import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';

import '/constants/open_source.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/session_actions.dart';

/// Home card telling the user that Vicoa is open source, with a one-tap path
/// to the repo in their own browser and a copy button for reading it on a
/// computer later. Purely informational: the free-messages reward for starring
/// lives on Usage & Credits alone, so home never asks for anything. Hides
/// itself once dismissed, so it doesn't become permanent furniture.
class OpenSourceCard extends StatefulWidget {
  const OpenSourceCard({super.key, this.onStateChanged});

  /// Called when the card hides itself (dismiss) so home can drop the
  /// surrounding padding.
  final VoidCallback? onStateChanged;

  @override
  State<OpenSourceCard> createState() => _OpenSourceCardState();
}

class _OpenSourceCardState extends State<OpenSourceCard> {
  late bool _dismissed = FFAppState().openSourceCardDismissed;

  Future<void> _viewCode() async {
    HapticFeedback.lightImpact();
    logFirebaseEvent('open_source_card_view_code');
    await openGithubUrl(kGithubRepoUrl);
  }

  Future<void> _copyLink() async {
    HapticFeedback.lightImpact();
    logFirebaseEvent('open_source_card_copy_link');
    await Clipboard.setData(const ClipboardData(text: kGithubRepoUrl));
    if (!mounted) {
      return;
    }
    SessionActions.showSnack(
        context, AppLocalizations.of(context).commonCopied,
        waitTime: 1500);
  }

  void _dismiss() {
    HapticFeedback.lightImpact();
    logFirebaseEvent('open_source_card_dismiss');
    FFAppState().openSourceCardDismissed = true;
    setState(() => _dismissed = true);
    widget.onStateChanged?.call();
  }

  @override
  Widget build(BuildContext context) {
    if (_dismissed) {
      return const SizedBox.shrink();
    }

    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(16.0),
        onTap: _viewCode,
        child: Container(
          decoration: BoxDecoration(
            color: theme.primaryBackground,
            borderRadius: BorderRadius.circular(16.0),
            border: Border.all(
                color: theme.primary.withValues(alpha: 0.20), width: 1.0),
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 8.0, 14.0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 2.0, right: 10.0),
                  child: FaIcon(FontAwesomeIcons.github,
                      color: theme.primaryText, size: 20.0),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        l10n.openSourceCardTitle,
                        style: theme.titleSmall.override(
                          font: GoogleFonts.sourceSans3(),
                          fontWeight: FontWeight.w700,
                          fontSize: 16.0,
                          letterSpacing: 0.0,
                        ),
                      ),
                      const SizedBox(height: 3.0),
                      Text(
                        l10n.openSourceCardBody,
                        style: theme.bodySmall.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText,
                          fontSize: 12.5,
                          letterSpacing: 0.0,
                        ),
                      ),
                    ],
                  ),
                ),
                // Dismiss keeps the top-right corner it always had; copy sits
                // under it — starring is easiest on a computer, so the card
                // offers the URL as well as the tap-through.
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _CardIconButton(
                      icon: Icons.close_rounded,
                      tooltip: l10n.openSourceCardDismissTooltip,
                      onTap: _dismiss,
                    ),
                    _CardIconButton(
                      icon: Icons.copy_rounded,
                      tooltip: l10n.openSourceCardCopyTooltip,
                      onTap: _copyLink,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CardIconButton extends StatelessWidget {
  const _CardIconButton({
    required this.icon,
    required this.tooltip,
    required this.onTap,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(8.0),
        onTap: onTap,
        child: Tooltip(
          message: tooltip,
          child: Padding(
            padding: const EdgeInsets.all(6.0),
            child: Icon(icon, size: 18.0, color: theme.secondaryText),
          ),
        ),
      ),
    );
  }
}
