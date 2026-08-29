// State machine backing the Git tab.
// See `plans/todos/vicoa-app-git-tab.md` §Phase C State / Render / Refresh.
//
// Pure ChangeNotifier — `gitStatus`, `gitDiff`, and `cache` are injected so
// the model is unit-testable without a live WebSocket or Hive box.

import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';

import 'rpc_git.dart';

typedef GitStatusFn = Future<GitStatusResult> Function({
  required String machineId,
  required String cwd,
});

typedef GitDiffFn = Future<GitDiffResult> Function({
  required String machineId,
  required String cwd,
  required String path,
  required bool staged,
  required bool ignoreWhitespace,
});

abstract class GitTabCache {
  Map<String, dynamic>? getDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
  });
  Future<void> putDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
    required Map<String, dynamic> payload,
  });
  Map<String, dynamic>? getLastStatus({
    required String machineId,
    required String cwd,
  });
  Future<void> putLastStatus({
    required String machineId,
    required String cwd,
    required Map<String, dynamic> payload,
  });
  // Persisted set of `_diffKey` strings — the files the user has explicitly
  // opened in the Git tab. Defaults to empty, i.e. every file collapsed.
  Set<String> getExpandedPaths({
    required String machineId,
    required String cwd,
  });
  Future<void> putExpandedPaths({
    required String machineId,
    required String cwd,
    required Set<String> paths,
  });
  // Toolbar toggle preferences (wrapLines, hideWhitespace). Stored globally
  // for the user — these are general reading preferences, not per-repo.
  GitTabPrefs? getGitTabPrefs();
  Future<void> putGitTabPrefs(GitTabPrefs prefs);
}

class GitTabPrefs {
  const GitTabPrefs({required this.wrapLines, required this.hideWhitespace});
  final bool wrapLines;
  final bool hideWhitespace;
}

/// Per-file diff slot. Mutable so the UI can subscribe to the GitTabModel
/// and rebuild as individual diffs land or error.
class DiffEntry {
  DiffEntry({this.payload, this.error, this.loading = true});
  GitDiffResult? payload;
  String? error;
  bool loading;
}

class GitTabModel extends ChangeNotifier {
  GitTabModel({
    required this.machineId,
    required this.cwd,
    required this.cache,
    required this.gitStatus,
    required this.gitDiff,
    this.maxInFlightDiffs = 6,
  });

  final String machineId;
  final String cwd;
  final GitTabCache cache;
  final GitStatusFn gitStatus;
  final GitDiffFn gitDiff;
  final int maxInFlightDiffs;

  GitStatusResult? _status;
  GitStatusResult? get status => _status;

  String? _statusError;
  String? get statusError => _statusError;

  bool _offline = false;
  bool get offline => _offline;

  // Diff state keyed by '$path|${staged ? 's' : 'u'}'.
  final Map<String, DiffEntry> _diffs = {};

  // Files the user has explicitly opened. Default empty → every file is
  // collapsed (paseo's model: headers are a TOC, tap to open). Hydrated from
  // `cache.getExpandedPaths` on `activate()` and persisted on every change.
  final Set<String> _expanded = <String>{};

  // Files whose body is showing the full diff. By default every body is
  // truncated to a short preview (see `_previewRowsFromSettings` in
  // git_tab_view.dart) so users can scan large files quickly; tap "show
  // more" on a file to add it to this set.
  final Set<String> _bodyFullyShown = <String>{};

  bool _wrapLines = true;
  bool _hideWhitespace = false;

  bool get wrapLines => _wrapLines;
  bool get hideWhitespace => _hideWhitespace;

  /// True when no file is currently expanded — drives the strip toolbar's
  /// "Expand all" vs "Collapse all" affordance.
  bool get allCollapsed => _expanded.isEmpty;

  // RPC error codes that mean "couldn't reach the daemon" rather than a real
  // per-path failure. Flips the offline banner, keeps cached status visible.
  static const Set<String> _connectivityCodes = {
    'not_connected',
    'target_disconnected',
    'timeout',
    'no_handler',
  };

  // ---------------------------------------------------------------- accessors

  DiffEntry? diffFor(String path, {required bool staged}) =>
      _diffs[_diffKey(path, staged)];

  bool isCollapsed(String path, {required bool staged}) =>
      !_expanded.contains(_diffKey(path, staged));

  bool isBodyFullyShown(String path, {required bool staged}) =>
      _bodyFullyShown.contains(_diffKey(path, staged));

  void showFullBody(String path, {required bool staged}) {
    final key = _diffKey(path, staged);
    if (_bodyFullyShown.add(key)) notifyListeners();
  }

  // ---------------------------------------------------------------- lifecycle

