// Pure path helpers behind the project-first new-session picker
// (plans/todos/project-first-picker-and-sidebar.md §6). Mirrors the web's
// `lib/project-paths.ts`.
//
// The new-session directory is any folder inside a project — its root or a
// subfolder — and never a worktree path. These helpers resolve such a folder
// to the DB project it belongs to (longest linked-directory prefix on the
// selected machine), split off the part below the root, and carry that part
// into a worktree at spawn.

/// Trailing slashes dropped (the root `/` kept), `~` expanded when the home
/// dir is known — the one form every comparison below is made in.
String canonicalPath(String path, String? homeDir) {
  var p = path.trim();
  if (p.startsWith('~') && homeDir != null && homeDir.isNotEmpty) {
    var h = homeDir.trim();
    while (h.length > 1 && h.endsWith('/')) {
      h = h.substring(0, h.length - 1);
    }
    p = '$h${p.substring(1)}';
  }
  while (p.length > 1 && p.endsWith('/')) {
    p = p.substring(0, p.length - 1);
  }
  return p;
}

/// Last path segment — the folder's own name.
String pathBasename(String path) {
  final parts = path.split('/').where((s) => s.isNotEmpty).toList();
  return parts.isEmpty ? path : parts.last;
}

/// The part of [directory] below [root]: `''` when they are the same folder,
/// `apps/web` for `<root>/apps/web`, `null` when [directory] is not inside
/// [root] at all. Compared on a path boundary (`/a/b` is not inside `/a/bc`).
String? relativeSubpath(String directory, String root, String? homeDir) {
  final dir = canonicalPath(directory, homeDir);
  final base = canonicalPath(root, homeDir);
  if (dir == base) return '';
  final prefix = base == '/' ? '/' : '$base/';
  if (!dir.startsWith(prefix)) return null;
  return dir.substring(prefix.length);
}

/// [base] + [subpath], with no doubled or dangling slashes.
String joinSubpath(String base, String subpath) {
  var b = base;
  while (b.length > 1 && b.endsWith('/')) {
    b = b.substring(0, b.length - 1);
  }
  var s = subpath;
  while (s.startsWith('/')) {
    s = s.substring(1);
  }
  if (s.isEmpty) return b;
  return b == '/' ? '/$s' : '$b/$s';
}

/// The project a folder belongs to on a machine, with the linked root and the
/// folder's part below it.
class ProjectDirectoryMatch {
  const ProjectDirectoryMatch({
    required this.project,
    required this.root,
    required this.subpath,
  });

  /// The raw project map from `GET /api/v1/projects`.
  final Map<String, dynamic> project;

  /// The project's linked folder on this machine, as stored.
  final String root;

  /// [directory] below [root] (`''` when it is the root itself).
  final String subpath;

  String get projectId => project['id']?.toString() ?? '';
  String get projectName => project['name']?.toString() ?? '';
}

List<Map<String, dynamic>> _directoriesOf(dynamic project) {
  if (project is! Map) return const [];
  final raw = project['directories'];
  if (raw is! List) return const [];
  return raw.whereType<Map>().map((d) => Map<String, dynamic>.from(d)).toList();
}

/// The project [directory] belongs to on [machineId]: the project whose
/// linked folder on that machine is the longest prefix of [directory].
/// `null` when no project claims it — a freshly typed folder; the backend
/// mints a project for it on the first spawn.
ProjectDirectoryMatch? resolveProjectForDirectory(
  String directory,
  String? machineId,
  List<dynamic> projects,
  String? homeDir,
) {
  if (directory.trim().isEmpty || machineId == null || machineId.isEmpty) {
    return null;
  }
  ProjectDirectoryMatch? best;
  for (final project in projects) {
    if (project is! Map) continue;
    for (final link in _directoriesOf(project)) {
      if (link['machine_id']?.toString() != machineId) continue;
      final localPath = link['local_path']?.toString() ?? '';
      if (localPath.isEmpty) continue;
      final subpath = relativeSubpath(directory, localPath, homeDir);
      if (subpath == null) continue;
      if (best == null || localPath.length > best.root.length) {
        best = ProjectDirectoryMatch(
          project: Map<String, dynamic>.from(project),
          root: localPath,
          subpath: subpath,
        );
      }
    }
  }
  return best;
}

/// One picker row: a project linked to a folder on the selected machine.
class ProjectPickerEntry {
  const ProjectPickerEntry({required this.project, required this.path});
  final Map<String, dynamic> project;
  final String path;

  String get id => project['id']?.toString() ?? '';
  String get name => project['name']?.toString() ?? '';
}

/// The projects linked to a folder on [machineId], newest activity first
/// (the picker's list), each with that folder. Archived projects are left out.
List<ProjectPickerEntry> projectsOnMachine(
  List<dynamic> projects,
  String? machineId,
) {
  if (machineId == null || machineId.isEmpty) return const [];
  final rows = <ProjectPickerEntry>[];
  for (final project in projects) {
    if (project is! Map) continue;
    if (project['is_archived'] == true) continue;
    for (final link in _directoriesOf(project)) {
      if (link['machine_id']?.toString() != machineId) continue;
      final path = link['local_path']?.toString() ?? '';
      if (path.isEmpty) continue;
      rows.add(ProjectPickerEntry(
        project: Map<String, dynamic>.from(project),
        path: path,
      ));
      break;
    }
  }
  // The user's drag order first (`position`, from the sidebar), then newest
  // activity, then name — the same order the backend lists projects in.
  rows.sort((a, b) {
    final pa = a.project['position'];
    final pb = b.project['position'];
    if (pa is int && pb is int) return pa.compareTo(pb);
    if (pa is int) return -1;
    if (pb is int) return 1;
    final at = a.project['last_activity_at']?.toString() ?? '';
    final bt = b.project['last_activity_at']?.toString() ?? '';
    if (at != bt) return at.compareTo(bt) > 0 ? -1 : 1;
    return a.name.toLowerCase().compareTo(b.name.toLowerCase());
  });
  return rows;
}

/// Chip label for the picker: the project's name, with the subfolder when the
/// directory sits below the root (`vicoa · apps/web`); the folder's own name
/// when no project claims it yet.
String directoryChipLabel(String directory, ProjectDirectoryMatch? match) {
  if (directory.trim().isEmpty) return '';
  if (match == null) return pathBasename(directory.trim());
  return match.subpath.isEmpty
      ? match.projectName
      : '${match.projectName} · ${match.subpath}';
}
