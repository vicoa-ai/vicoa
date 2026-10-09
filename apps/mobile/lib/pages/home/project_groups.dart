// Project grouping for the home session list — the mobile twin of the web
// sidebar's `groupSessions(..., 'project')` in `session-grouping.ts`.

/// Label of the group for sessions with no project at all. Kept in English
/// like the other group keys; `localizedFilterLabel` translates it at render.
const String kNoProjectGroup = 'No Project';

const String _noProjectKey = '__no_project__';

/// One group of the home list. [key] is its identity (what collapse state is
/// stored under); [label] is what the header shows. A project group carries
/// [isProject] so the header draws the project's icon, and [project] — the DB
/// row — when the group is a linked project rather than a bare folder.
class SessionGroup {
  const SessionGroup({
    required this.key,
    required this.label,
    required this.sessions,
    this.isProject = false,
    this.project,
  });

  final String key;
  final String label;
  final List<dynamic> sessions;
  final bool isProject;
  final Map<String, dynamic>? project;

  /// The group for sessions with no folder at all.
  bool get isNoProject => key == _noProjectKey;
}

/// Stable identity of the project a session belongs to: its linked
/// `project_id`, else the folder basename for a session no project claims,
/// else the shared no-project key.
String sessionProjectKey(Map session) {
  final projectId = session['project_id']?.toString() ?? '';
  if (projectId.isNotEmpty) return projectId;
  final basename = _folderBasename(session);
  return basename.isEmpty ? _noProjectKey : basename;
}

String _folderBasename(Map session) {
  final raw = session['project']?.toString().trim() ?? '';
  if (raw.isEmpty) return '';
  final clean = raw.endsWith('/') ? raw.substring(0, raw.length - 1) : raw;
  return clean.split('/').last;
}

Map<String, Map<String, dynamic>> _projectsById(List<dynamic> projects) {
  final byId = <String, Map<String, dynamic>>{};
  for (final project in projects) {
    if (project is! Map) continue;
    final id = project['id']?.toString() ?? '';
    if (id.isNotEmpty) byId.putIfAbsent(id, () => Map<String, dynamic>.from(project));
  }
  return byId;
}

/// Drops the sessions filed under an archived project, as the web sidebar does
/// in every grouping: archiving a project declutters it off every device.
/// Needs a project list that includes archived rows. A session whose project
/// isn't in [projects] (not loaded yet) always stays.
List<dynamic> withoutArchivedProjects(
    List<dynamic> sessions, List<dynamic> projects) {
  final byId = _projectsById(projects);
  if (byId.isEmpty) return sessions;
  return sessions.where((s) {
    if (s is! Map) return true;
    final projectId = s['project_id']?.toString() ?? '';
    return byId[projectId]?['is_archived'] != true;
  }).toList();
}

/// Group [sessions] (already sorted newest first) by project.
///
/// Keyed on the session's `project_id` (falling back to the folder basename
/// for a session with no linked project) and labelled with the DB project's
/// name, so a group reads the same here as in the web sidebar and on the
/// Tasks board. Two projects that share a name stay two groups, as on web.
/// Groups follow the order of [projects] — `GET /projects` returns the
/// viewer's drag-and-drop order first, then recency — which is what carries
/// an arrangement made on desktop or web over to the phone. Groups the
/// project list doesn't know (unlinked folders, a project not loaded yet)
/// trail alphabetically; "No project" is always last.
List<SessionGroup> groupSessionsByProject(
  List<dynamic> sessions,
  List<dynamic> projects,
) {
  final byId = _projectsById(projects);
  final rank = <String, int>{};
  for (final id in byId.keys) {
    rank[id] = rank.length;
  }

  final byKey = <String, List<dynamic>>{};
  final labelByKey = <String, String>{};
  for (final session in sessions) {
    if (session is! Map) continue;
    final key = sessionProjectKey(session);
    labelByKey.putIfAbsent(key, () {
      if (key == _noProjectKey) return kNoProjectGroup;
      final dbName = byId[key]?['name']?.toString().trim() ?? '';
      if (dbName.isNotEmpty) return dbName;
      final basename = _folderBasename(session);
      return basename.isEmpty ? key : basename;
    });
    byKey.putIfAbsent(key, () => []).add(session);
  }

  final keys = byKey.keys.toList()
    ..sort((a, b) {
      if (a == _noProjectKey) return 1;
      if (b == _noProjectKey) return -1;
      final rankA = rank[a];
      final rankB = rank[b];
      if (rankA != null && rankB != null) return rankA.compareTo(rankB);
      if (rankA != null) return -1;
      if (rankB != null) return 1;
      return labelByKey[a]!.toLowerCase().compareTo(labelByKey[b]!.toLowerCase());
    });

  return [
    for (final key in keys)
      SessionGroup(
        key: key,
        label: labelByKey[key]!,
        sessions: byKey[key]!,
        isProject: true,
        project: byId[key],
      ),
  ];
}