  /// First Git-tab activation. Loads cached last-status (if any) for instant
  /// paint, then fires `git-status` and pulls diffs for every file.
  Future<void> activate() async {
    // Restore the per-(machineId, cwd) expanded set so reopening the same
    // repo on the same machine keeps the user's chosen file selection.
    _expanded.addAll(cache.getExpandedPaths(machineId: machineId, cwd: cwd));
    // Restore global toolbar prefs (wrap / hide-whitespace) so the user's
    // choice survives across launches and across repos.
    final prefs = cache.getGitTabPrefs();
    if (prefs != null) {
      _wrapLines = prefs.wrapLines;
      _hideWhitespace = prefs.hideWhitespace;
    }
    final cached = cache.getLastStatus(machineId: machineId, cwd: cwd);
    if (cached != null) {
      try {
        _status = GitStatusResult.fromJson(cached);
        notifyListeners();
      } catch (_) {
        // Malformed cache — ignore and proceed with live fetch.
      }
    }
    await _fetchStatusAndDiffs(isRefresh: false);
  }

  /// Re-fetch status + only re-fetch diffs for files whose content_hash
  /// changed. Backs pull-to-refresh, the toolbar refresh icon, app-resume,
  /// and WS reconnect.
  Future<void> refresh() => _fetchStatusAndDiffs(isRefresh: true);

  /// Flip hide-whitespace. Every diff's cache key changes, so every
  /// currently-visible diff is invalidated and re-fetched.
  Future<void> toggleHideWhitespace() async {
    _hideWhitespace = !_hideWhitespace;
    _diffs.clear();
    _persistPrefs();
    notifyListeners();
    if (_status != null) {
      await _loadDiffsForStatus(_status!, force: true);
    }
  }

  void toggleWrapLines() {
    _wrapLines = !_wrapLines;
    _persistPrefs();
    notifyListeners();
  }

  void _persistPrefs() {
    unawaited(cache.putGitTabPrefs(
      GitTabPrefs(wrapLines: _wrapLines, hideWhitespace: _hideWhitespace),
    ));
  }

  /// If anything is currently expanded, collapse everything; otherwise expand
  /// every file in the current status. Mirrors paseo's all-or-nothing
  /// behaviour (diff-pane.tsx `handleToggleExpandAll`).
  void toggleExpandAll() {
    final status = _status;
    if (_expanded.isNotEmpty) {
      _expanded.clear();
    } else if (status != null) {
      for (final e in status.staged) {
        _expanded.add(_diffKey(e.path, true));
      }
      for (final e in status.unstaged) {
        _expanded.add(_diffKey(e.path, false));
      }
      for (final e in status.untracked) {
        _expanded.add(_diffKey(e.path, false));
      }
    }
    _persistExpandedPaths();
    notifyListeners();
  }

  void toggleFile(String path, {required bool staged}) {
    final key = _diffKey(path, staged);
    if (_expanded.contains(key)) {
      _expanded.remove(key);
    } else {
      _expanded.add(key);
    }
    _persistExpandedPaths();
    notifyListeners();
  }

  void _persistExpandedPaths() {
    unawaited(cache.putExpandedPaths(
      machineId: machineId,
      cwd: cwd,
      paths: Set<String>.from(_expanded),
    ));
  }

  // ----------------------------------------------------------------- internals

  Future<void> _fetchStatusAndDiffs({required bool isRefresh}) async {
    final GitStatusResult newStatus;
    try {
      newStatus = await gitStatus(machineId: machineId, cwd: cwd);
    } on GitOpsException catch (exc) {
      if (_connectivityCodes.contains(exc.code)) {
        _offline = true;
      } else {
        _statusError = exc.code;
        _status = null;
      }
      notifyListeners();
      return;
    } catch (_) {
      _offline = true;
      notifyListeners();
      return;
    }

    _offline = false;
    _statusError = null;

    if (isRefresh) {
      _purgeStaleDiffs(newStatus);
    }
    _status = newStatus;
    // Persist for offline-fallback rendering on the next activate.
    unawaited(cache.putLastStatus(
      machineId: machineId,
      cwd: cwd,
      payload: _statusToJson(newStatus),
    ));
    notifyListeners();

    await _loadDiffsForStatus(newStatus, force: false);
  }

  /// Drop diff entries for files no longer in [next] status (e.g. user reverted
  /// a change). Files whose content_hash matches the cached entry are left
  /// alone; mismatches will be re-fetched by `_loadDiffsForStatus`.
  void _purgeStaleDiffs(GitStatusResult next) {
    final liveKeys = <String>{};
    for (final e in next.staged) {
      liveKeys.add(_diffKey(e.path, true));
    }
    for (final e in next.unstaged) {
      liveKeys.add(_diffKey(e.path, false));
    }
    for (final e in next.untracked) {
      liveKeys.add(_diffKey(e.path, false));
    }
    _diffs.removeWhere((k, _) => !liveKeys.contains(k));
  }

