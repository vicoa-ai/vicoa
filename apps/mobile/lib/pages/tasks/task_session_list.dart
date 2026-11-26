import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'task_timeline_text.dart';
import 'task_timeline_view.dart' show taskSessionIsClosed, taskSessionTime, taskSessionTitle;

/// A task's Sessions list: every session its record names (filed under it,
/// created it, changed it, commented on it, referenced it), one line each,
/// most recently active first. A row is only a way into the session; resuming
/// it is the chat's own business. The twin of the web's `TaskSessionList`.
///
/// A line is the agent mark, the title and the strongest relation; a long
/// press lists every relation.
class TaskSessionList extends StatefulWidget {
  const TaskSessionList({super.key, required this.sessions, required this.onOpenSession});

  final List<dynamic> sessions;
  final void Function(String sessionId) onOpenSession;

  @override
  State<TaskSessionList> createState() => _TaskSessionListState();
}

/// Rows before "Show all": the recent few are the ones you go back to.
const int _kCollapsedRows = 5;

class _TaskSessionListState extends State<TaskSessionList> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final all = widget.sessions;
    final shown = _expanded ? all : all.take(_kCollapsedRows).toList();
    final small = theme.labelMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 12.5, letterSpacing: 0.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final s in shown) _row(context, s, theme, l10n, small),
        if (all.length > _kCollapsedRows)
          InkWell(
            borderRadius: BorderRadius.circular(8.0),
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8.0),
              child: Text(_expanded ? l10n.tasksShowFewer : l10n.tasksShowAll(all.length), style: small),
            ),
          ),
      ],
    );
  }

  Widget _row(BuildContext context, dynamic s, FlutterFlowTheme theme, AppLocalizations l10n, TextStyle small) {
    final id = (s is Map ? s['id'] : null)?.toString() ?? '';
    final relations = tutils.sessionTaskRelations(s);
    final strongest = relations.isEmpty ? null : sessionRelationLabel(l10n, relations.first);
    return Tooltip(
      message: [taskSessionTitle(s), relations.map((r) => sessionRelationLabel(l10n, r)).join(', '), taskSessionTime(s)].where((t) => t.isNotEmpty).join('\n'),
      triggerMode: TooltipTriggerMode.longPress,
      child: InkWell(
        borderRadius: BorderRadius.circular(8.0),
        onTap: id.isEmpty ? null : () => widget.onOpenSession(id),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8.0),
          child: Row(
            children: [
              AgentTypeIconWidget(agentTypeName: (s is Map ? s['agent_type_name'] : null)?.toString(), size: 15.0, muted: taskSessionIsClosed(s)),
              const SizedBox(width: 10.0),
              Expanded(
                child: Text(
                  taskSessionTitle(s),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.primaryText, fontSize: 14.0, letterSpacing: 0.0),
                ),
              ),
              if (strongest != null) ...[const SizedBox(width: 8.0), Text(strongest, style: small)],
            ],
          ),
        ),
      ),
    );
  }
}
