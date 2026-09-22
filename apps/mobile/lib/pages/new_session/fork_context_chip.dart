// The conversation a fork carried into the new-session composer.
//
// A fork attaches text, not a file, and that text is invisible until the
// session has already started — on a phone there is no hover, no tooltip and
// no dev-tools to check what came along. So the chip is a full-width row
// rather than an attachment tile, it says how much history it holds, and
// tapping it opens the block itself. Removing it starts the session with a
// clean slate.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/fork_transcript.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

class ForkContextChip extends StatelessWidget {
  const ForkContextChip({super.key, required this.fork, required this.onRemove});

  final ForkSessionContext fork;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final subtitle = <String>[
      if (fork.sourceTitle != null) l10n.newSessionForkFrom(fork.sourceTitle!),
      if (fork.omittedCount > 0) l10n.newSessionForkOmitted(fork.omittedCount),
    ].join(' · ');

    return Container(
      margin: const EdgeInsets.only(bottom: 6.0),
      decoration: BoxDecoration(
        color: theme.secondaryText.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(16.0),
        border: Border.all(color: theme.secondaryText.withValues(alpha: 0.2), width: 1.0),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          onTap: () {
            HapticFeedback.lightImpact();
            showForkContextPreview(context, fork);
          },
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(12.0, 8.0, 4.0, 8.0),
            child: Row(
              children: [
                Icon(Icons.alt_route_rounded, size: 18.0, color: theme.secondaryText),
                const SizedBox(width: 10.0),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${l10n.newSessionForkChipTitle} · ${l10n.newSessionForkMessages(fork.messageCount)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.bodyMedium.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.primaryText,
                          fontSize: 14.0,
                          letterSpacing: 0.0,
                        ),
                      ),
                      if (subtitle.isNotEmpty)
                        Text(
                          subtitle,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.bodySmall.override(
                            font: GoogleFonts.sourceSans3(),
                            color: theme.secondaryText,
                            fontSize: 12.0,
                            letterSpacing: 0.0,
                          ),
                        ),
                    ],
                  ),
                ),
                IconButton(
                  icon: Icon(Icons.close_rounded, size: 18.0, color: theme.secondaryText),
                  tooltip: l10n.newSessionForkRemove,
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    onRemove();
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The block itself, read-only: what the new session is about to be told.
Future<void> showForkContextPreview(BuildContext context, ForkSessionContext fork) {
  final theme = FlutterFlowTheme.of(context);
  final l10n = AppLocalizations.of(context);
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      expand: false,
      builder: (sheetContext, scrollController) => Container(
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20.0)),
        ),
        child: Column(
          children: [
            Container(
              margin: const EdgeInsets.only(top: 10.0, bottom: 6.0),
              width: 36.0,
              height: 4.0,
              decoration: BoxDecoration(
                color: theme.secondaryText.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(20.0, 4.0, 8.0, 0.0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '${l10n.newSessionForkChipTitle} · ${l10n.newSessionForkMessages(fork.messageCount)}',
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500),
                        color: theme.primaryText,
                        fontSize: 17.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close_rounded, size: 20.0, color: theme.secondaryText),
                    onPressed: () => Navigator.pop(sheetContext),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(20.0, 0.0, 20.0, 12.0),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: Text(
                  l10n.newSessionForkPreviewHint,
                  style: theme.bodySmall.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.secondaryText,
                    fontSize: 12.0,
                    letterSpacing: 0.0,
                  ),
                ),
              ),
            ),
            Expanded(
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(20.0, 0.0, 20.0, 32.0),
                children: [
                  SelectableText(
                    fork.text,
                    style: GoogleFonts.jetBrainsMono().copyWith(
                      color: theme.primaryText,
                      fontSize: 12.0,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