  Future<void> _loadDiffsForStatus(
    GitStatusResult status, {
    required bool force,
  }) async {
    final tasks = <_DiffTask>[];
    for (final e in status.staged) {
      tasks.add(_DiffTask(entry: e, staged: true));
    }
    for (final e in status.unstaged) {
      tasks.add(_DiffTask(entry: e, staged: false));
    }
    for (final e in status.untracked) {
      tasks.add(_DiffTask(entry: e, staged: false));
    }

    final queue = Queue<_DiffTask>();
    for (final t in tasks) {
      final key = _diffKey(t.entry.path, t.staged);
      final hash = t.entry.contentHash;
      if (!force && hash != null) {
        final cached = cache.getDiff(
          machineId: machineId,
          cwd: cwd,
          path: t.entry.path,
          contentHash: hash,
          staged: t.staged,
          ignoreWhitespace: _hideWhitespace,
        );
        if (cached != null) {
          _diffs[key] = DiffEntry(
            payload: GitDiffResult.fromJson(cached),
            loading: false,
          );
          continue;
        }
      }
      _diffs[key] = DiffEntry(loading: true);
      queue.add(t);
    }

    notifyListeners();
    await _drainDiffQueue(queue);
  }

  Future<void> _drainDiffQueue(Queue<_DiffTask> queue) async {
    final inFlight = <Future<void>>[];

    Future<void> runOne(_DiffTask task) async {
      final key = _diffKey(task.entry.path, task.staged);
      try {
        final result = await gitDiff(
          machineId: machineId,
          cwd: cwd,
          path: task.entry.path,
          staged: task.staged,
          ignoreWhitespace: _hideWhitespace,
        );
        _diffs[key] = DiffEntry(payload: result, loading: false);
        final hash = task.entry.contentHash;
        if (hash != null) {
          unawaited(cache.putDiff(
            machineId: machineId,
            cwd: cwd,
            path: task.entry.path,
            contentHash: hash,
            staged: task.staged,
            ignoreWhitespace: _hideWhitespace,
            payload: _diffToJson(result),
          ));
        }
      } on GitOpsException catch (exc) {
        if (_connectivityCodes.contains(exc.code)) {
          _offline = true;
        }
        _diffs[key] = DiffEntry(error: exc.code, loading: false);
      } catch (_) {
        _diffs[key] = DiffEntry(error: 'not_connected', loading: false);
        _offline = true;
      }
      notifyListeners();
    }

    while (queue.isNotEmpty || inFlight.isNotEmpty) {
      while (inFlight.length < maxInFlightDiffs && queue.isNotEmpty) {
        final task = queue.removeFirst();
        late Future<void> fut;
        fut = runOne(task).whenComplete(() => inFlight.remove(fut));
        inFlight.add(fut);
      }
      if (inFlight.isEmpty) break;
      await Future.any(inFlight);
    }
  }

  String _diffKey(String path, bool staged) =>
      '$path|${staged ? 's' : 'u'}';

  Map<String, dynamic> _statusToJson(GitStatusResult s) => {
        'branch': s.branch,
        'ahead': s.ahead,
        'behind': s.behind,
        if (s.upstream != null) 'upstream': s.upstream,
        if (s.detachedHead) 'detached_head': true,
        'staged': s.staged.map(_fileToJson).toList(),
        'unstaged': s.unstaged.map(_fileToJson).toList(),
        'untracked': s.untracked.map(_fileToJson).toList(),
      };

  Map<String, dynamic> _fileToJson(GitFileEntry e) => {
        'path': e.path,
        'status': e.status,
        'additions': e.additions,
        'deletions': e.deletions,
        'content_hash': e.contentHash,
        if (e.oldPath != null) 'old_path': e.oldPath,
      };

  Map<String, dynamic> _diffToJson(GitDiffResult d) => {
        'path': d.path,
        'hunks': d.hunks
            .map(
              (h) => {
                'header': h.header,
                'old_start': h.oldStart,
                'old_count': h.oldCount,
                'new_start': h.newStart,
                'new_count': h.newCount,
                'lines': h.lines
                    .map((l) => {'type': l.type, 'content': l.content})
                    .toList(),
              },
            )
            .toList(),
        'is_binary': d.isBinary,
        'truncated': d.truncated,
        'size': d.size,
      };
}

class _DiffTask {
  _DiffTask({required this.entry, required this.staged});
  final GitFileEntry entry;
  final bool staged;
}
