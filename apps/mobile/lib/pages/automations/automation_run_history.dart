import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/automation_utils.dart' as autils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'automation_l10n.dart';

/// Run history rows for the edit sheet: status icon + label + fired-at time,
/// tappable when the run linked an agent session.
class AutomationRunHistory extends StatefulWidget {
  const AutomationRunHistory({
    super.key,
    required this.automationId,
    required this.onOpenInstance,
  });

  final String automationId;
  final ValueChanged<String> onOpenInstance;

  @override
  State<AutomationRunHistory> createState() => _AutomationRunHistoryState();
}

class _AutomationRunHistoryState extends State<AutomationRunHistory> {
  List<dynamic> _runs = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final runs = await actions.apiGetAutomationRuns(widget.automationId);
    if (!mounted) return;
    setState(() {
      _runs = runs;
      _loading = false;
    });
  }

  (IconData, Color) _statusGlyph(FlutterFlowTheme theme, String status) {
    switch (status) {
      case 'fired':
        return (Icons.check_circle_rounded, theme.success);
      case 'missed_offline':
        return (Icons.error_outline_rounded, theme.warning);
      case 'failed':
        return (Icons.cancel_rounded, theme.error);
      default:
        return (Icons.remove_circle_outline_rounded, theme.secondaryText);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final locale = Localizations.localeOf(context).toString();

    if (_loading) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 18.0),
        child: Center(
          child: SizedBox(
            width: 18.0,
            height: 18.0,
            child: CircularProgressIndicator(
              strokeWidth: 2.0,
              valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
            ),
          ),
        ),
      );
    }
    if (_runs.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: 14.0, vertical: 14.0),
        child: Text(
          l10n.automationsNoRunsYet,
          style: theme.bodySmall.override(
            font: GoogleFonts.sourceSans3(),
            letterSpacing: 0.0,
            color: theme.secondaryText,
          ),
        ),
      );
    }

    return Column(
      children: [
        for (var i = 0; i < _runs.length; i++) ...[
          if (i > 0)
            Divider(
              height: 1.0,
              thickness: 1.0,
              indent: 14.0,
              color: theme.alternate.withValues(alpha: 0.6),
            ),
          _runRow(context, theme, l10n, locale, _runs[i]),
        ],
      ],
    );
  }

  Widget _runRow(BuildContext context, FlutterFlowTheme theme,
      AppLocalizations l10n, String locale, dynamic run) {
    final status = autils.automationRunStatus(run);
    final (icon, color) = _statusGlyph(theme, status);
    final firedAt = autils.automationRunFiredAt(run);
    final when = firedAt == null
        ? ''
        : '${DateFormat.MMMd(locale).format(firedAt)}, ${DateFormat.jm(locale).format(firedAt)}';
    final instanceId = autils.automationRunInstanceId(run);
    final detail = autils.automationRunDetail(run);

    final row = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 11.0),
      child: Row(
        children: [
          Icon(icon, size: 17.0, color: color),
          const SizedBox(width: 10.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${automationRunStatusLabel(l10n, status)} · $when',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 14.0,
                    letterSpacing: 0.0,
                  ),
                ),
                if (detail != null)
                  Text(
                    detail,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.bodySmall.override(
                      font: GoogleFonts.sourceSans3(),
                      fontSize: 12.0,
                      letterSpacing: 0.0,
                      color: theme.secondaryText,
                    ),
                  ),
              ],
            ),
          ),
          if (instanceId != null)
            Icon(Icons.arrow_outward_rounded,
                size: 16.0, color: theme.secondaryText),
        ],
      ),
    );

    if (instanceId == null) return row;
    return InkWell(
      onTap: () {
        HapticFeedback.lightImpact();
        widget.onOpenInstance(instanceId);
      },
      child: row,
    );
  }
}
