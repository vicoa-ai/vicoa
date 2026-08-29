// New-session worktree selection state + the spawn-arg decision logic.
// See `plans/todos/vicoa-app-worktree.md` §5.3.

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
/// `newWorktree` keeps [baseDirectory] (the daemon forks off its HEAD) and asks
/// for creation; `existing` spawns directly in the selected worktree path with
/// no `worktree` param; `none` is today's plain spawn. An `existing` selection
/// with no path falls back to the base directory so a stale selection can never
/// produce an empty directory.
WorktreeSpawn resolveWorktreeSpawn({
  required WorktreeMode mode,
  required String baseDirectory,
  String? selectedWorktreePath,
}) {
  switch (mode) {
    case WorktreeMode.none:
      return (directory: baseDirectory, worktree: null);
    case WorktreeMode.newWorktree:
      return (directory: baseDirectory, worktree: {'new': true});
    case WorktreeMode.existing:
      return (
        directory: selectedWorktreePath ?? baseDirectory,
        worktree: null,
      );
  }
}

/// Session statuses that mean a session is still live. Mirrors the active set
/// used by the home session list; anything else (e.g. COMPLETED) is terminal.
const Set<String> kActiveSessionStatuses = {
  'ACTIVE',
  'AWAITING_INPUT',
  'REVIEWED',
};

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

/// Whether any session in [sessions] is still live AND running in
/// [worktreePath]. The daemon is a dumb executor with no session knowledge, so
/// the app must enforce "don't remove a worktree out from under a live session"
/// before calling `git-worktree-remove` (§5.5). [sessions] are raw agent
/// instance maps (`{'project': ..., 'status': ...}`); malformed entries are
/// ignored. [homeDir] (the machine's home) is required to match the absolute
/// git worktree path against the `~`-form session `project`; without it the
/// comparison falls back to exact string match.
bool worktreeHasActiveSession(String worktreePath, List<dynamic> sessions,
    {String? homeDir}) {
  final target = relativizeHome(worktreePath, homeDir);
  for (final s in sessions) {
    if (s is! Map) continue;
    final project = s['project'];
    final status = s['status'];
    if (project is! String || status is! String) continue;
    if (relativizeHome(project, homeDir) == target &&
        kActiveSessionStatuses.contains(status)) {
      return true;
    }
  }
  return false;
}
