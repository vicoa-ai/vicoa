// Typed wrapper around `ws_client.callRpc('github-pr-list', ...)`, plus the
// shared cache every screen reads it through. The mobile twin of the web's
// `rpcGithubPrList` / `rpcGithubPrListCached` (files-git-panel/rpc.ts).
//
// The daemon answers this by running `gh pr list` on the user's machine, so
// each call spends a GitHub API request from a quota the agent's own `gh`
// calls share. One call covers a whole repository; callers join it locally
// against branches they already know rather than asking per branch.

import 'package:flutter/foundation.dart';

import 'rpc_git.dart' show GitOpsException, RpcCaller;

/// `open` / `draft` / `merged` / `closed`. A draft is its own state rather
/// than a flag on `open`: it is not yet a claim that the work is ready.
enum PrState { open, draft, merged, closed }

/// Rollup of the PR's status checks.
enum PrChecks { pass, fail, pending, none }

PrState _parseState(Object? raw) => switch (raw) {
      'merged' => PrState.merged,
      'closed' => PrState.closed,
      'draft' => PrState.draft,
      _ => PrState.open,
    };

PrChecks _parseChecks(Object? raw) => switch (raw) {
      'pass' => PrChecks.pass,
      'fail' => PrChecks.fail,
      'pending' => PrChecks.pending,
      _ => PrChecks.none,
    };

/// A branch's pull request, as returned by the daemon's `github-pr-list`.
@immutable
class PrInfo {
  const PrInfo({
    required this.number,
    required this.title,
    required this.state,
    required this.url,
    this.checks = PrChecks.none,
    this.head,
  });

  final int number;
  final String title;
  final PrState state;
  final String url;
  final PrChecks checks;

  /// Head commit sha. Absent from an older daemon.
  final String? head;

  /// Null for a record that names no PR (no number).
  static PrInfo? fromJson(Map<String, dynamic> json) {
    final number = json['number'];
    if (number is! int) return null;
    final head = json['head'];
    return PrInfo(
      number: number,
      title: json['title']?.toString() ?? '',
      state: _parseState(json['state']),
      url: json['url']?.toString() ?? '',
      checks: _parseChecks(json['checks']),
      head: head is String && head.isNotEmpty ? head : null,
    );
  }

  Map<String, dynamic> toJson() => {
        'number': number,
        'title': title,
        'state': state.name,
        'url': url,
        'checks': checks.name,
        if (head != null) 'head': head,
      };

  @override
  bool operator ==(Object other) =>
      other is PrInfo &&
      other.number == number &&
      other.title == title &&
      other.state == state &&
      other.url == url &&
      other.checks == checks &&
      other.head == head;

  @override
  int get hashCode => Object.hash(number, title, state, url, checks, head);
}

/// Daemon `github-pr-list` errors that mean "this repo has no PR decoration to
/// show": not a repo, no `gh`, not signed in, no GitHub remote. They resolve
/// to an empty map and are cached like any answer, since asking again soon
/// would only spawn `gh` to hear the same thing. Every other code
/// (`gh_unavailable`: a timeout, a rate limit, an outage) is transient and
/// throws instead, so the caller keeps the icons it already shows.
const Set<String> kSettledPrErrors = {
  'not_a_repo',
  'gh_missing',
  'gh_unauthenticated',
  'no_remote',
};

/// Pull-request state for every branch of the repo containing [cwd], keyed by
/// head branch. Empty when the repo simply has no PRs to show (see
/// [kSettledPrErrors]); throws [GitOpsException] on a transient daemon error
/// and the transport's own exception when the machine can't be reached.
/// Neither is ever worth raising at the user.
Future<Map<String, PrInfo>> rpcGithubPrList({
  required RpcCaller call,
  required String machineId,
  required String cwd,
}) async {
  final result = await call(machineId, 'github-pr-list', {'cwd': cwd});
  final err = result['error'];
  if (err is String) {
    if (kSettledPrErrors.contains(err)) return const {};
    throw GitOpsException(err);
  }
  final raw = result['prs'];
  if (raw is! Map) return const {};
  final prs = <String, PrInfo>{};
  for (final e in raw.entries) {
    final v = e.value;
    if (v is! Map) continue;
    final pr = PrInfo.fromJson(Map<String, dynamic>.from(v));
    if (pr != null) prs[e.key.toString()] = pr;
  }
  return prs;
}

/// A repo's PR map, stamped with when the request behind it went out.
@immutable
class PrSnapshot {
  const PrSnapshot({required this.prs, required this.requestedAt});
  final Map<String, PrInfo> prs;

  /// Of two snapshots, the one requested later wins.
  final DateTime requestedAt;
}

/// How long a repo's PR map is reused before a later trigger refetches it.
const Duration kPrCacheTtl = Duration(seconds: 60);

class _CacheEntry {
  _CacheEntry(this.at, this.value);
  final DateTime at;
  final Future<PrSnapshot> value;
}

final Map<String, _CacheEntry> _prCache = {};

/// The latest settled answer per repo. Kept apart from [_prCache] so a refresh
/// in flight doesn't hide the answer it is about to replace.
final Map<String, PrSnapshot> _prLatest = {};

String _normalizePath(String path) {
  var p = path.trim();
  while (p.length > 1 && p.endsWith('/')) {
    p = p.substring(0, p.length - 1);
  }
  return p;
}

/// Cache identity of one repo on one machine.
String prRepoKey(String machineId, String repoPath) =>
    '$machineId|${_normalizePath(repoPath)}';

/// [rpcGithubPrList] behind a cache shared by every screen, keyed by machine +
/// repo. A request sent within the last [maxAge] is reused, in flight or
/// settled; otherwise a new one goes out. A failure is never cached: a
/// transient disconnect or `gh` timeout would otherwise read as "no PRs" until
/// the entry expired.
///
/// Home asks on every list refresh (open, resume, reconnect, pull), so without
/// this a user flicking the app in and out would spend one GitHub request per
/// repo each time.
Future<PrSnapshot> rpcGithubPrListCached({
  required RpcCaller call,
  required String machineId,
  required String repoPath,
  Duration maxAge = kPrCacheTtl,
}) {
  final key = prRepoKey(machineId, repoPath);
  final hit = _prCache[key];
  final now = DateTime.now();
  if (hit != null && now.difference(hit.at) < maxAge) return hit.value;

  late final _CacheEntry entry;
  final value = rpcGithubPrList(call: call, machineId: machineId, cwd: repoPath).then(
    (prs) {
      final snapshot = PrSnapshot(prs: prs, requestedAt: now);
      final latest = _prLatest[key];
      if (latest == null || !latest.requestedAt.isAfter(now)) _prLatest[key] = snapshot;
      return snapshot;
    },
    onError: (Object err, StackTrace stack) {
      // Only drop our own entry; a newer request may already have replaced it.
      if (identical(_prCache[key], entry)) _prCache.remove(key);
      Error.throwWithStackTrace(err, stack);
    },
  );
  entry = _CacheEntry(now, value);
  _prCache[key] = entry;
  return value;
}

/// The last settled answer for this repo this run, if any, without asking:
/// lets a screen paint the colors Home already knows before its own request
/// lands.
PrSnapshot? peekGithubPrList(String machineId, String repoPath) =>
    _prLatest[prRepoKey(machineId, repoPath)];

/// When the cached request for this repo went out, or null if none is cached.
DateTime? githubPrListRequestedAt(String machineId, String repoPath) =>
    _prCache[prRepoKey(machineId, repoPath)]?.at;

@visibleForTesting
void resetGithubPrListCache() {
  _prCache.clear();
  _prLatest.clear();
}
