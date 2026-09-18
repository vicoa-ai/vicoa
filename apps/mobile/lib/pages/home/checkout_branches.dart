// Resolves the current git branch of the checkouts the home page's sessions
// run in, over the daemon's `git-status` RPC, for the session card's second
// line. A worktree session carries its branch as `worktree_name`; a session
// in a repo's MAIN checkout carries nothing (the backend never learns it, and
// it can change under a long-lived checkout), so it is read live — the same
// way the desktop sidebar labels its "main" row. Results are cached in memory
// and, via [persist], across launches, so cards paint with their last-known
// branch on the first frame and only relabel if the branch moved.

import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';

import '/custom_code/actions/rpc_git.dart';

/// One checkout to read the branch of: a session's machine + cwd.
typedef BranchProbeTarget = ({String machineId, String path});

/// Folder-path identity: trailing slashes never make two paths differ.
String _normalizePath(String path) {
  var p = path.trim();
  while (p.length > 1 && p.endsWith('/')) {
    p = p.substring(0, p.length - 1);
  }
  return p;
}

String branchCacheKey(String machineId, String path) =>
    '$machineId|${_normalizePath(path)}';

class CheckoutBranchResolver {
  CheckoutBranchResolver({
    required RpcCaller call,
    required VoidCallback onChanged,
    Map<String, String> seed = const {},
    void Function(Map<String, String> branches)? persist,
  })  : _call = call,
        _onChanged = onChanged,
        _persist = persist,
        _branches = LinkedHashMap.of(seed);

  /// Bound on the persisted cache; the oldest-touched entries fall off first.
  static const int maxEntries = 200;

  final RpcCaller _call;
  final VoidCallback _onChanged;
  final void Function(Map<String, String> branches)? _persist;
  // key → branch; `''` means a detached HEAD (known, just nameless).
  final LinkedHashMap<String, String> _branches;
  final Set<String> _inFlight = {};

  /// Last-known branch of the checkout at [path] on [machineId]; `null` when
  /// never resolved, or the folder turned out not to be a repo.
  String? branchFor(String machineId, String path) =>
      _branches[branchCacheKey(machineId, path)];

  /// Re-read the branch of every target. Each result notifies as it lands so
  /// one slow machine never holds the others back; a target already in
  /// flight is not asked twice. With [onlyUnknown], targets that already have
  /// a cached branch are skipped — for paths that merely *add* sessions
  /// (pagination, a WS spawn, a filter change) and shouldn't fan out to every
  /// checkout again.
  Future<void> refresh(
    Iterable<BranchProbeTarget> targets, {
    bool onlyUnknown = false,
  }) =>
      Future.wait([
        for (final t in targets)
          if (!onlyUnknown || !_branches.containsKey(branchCacheKey(t.machineId, t.path)))
            _probe(t),
      ]);

  Future<void> _probe(BranchProbeTarget target) async {
    final key = branchCacheKey(target.machineId, target.path);
    if (!_inFlight.add(key)) return;
    try {
      final status = await rpcGitStatus(
        call: _call,
        machineId: target.machineId,
        cwd: target.path,
      );
      _store(key, status.detachedHead ? '' : status.branch);
    } on GitOpsException {
      // The daemon looked and there is nothing to label — a plain folder
      // (`not_a_repo`) or a cwd that is gone (`path_not_found`). Forget any
      // branch cached from when it was one.
      if (_branches.remove(key) != null) _changed();
    } catch (_) {
      // Transport failure (machine offline, timeout, WS down): the checkout is
      // still whatever it was, so keep the last-known label.
    } finally {
      _inFlight.remove(key);
    }
  }

  void _store(String key, String branch) {
    final unchanged = _branches.containsKey(key) && _branches[key] == branch;
    // Re-insert so the entry moves to the end (most recently touched).
    _branches.remove(key);
    _branches[key] = branch;
    while (_branches.length > maxEntries) {
      _branches.remove(_branches.keys.first);
    }
    if (!unchanged) _changed();
  }

  void _changed() {
    _persist?.call(Map.of(_branches));
    _onChanged();
  }
}
