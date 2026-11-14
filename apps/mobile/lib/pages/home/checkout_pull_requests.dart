// Resolves the pull request behind each git session on the home page, so the
// branch icon on its card can take the PR's state color (green open, purple
// merged, red closed, grey draft), as the desktop sidebar's branch rows do.
//
// Two daemon RPCs per repo: `git-worktree-list` (local git: which repo a
// session's folder belongs to, and each checkout's branch, upstream and head
// commit) and `github-pr-list` (one `gh pr list` for the whole repo, through
// the shared cache in `rpc_github.dart`). A PR is matched to a checkout with
// `prForCheckout`. Results are kept in memory and, via [persist], across
// launches, so cards paint with their last-known colors on the first frame.
//
// When it asks, mirroring the desktop sidebar:
// - on every list refresh (open, resume, reconnect, pull), reusing an answer
//   younger than `kPrCacheTtl`, so flicking the app in and out spends nothing;
// - for one repo when one of its sessions ends a turn, which is when an agent
//   has typically just run `gh pr create` or `gh pr merge`
//   ([requestTurnRefresh], at most every [turnRefreshMinInterval] per repo);
// - on a slow poll while Home is on screen ([poll]), for repos with a linked
//   worktree, whose rows can gain a PR or see it merged on github.com with
//   nothing in the app announcing it.

import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';

import '/custom_code/actions/rpc_git.dart';
import '/custom_code/actions/rpc_github.dart';
import '/custom_code/utils/pr_status.dart';

/// One session folder to decorate: its machine + cwd.
typedef PrProbeTarget = ({String machineId, String path});

String _normalizePath(String path) {
  var p = path.trim();
  while (p.length > 1 && p.endsWith('/')) {
    p = p.substring(0, p.length - 1);
  }
  return p;
}

String _cwdKey(String machineId, String path) => '$machineId|${_normalizePath(path)}';

/// What a checkout has out, as far as matching a PR goes. A null [branch]
/// means the daemon didn't say (one that predates `main_branch`); the card's
/// own branch label stands in.
@immutable
class _CheckoutRef {
  const _CheckoutRef({this.branch, this.upstream = '', this.head = ''});
  final String? branch;
  final String upstream;
  final String head;

