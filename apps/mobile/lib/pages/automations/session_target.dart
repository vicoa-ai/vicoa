// A session an automation can run in, as the "Runs in" picker lists it. Pure
// so it can be unit-tested without pumping the sheet.

import '/custom_code/actions/api_resume_session.dart' show resumeAgentSlug;
import '/pages/home/session_card_text.dart' show sessionCardRow1;

class AutomationSessionTarget {
  const AutomationSessionTarget({
    required this.id,
    required this.title,
    required this.machineId,
    required this.project,
    required this.agent,
    this.at,
  });

  final String id;
  /// The session's title as the Home card shows it.
  final String title;
  final String machineId;
  /// The session's folder, as the backend stores it (may start with `~`).
  final String project;
  /// Catalog agent id ('claude', 'codex', …), for the prompt's `/` and `@`.
  final String agent;
  /// Latest activity, for the row's date.
  final DateTime? at;
}

/// [session] as the picker lists it, or null for one the scheduler could never
/// reach: deleted, or with no computer or folder to resume it in (a legacy
/// terminal session). Takes rows from both the session list and search.
AutomationSessionTarget? automationSessionTargetFrom(dynamic session) {
  if (session is! Map) return null;
  final s = Map<String, dynamic>.from(session);
  final id = s['id']?.toString() ?? '';
  final machineId = s['machine_id']?.toString() ?? '';
  final project = s['project']?.toString().trim() ?? '';
  if (id.isEmpty || machineId.isEmpty || project.isEmpty) return null;
  if (s['status']?.toString() == 'DELETED') return null;
  final config = s['session_config'] is Map
      ? Map<String, dynamic>.from(s['session_config'] as Map)
      : null;
  final at = (s['latest_message_at'] ?? s['started_at'])?.toString();
  return AutomationSessionTarget(
    id: id,
    title: sessionCardRow1(s),
    machineId: machineId,
    project: project,
    agent: resumeAgentSlug(s['agent_type_name']?.toString(), sessionConfig: config),
    at: at == null ? null : DateTime.tryParse(at)?.toLocal(),
  );
}

/// The pickable sessions in [sessions], in order.
List<AutomationSessionTarget> automationSessionTargets(Iterable<dynamic> sessions) =>
    sessions.map(automationSessionTargetFrom).whereType<AutomationSessionTarget>().toList();
