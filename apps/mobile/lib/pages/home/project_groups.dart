// Project grouping for the home session list — the mobile twin of the web
// sidebar's `groupSessions(..., 'project')` in `session-grouping.ts`.

/// Label of the group for sessions with no project at all. Kept in English
/// like the other group keys; `localizedFilterLabel` translates it at render.
const String kNoProjectGroup = 'No Project';

const String _noProjectKey = '__no_project__';

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

/// Group [sessions] (already sorted newest first) by project.
///
/// Keyed on the session's `project_id` (falling back to the folder basename
/// for a session with no linked project) and labelled with the DB project's
/// name, so a group reads the same here as in the web sidebar and on the
/// Tasks board. Groups follow the order of [projects] — `GET /projects`
/// returns the viewer's drag-and-drop order first, then recency — which is
/// what carries an arrangement made on desktop or web over to the phone.
/// Groups the project list doesn't know (unlinked folders, a project not
/// loaded yet) trail alphabetically; "No project" is always last. Two
/// projects sharing a name fold into one group, as same-named folders
/// always have.
Map<String, List<dynamic>> groupSessionsByProject(
  List<dynamic> sessions,
  List<dynamic> projects,
) {
  final rank = <String, int>{};
  final nameById = <String, String>{};
  for (final project in projects) {
    if (project is! Map) continue;
    final id = project['id']?.toString() ?? '';
    if (id.isEmpty) continue;
    rank.putIfAbsent(id, () => rank.length);
    final name = project['name']?.toString().trim() ?? '';
    if (name.isNotEmpty) nameById[id] = name;
  }

  final byKey = <String, List<dynamic>>{};
  final labelByKey = <String, String>{};
  for (final session in sessions) {
    if (session is! Map) continue;
    final key = sessionProjectKey(session);
    labelByKey.putIfAbsent(key, () {
      if (key == _noProjectKey) return kNoProjectGroup;
      final dbName = nameById[key];
      if (dbName != null) return dbName;
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

  final grouped = <String, List<dynamic>>{};
  for (final key in keys) {
    grouped.putIfAbsent(labelByKey[key]!, () => []).addAll(byKey[key]!);
  }
  return grouped;
}