  static _CheckoutRef fromJson(Map json) => _CheckoutRef(
        branch: json['b'] as String?,
        upstream: json['u'] as String? ?? '',
        head: json['h'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {
        if (branch != null) 'b': branch,
        if (upstream.isNotEmpty) 'u': upstream,
        if (head.isNotEmpty) 'h': head,
      };

  @override
  bool operator ==(Object other) =>
      other is _CheckoutRef &&
      other.branch == branch &&
      other.upstream == upstream &&
      other.head == head;

  @override
  int get hashCode => Object.hash(branch, upstream, head);
}

class _RepoView {
  _RepoView(this.machineId, this.repoPath);
  final String machineId;

  /// The main checkout's path, the cwd both RPCs run from.
  final String repoPath;

  /// Every checkout of the repo by path, in both the absolute and the `~/…`
  /// form, since a session's `project` may be either.
  Map<String, _CheckoutRef> checkouts = const {};

  /// Git lists a linked worktree the user works in: the repo is worth polling.
  bool hasLiveWorktrees = false;
  Map<String, PrInfo> prs = const {};

  /// When the request behind [prs] went out (null = never this run): a slow
  /// answer that lands after a newer one must not overwrite it.
  DateTime? prsRequestedAt;

  /// The checkout [cwd] is in: its own entry, else the deepest checkout it
  /// sits inside (a session started in a subfolder).
  _CheckoutRef? refFor(String cwd) {
    final p = _normalizePath(cwd);
    final exact = checkouts[p];
    if (exact != null) return exact;
    String? best;
    for (final k in checkouts.keys) {
      if (p.startsWith(k == '/' ? k : '$k/') && (best == null || k.length > best.length)) {
        best = k;
      }
    }
    return best == null ? null : checkouts[best];
  }

  PrInfo? prFor(String cwd, String? fallbackBranch) {
    final ref = refFor(cwd);
    return prForCheckout(
      prs,
      branch: ref?.branch ?? fallbackBranch ?? '',
      upstream: ref?.upstream,
      head: ref?.head,
    );
  }

  Map<String, dynamic> toJson() {
    // Only the PRs some checkout resolves to: they are all a first frame
    // needs, and a repo can have a hundred.
    final kept = <String, PrInfo>{};
    final winners = <PrInfo>{
      for (final ref in checkouts.values)
        if (prForCheckout(prs, branch: ref.branch ?? '', upstream: ref.upstream, head: ref.head)
            case final pr?)
          pr,
    };
    for (final e in prs.entries) {
      if (winners.contains(e.value)) kept[e.key] = e.value;
    }
    return {
      'm': machineId,
      'p': repoPath,
      if (hasLiveWorktrees) 'w': true,
      'c': {for (final e in checkouts.entries) e.key: e.value.toJson()},
      'r': {for (final e in kept.entries) e.key: e.value.toJson()},
    };
  }

  static _RepoView? fromJson(Object? json) {
    if (json is! Map) return null;
    final machineId = json['m'];
    final repoPath = json['p'];
    if (machineId is! String || repoPath is! String) return null;
    final view = _RepoView(machineId, repoPath)..hasLiveWorktrees = json['w'] == true;
    final c = json['c'];
    if (c is Map) {
      view.checkouts = {
        for (final e in c.entries)
          if (e.value is Map) e.key.toString(): _CheckoutRef.fromJson(e.value as Map),
      };
    }
    final r = json['r'];
    if (r is Map) {
      view.prs = {
        for (final e in r.entries)
          if (e.value is Map)
            if (PrInfo.fromJson(Map<String, dynamic>.from(e.value as Map)) case final pr?)
              e.key.toString(): pr,
      };
    }
    return view;
  }
}

class _TurnRefresh {
  _TurnRefresh(this.since);

  /// When the latest turn this refresh covers ended.
  DateTime since;
  Timer? timer;
}

class CheckoutPullRequests {
  CheckoutPullRequests({
    required RpcCaller call,
    required VoidCallback onChanged,
    Map<String, dynamic> seed = const {},
    void Function(Map<String, dynamic> state)? persist,
  })  : _call = call,
        _onChanged = onChanged,
        _persist = persist {
    _restore(seed);
  }

  /// Bounds on the persisted cache; the oldest-touched entries fall off first.
  static const int maxRepos = 50;
  static const int maxFolders = 200;

  /// Floor between two turn-end refreshes of one repo: a burst of agents
  /// finishing collapses into one trailing refresh.
  static const Duration turnRefreshMinInterval = Duration(seconds: 30);

  final RpcCaller _call;
  final VoidCallback _onChanged;
  final void Function(Map<String, dynamic> state)? _persist;

  // repo key → view; session folder key → repo key.
  final LinkedHashMap<String, _RepoView> _repos = LinkedHashMap();
  final LinkedHashMap<String, String> _folderRepo = LinkedHashMap();
  final Set<String> _discovering = {};
  final Map<String, _TurnRefresh> _turnRefreshes = {};
  bool _disposed = false;

  /// The PR of the checkout [path] on [machineId] is in, or null when it has
  /// none or it is not known yet. [branch] is the card's own branch label,
  /// used when the daemon can't say what the checkout has out.
  PrInfo? prFor(String machineId, String path, {String? branch}) {
    final repo = _repos[_folderRepo[_cwdKey(machineId, path)]];
    return repo?.prFor(path, branch);
  }

  /// Re-read the repos behind [targets]. A folder never seen is first resolved
  /// to its repo; with [onlyUnknown] that is all that happens, for paths that
  /// merely *add* sessions (pagination, a spawn, a filter change) and
  /// shouldn't re-ask every repo. A PR answer younger than [maxAge] is reused.
  Future<void> refresh(
    Iterable<PrProbeTarget> targets, {
    bool onlyUnknown = false,
    Duration maxAge = kPrCacheTtl,
  }) {
    final repos = <String, _RepoView>{};
    final unknown = <String, PrProbeTarget>{};
    for (final t in targets) {
      final key = _cwdKey(t.machineId, t.path);
      final repoKey = _folderRepo[key];
      final repo = repoKey == null ? null : _repos[repoKey];
      if (repo == null) {
        unknown[key] = t;
      } else if (!onlyUnknown) {
        repos[repoKey!] = repo;
      }
    }
    return Future.wait([
      for (final e in unknown.entries) _discover(e.key, e.value, maxAge),
      for (final repo in repos.values) _refreshRepo(repo, maxAge),
    ]);
  }

  /// A session in [target] ended a turn: re-read its repo, at most every
  /// [turnRefreshMinInterval]. Reuses a PR answer only if it was requested
  /// after the latest turn ended; an earlier one may predate the PR that turn
  /// opened or merged.
  void requestTurnRefresh(PrProbeTarget target) {
    if (_disposed) return;
    final repoKey = _folderRepo[_cwdKey(target.machineId, target.path)];
    final repo = repoKey == null ? null : _repos[repoKey];
    if (repo == null) {
      unawaited(refresh([target]));
      return;
    }
    final now = DateTime.now();
    final queued = _turnRefreshes[repoKey];
    if (queued != null) {
      queued.since = now;
      return;
    }
    final last = githubPrListRequestedAt(repo.machineId, repo.repoPath);
    var delay = Duration.zero;
    if (last != null) {
      final wait = last.add(turnRefreshMinInterval).difference(now);
      if (wait > Duration.zero) delay = wait;
    }
    final entry = _TurnRefresh(now);
    entry.timer = Timer(delay, () {
      _turnRefreshes.remove(repoKey);
      if (_disposed) return;
      unawaited(_refreshRepo(repo, DateTime.now().difference(entry.since)));
    });
    _turnRefreshes[repoKey!] = entry;
  }

  /// The slow-poll tick: re-read the repos behind [targets] that have a linked
  /// worktree. A repo with only its main checkout is left to the other
  /// triggers, since its branch rarely gains a PR without an agent turn.
  Future<void> poll(Iterable<PrProbeTarget> targets) {
    final repos = <String, _RepoView>{};
    for (final t in targets) {
      final repoKey = _folderRepo[_cwdKey(t.machineId, t.path)];
      final repo = repoKey == null ? null : _repos[repoKey];
      if (repo != null && repo.hasLiveWorktrees) repos[repoKey!] = repo;
    }
    return Future.wait([for (final repo in repos.values) _refreshRepo(repo, kPrCacheTtl)]);
  }

  void dispose() {
    _disposed = true;
    for (final t in _turnRefreshes.values) {
      t.timer?.cancel();
    }
    _turnRefreshes.clear();
  }

  Future<void> _discover(String folderKey, PrProbeTarget target, Duration maxAge) async {
    if (!_discovering.add(folderKey)) return;
    try {
      final listing = await rpcGitWorktreeListing(
        call: _call,
        machineId: target.machineId,
        cwd: target.path,
      );
      if (_disposed) return;
      final repoPath = listing.mainDisplayPath ?? listing.mainPath ?? target.path;
      final repoKey = prRepoKey(target.machineId, repoPath);
      final repo = _repos[repoKey] ?? _RepoView(target.machineId, repoPath);
      _touchRepo(repoKey, repo);
      _folderRepo.remove(folderKey);
      _folderRepo[folderKey] = repoKey;
      _applyListing(repo, listing);
      _changed();
      await _refreshPrs(repo, maxAge);
    } on GitOpsException {
      // Not a repo (or gone): nothing to decorate.
    } catch (_) {
      // Machine unreachable: try again on the next refresh.
    } finally {
      _discovering.remove(folderKey);
    }
  }

  Future<void> _refreshRepo(_RepoView repo, Duration maxAge) => Future.wait([
        _refreshListing(repo),
        _refreshPrs(repo, maxAge),
      ]);

  Future<void> _refreshListing(_RepoView repo) async {
    try {
      final listing = await rpcGitWorktreeListing(
        call: _call,
        machineId: repo.machineId,
        cwd: repo.repoPath,
      );
      if (_disposed) return;
      if (_applyListing(repo, listing)) _changed();
    } catch (_) {
      // Keep the last-known checkouts: a transient failure is not a change.
    }
  }

  /// Whether anything a card shows changed.
  bool _applyListing(_RepoView repo, WorktreeListing listing) {
    final checkouts = <String, _CheckoutRef>{};
    void put(String? path, _CheckoutRef ref) {
      if (path != null && path.isNotEmpty) checkouts[_normalizePath(path)] = ref;
    }

    final main = _CheckoutRef(branch: listing.mainBranch);
    put(listing.mainPath, main);
    put(listing.mainDisplayPath, main);
    for (final w in listing.worktrees) {
      if (w.prunable) continue;
      final ref = _CheckoutRef(branch: w.branch, upstream: w.upstream, head: w.head);
      put(w.path, ref);
      put(w.displayPath, ref);
    }
    final live = listing.worktrees.any((w) => !w.prunable && !isAgentScratchWorktree(w.path));
    final changed = !mapEquals(checkouts, repo.checkouts) || live != repo.hasLiveWorktrees;
    repo.checkouts = checkouts;
    repo.hasLiveWorktrees = live;
    return changed;
  }

  Future<void> _refreshPrs(_RepoView repo, Duration maxAge) async {
    try {
      final snapshot = await rpcGithubPrListCached(
        call: _call,
        machineId: repo.machineId,
        repoPath: repo.repoPath,
        maxAge: maxAge,
      );
      if (_disposed) return;
      final shown = repo.prsRequestedAt;
      if (shown != null && shown.isAfter(snapshot.requestedAt)) return;
      repo.prsRequestedAt = snapshot.requestedAt;
      if (mapEquals(snapshot.prs, repo.prs)) return;
      repo.prs = snapshot.prs;
      _changed();
    } catch (_) {
      // A transient `gh` failure or an unreachable machine keeps the colors on
      // screen rather than greying every icon out.
    }
  }

  void _touchRepo(String repoKey, _RepoView repo) {
    _repos.remove(repoKey);
    _repos[repoKey] = repo;
    while (_repos.length > maxRepos) {
      _repos.remove(_repos.keys.first);
    }
  }

  void _restore(Map<String, dynamic> seed) {
    final repos = seed['repos'];
    if (repos is Map) {
      for (final e in repos.entries) {
        final view = _RepoView.fromJson(e.value);
        if (view != null) _repos[e.key.toString()] = view;
      }
    }
    final folders = seed['folders'];
    if (folders is Map) {
      for (final e in folders.entries) {
        final repoKey = e.value;
        if (repoKey is String && _repos.containsKey(repoKey)) {
          _folderRepo[e.key.toString()] = repoKey;
        }
      }
    }
  }

  void _changed() {
    if (_disposed) return;
    while (_folderRepo.length > maxFolders) {
      _folderRepo.remove(_folderRepo.keys.first);
    }
    _folderRepo.removeWhere((_, repoKey) => !_repos.containsKey(repoKey));
    _persist?.call({
      'repos': {for (final e in _repos.entries) e.key: e.value.toJson()},
      'folders': Map.of(_folderRepo),
    });
    _onChanged();
  }
}
