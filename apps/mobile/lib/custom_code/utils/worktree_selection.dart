// New-session worktree selection state + the spawn-arg decision logic.
// See `plans/todos/vicoa-app-worktree.md` §5.3.

import '../../pages/home/session_status.dart';
import 'project_paths.dart';

/// How the new session relates to a git worktree:
///   - [none]        spawn in the chosen directory (today's behavior)
///   - [newWorktree] daemon forks a fresh branch+checkout off HEAD
///   - [existing]    spawn into an already-existing worktree
enum WorktreeMode { none, newWorktree, existing }

/// The resolved spawn-session inputs for a worktree selection: the directory to
/// run in, and the optional `worktree` RPC param.
typedef WorktreeSpawn = ({String directory, Map<String, dynamic>? worktree});

/// Map a [WorktreeMode] selection onto spawn-session args.
///
/// [baseDirectory] is the folder the user picked — the repo root or a
/// subfolder of it (a monorepo session at `repo/apps/web`); [subpath] is that
/// folder's part below the root (`''` at the root). `newWorktree` sends the
/// folder as-is (the daemon forks the whole repo off its HEAD and starts the
/// agent at the same subfolder inside the new checkout); `existing` starts at
/// the selected worktree — at the same subfolder inside it, so the checkout
/// and the folder stay orthogonal; `none` is today's plain spawn. An
/// `existing` selection with no path falls back to the base directory so a
/// stale selection can never produce an empty directory.
WorktreeSpawn resolveWorktreeSpawn({
  required WorktreeMode mode,
  required String baseDirectory,
  String subpath = '',
  String? selectedWorktreePath,
}) {
  switch (mode) {
    case WorktreeMode.none:
      return (directory: baseDirectory, worktree: null);
    case WorktreeMode.newWorktree:
      return (directory: baseDirectory, worktree: {'new': true});
    case WorktreeMode.existing:
      return (
        directory: selectedWorktreePath == null
            ? baseDirectory
            : joinSubpath(selectedWorktreePath, subpath),
        worktree: null,
      );
  }
}

/// Whether [path] looks like a vicoa-managed worktree (under
/// `~/vicoa/workspaces/`). A heuristic used only to decide whether to OFFER
/// cleanup — the daemon is the real authority and re-validates on remove.
bool isManagedWorktreePath(String path) =>
    path.contains('/vicoa/workspaces/');

/// Collapse an absolute home-dir path to `~` form (e.g. `/Users/dev/x` →
/// `~/x`). The daemon expands paths when it runs git, so `git worktree list`
/// returns absolute paths, while the CLI records a session's `project`
/// home-collapsed (`~/...`). Normalizing to the same `~` form lets the two line
/// up for comparison AND gives a tidier path to display. Returns [path]
/// unchanged (trailing slash trimmed) when [homeDir] is null/empty or doesn't
/// prefix it (already-relative or non-home paths).
String relativizeHome(String path, String? homeDir) {
  var p = path.trim();
  while (p.length > 1 && p.endsWith('/')) {
    p = p.substring(0, p.length - 1);
  }
  if (homeDir == null || homeDir.isEmpty) return p;
  var h = homeDir.trim();
  while (h.length > 1 && h.endsWith('/')) {
    h = h.substring(0, h.length - 1);
  }
  if (p == h) return '~';
  if (p.startsWith('$h/')) return '~${p.substring(h.length)}';
  return p;
}

/// The sessions in [sessions] that are still live (not closed, the same set as
/// the web's `CLOSED_STATUSES`) AND running in [worktreePath], at its root or
/// in a folder inside it. The daemon is a dumb executor with no session
/// knowledge, so the app must find these before calling `git-worktree-remove`
/// (§5.5) and archive them rather than pull the folder out from under them.
/// [sessions] are raw agent instance maps (`{'project': ..., 'status': ...}`);
/// malformed entries are ignored. [homeDir] (the machine's home) is required
/// to match the absolute git worktree path against the `~`-form session
/// `project`; without it the comparison falls back to exact string match.
Iterable<Map> _liveSessionsIn(String worktreePath, List<dynamic> sessions,
    {String? homeDir}) sync* {
  final target = relativizeHome(worktreePath, homeDir);
  for (final s in sessions) {
    if (s is! Map) continue;
    final project = s['project'];
    final status = s['status'];
    if (project is! String || status is! String || isClosedStatus(status)) {
      continue;
    }
    final p = relativizeHome(project, homeDir);
    if (p == target || p.startsWith('$target/')) yield s;
  }
}

/// Whether any live session runs in [worktreePath]; see [_liveSessionsIn].
bool worktreeHasActiveSession(String worktreePath, List<dynamic> sessions,
        {String? homeDir}) =>
    _liveSessionsIn(worktreePath, sessions, homeDir: homeDir).isNotEmpty;

/// The ids of the live sessions in [worktreePath], the ones a worktree removal
/// archives first; see [_liveSessionsIn].
List<String> worktreeActiveSessionIds(String worktreePath, List<dynamic> sessions,
        {String? homeDir}) =>
    _liveSessionsIn(worktreePath, sessions, homeDir: homeDir)
        .map((s) => s['id'])
        .whereType<String>()
        .toList();
