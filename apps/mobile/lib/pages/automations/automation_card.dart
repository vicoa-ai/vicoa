import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/automation_utils.dart' as autils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'automation_l10n.dart';

/// One automation list row: pause/resume toggle, title + schedule summary +
/// next-run line, and a ⋯ button for Run now / Pause / Delete.
class AutomationCard extends StatelessWidget {
  const AutomationCard({
    super.key,
    required this.automation,
    required this.isBusy,
    required this.onTap,
    required this.onToggleEnabled,
    required this.onShowActions,
  });

  final dynamic automation;
  final bool isBusy;
  final VoidCallback onTap;
  final VoidCallback onToggleEnabled;
  final VoidCallback onShowActions;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final enabled = autils.automationEnabled(automation);
    final next = nextRunLabel(context, automation);
    final lastStatus = autils.automationLastRunStatus(automation);

    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 5.0, 16.0, 5.0),
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        borderRadius: BorderRadius.circular(16.0),
        child: Container(
          decoration: BoxDecoration(
            color: theme.primaryBackground,
            borderRadius: BorderRadius.circular(16.0),
            border: Border.all(color: theme.alternate),
          ),
          padding: const EdgeInsetsDirectional.fromSTEB(6.0, 10.0, 6.0, 10.0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Status glyph — shows the STATE (like the web list and the
              // Tasks status icons): plain circle = active, pause-in-circle =
              // paused. Neutral colors; tapping toggles.
              IconButton(
                onPressed: () {
                  HapticFeedback.selectionClick();
                  onToggleEnabled();
                },
                icon: Icon(
                  enabled
                      ? Icons.circle_outlined
                      : Icons.pause_circle_outline_rounded,
                  size: 24.0,
                  color: theme.secondaryText,
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      autils.automationTitle(automation),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.bodyLarge.override(
                        font: GoogleFonts.sourceSans3(),
                        fontSize: 16.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w600,
                        color:
                            enabled ? theme.primaryText : theme.secondaryText,
                      ),
                    ),
                    const SizedBox(height: 2.0),
                    Text(
                      summarizeAutomationSchedule(context, automation),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.bodySmall.override(
                        font: GoogleFonts.sourceSans3(),
                        fontSize: 13.0,
                        letterSpacing: 0.0,
                        color: theme.secondaryText,
                      ),
                    ),
                    if (enabled && next != null) ...[
                      const SizedBox(height: 2.0),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (lastStatus != null) ...[
                            _LastRunDot(status: lastStatus),
                            const SizedBox(width: 5.0),
                          ],
                          Flexible(
                            child: Text(
                              next,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.bodySmall.override(
                                font: GoogleFonts.sourceSans3(),
                                fontSize: 12.0,
                                letterSpacing: 0.0,
                                color:
                                    theme.secondaryText.withValues(alpha: 0.8),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ] else if (!enabled) ...[
                      const SizedBox(height: 2.0),
                      Text(
                        l10n.automationsStatusPaused,
                        style: theme.bodySmall.override(
                          font: GoogleFonts.sourceSans3(),
                          fontSize: 12.0,
                          letterSpacing: 0.0,
                          color: theme.secondaryText.withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (isBusy)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12.0),
                  child: SizedBox(
                    width: 18.0,
                    height: 18.0,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.0,
                      valueColor:
                          AlwaysStoppedAnimation<Color>(theme.primary),
                    ),
                  ),
                )
              else
                IconButton(
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    onShowActions();
                  },
                  icon: Icon(Icons.more_horiz_rounded,
                      size: 22.0, color: theme.secondaryText),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Tiny status dot summarizing the last run outcome next to the next-run line.
class _LastRunDot extends StatelessWidget {
  const _LastRunDot({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final color = switch (status) {
      'fired' => theme.success,
      'missed_offline' => theme.warning,
      'failed' => theme.error,
      _ => theme.secondaryText,
    };
    return Container(
      width: 7.0,
      height: 7.0,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }
}
