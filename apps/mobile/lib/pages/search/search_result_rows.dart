import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/custom_code/utils/automation_utils.dart' as autils;
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/custom_functions.dart' as functions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/pages/tasks/task_glyphs.dart';

/// Shared tappable result row: a leading glyph, a title with an optional
/// second line (the match snippet), and an optional trailing widget. Kept
/// deliberately flat (not a card) so a long results list reads calmly, matching
/// the palette feel of the web ⌘K overlay.
class _ResultRow extends StatelessWidget {
  const _ResultRow({
    required this.leading,
    required this.title,
    this.subtitle,
    this.trailing,
    required this.onTap,
  });

  final Widget leading;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final subtitleText = subtitle?.trim() ?? '';
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12.0),
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(6.0, 10.0, 6.0, 10.0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            SizedBox(width: 24.0, child: Center(child: leading)),
            const SizedBox(width: 12.0),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.bodyLarge.override(
                      font: GoogleFonts.sourceSans3(),
                      letterSpacing: 0.0,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  if (subtitleText.isNotEmpty) ...[
                    const SizedBox(height: 2.0),
                    Text(
                      subtitleText,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.bodySmall.override(
                        font: GoogleFonts.sourceSans3(),
                        letterSpacing: 0.0,
                        color: theme.secondaryText,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (trailing != null) ...[
              const SizedBox(width: 10.0),
              trailing!,
            ],
          ],
        ),
      ),
    );
  }
}

String _sessionTitle(Map session) {
  final name = session['name']?.toString().trim() ?? '';
  if (name.isNotEmpty) return name;
  final msg = session['latest_message']?.toString().trim() ?? '';
  if (msg.isNotEmpty && !msg.contains('API Error') && !msg.contains('error')) {
    return msg;
  }
  final raw = session['agent_type_name']?.toString();
  if (raw == null || raw.isEmpty) return 'Agent';
  return raw.toLowerCase() == 'claude' ? 'Claude Code' : raw;
}

String _projectBasename(dynamic project) {
  final path = project?.toString().trim() ?? '';
  if (path.isEmpty) return '';
  final clean = path.endsWith('/') ? path.substring(0, path.length - 1) : path;
  final last = clean.split('/').last;
  return last.isNotEmpty ? last : '';
}

class SearchSessionRow extends StatelessWidget {
  const SearchSessionRow({super.key, required this.session, required this.onTap});

  final Map<String, dynamic> session;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    // The message snippet (server match) is the most useful second line; fall
    // back to the project name so the row still has context on a title match.
    final snippet = session['snippet']?.toString().trim() ?? '';
    final project = _projectBasename(session['project']);
    final closed = functions.isSessionClosed(session['status']?.toString());
    return _ResultRow(
      leading: AgentTypeIconWidget(
        agentTypeName: session['agent_type_name']?.toString(),
        size: 20.0,
        muted: closed,
      ),
      title: _sessionTitle(session),
      subtitle: snippet.isNotEmpty ? snippet : null,
      trailing: project.isEmpty
          ? null
          : Text(
              project,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.bodySmall.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
                color: theme.secondaryText,
              ),
            ),
      onTap: onTap,
    );
  }
}

class SearchTaskRow extends StatelessWidget {
  const SearchTaskRow({super.key, required this.task, required this.onTap});

  final Map<String, dynamic> task;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final snippet = task['snippet']?.toString().trim() ?? '';
    return _ResultRow(
      leading: TaskStatusIcon(status: tutils.taskStatus(task), size: 18.0),
      title: tutils.taskTitle(task),
      subtitle: snippet.isNotEmpty ? snippet : null,
      trailing: TaskPriorityIcon(priority: tutils.taskPriority(task), size: 14.0),
      onTap: onTap,
    );
  }
}

class SearchAutomationRow extends StatelessWidget {
  const SearchAutomationRow(
      {super.key, required this.automation, required this.onTap});

  final Map<String, dynamic> automation;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final snippet = automation['snippet']?.toString().trim() ?? '';
    final enabled = autils.automationEnabled(automation);
    return _ResultRow(
      leading: Icon(
        Icons.schedule_rounded,
        size: 20.0,
        color: theme.secondaryText,
      ),
      title: autils.automationTitle(automation),
      subtitle: snippet.isNotEmpty ? snippet : null,
      // A small state dot (brand color = active, muted = paused) keeps the row
      // glanceable without another localized label.
      trailing: Container(
        width: 8.0,
        height: 8.0,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: enabled ? theme.primary : theme.secondaryText.withValues(alpha: 0.4),
        ),
      ),
      onTap: onTap,
    );
  }
}
