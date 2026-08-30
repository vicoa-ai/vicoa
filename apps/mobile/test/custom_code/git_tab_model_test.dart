// State-machine spec for the Git tab. See
// `plans/todos/vicoa-app-git-tab.md` §Phase C State + Refresh wiring + Tests.
//
// Uses controllable in-memory RPC + cache fakes — no live WS or Hive.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/git_tab_model.dart';
import 'package:vicoa/custom_code/actions/rpc_git.dart';

// --- fakes -------------------------------------------------------------------

class _FakeCache implements GitTabCache {
  final Map<String, Map<String, dynamic>> diffs = {};
  final Map<String, Map<String, dynamic>> statuses = {};
  final Map<String, Set<String>> expandedPaths = {};
  GitTabPrefs? gitTabPrefs;

  String _diffKey(
    String mid,
    String cwd,
    String path,
    String hash,
    bool staged,
    bool ws,
  ) => '$mid|$cwd|$path|$hash|${staged ? 's' : 'u'}|${ws ? 'w' : '.'}';

  String _statusKey(String mid, String cwd) => '$mid|$cwd';

  @override
  Map<String, dynamic>? getDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
  }) =>
      diffs[_diffKey(machineId, cwd, path, contentHash, staged, ignoreWhitespace)];

  @override
  Future<void> putDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
    required Map<String, dynamic> payload,
  }) async {
    diffs[_diffKey(machineId, cwd, path, contentHash, staged, ignoreWhitespace)] =
        payload;
  }

  @override
  Map<String, dynamic>? getLastStatus({required String machineId, required String cwd}) =>
      statuses[_statusKey(machineId, cwd)];

  @override
  Future<void> putLastStatus({
    required String machineId,
    required String cwd,
    required Map<String, dynamic> payload,
  }) async {
    statuses[_statusKey(machineId, cwd)] = payload;
  }

  @override
  Set<String> getExpandedPaths({required String machineId, required String cwd}) =>
      expandedPaths[_statusKey(machineId, cwd)] ?? <String>{};

  @override
  Future<void> putExpandedPaths({
    required String machineId,
    required String cwd,
    required Set<String> paths,
  }) async {
    expandedPaths[_statusKey(machineId, cwd)] = Set<String>.from(paths);
  }

  @override
  GitTabPrefs? getGitTabPrefs() => gitTabPrefs;

  @override
  Future<void> putGitTabPrefs(GitTabPrefs prefs) async {
    gitTabPrefs = prefs;
  }
}

/// RPC fakes — each call resolves via a completer in `pending`, so the test
/// can interleave them. If `auto` is true, calls resolve synchronously.
class _FakeRpc {
  _FakeRpc({this.auto = true});
  final bool auto;
  int statusCalls = 0;
  final List<({String path, bool staged, bool ws})> diffCalls = [];
  final List<Completer<GitStatusResult>> pendingStatus = [];
  final List<Completer<GitDiffResult>> pendingDiff = [];

  Map<String, dynamic>? nextStatusPayload;
  Object? nextStatusError;
  Map<String, Map<String, dynamic>> diffPayloads = {};
  Object? nextDiffError;

  Future<GitStatusResult> status({
    required String machineId,
    required String cwd,
  }) async {
    statusCalls += 1;
    if (auto) {
      if (nextStatusError != null) throw nextStatusError!;
      return GitStatusResult.fromJson(nextStatusPayload!);
    }
    final c = Completer<GitStatusResult>();
    pendingStatus.add(c);
    return c.future;
  }

  Future<GitDiffResult> diff({
    required String machineId,
    required String cwd,
    required String path,
    required bool staged,
    required bool ignoreWhitespace,
  }) async {
    diffCalls.add((path: path, staged: staged, ws: ignoreWhitespace));
    if (auto) {
      if (nextDiffError != null) throw nextDiffError!;
      final key = '$path|${staged ? 's' : 'u'}';
      return GitDiffResult.fromJson(diffPayloads[key] ??
          {
            'path': path,
            'hunks': [],
            'is_binary': false,
            'truncated': false,
            'size': 0,
          });
    }
    final c = Completer<GitDiffResult>();
    pendingDiff.add(c);
    return c.future;
  }
}

Map<String, dynamic> _statusOneUnstaged(String path, String hash) => {
      'branch': 'main',
      'ahead': 0,
      'behind': 0,
      'staged': [],
      'unstaged': [
        {
          'path': path,
          'status': 'M',
          'additions': 1,
          'deletions': 0,
          'content_hash': hash,
        }
      ],
      'untracked': [],
    };

GitTabModel _makeModel(_FakeCache cache, _FakeRpc rpc) => GitTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: cache,
      gitStatus: rpc.status,
      gitDiff: rpc.diff,
    );

void main() {
  // --- activate ---------------------------------------------------------------

  test('activate fetches status and exposes branch + sections', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);

    await model.activate();

    expect(model.status, isNotNull);
    expect(model.status!.branch, 'main');
    expect(model.status!.unstaged.single.path, 'a.dart');
    expect(rpc.statusCalls, 1);
  });

  test('activate fetches diff for each file in status', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);

    await model.activate();

    expect(rpc.diffCalls, hasLength(1));
    expect(rpc.diffCalls.single.path, 'a.dart');
    expect(rpc.diffCalls.single.staged, isFalse);
  });

  test('activate caches each diff under (path, hash, staged, ignoreWs)', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a')
      ..diffPayloads['a.dart|u'] = {
        'path': 'a.dart',
        'hunks': [
          {
            'header': '@@',
            'old_start': 1,
            'old_count': 1,
            'new_start': 1,
            'new_count': 2,
            'lines': [
              {'type': 'add', 'content': 'x'}
            ]
          }
        ],
        'is_binary': false,
        'truncated': false,
        'size': 2,
      };
    final model = _makeModel(cache, rpc);
    await model.activate();

    final cached = cache.getDiff(
      machineId: 'm',
      cwd: '/proj',
      path: 'a.dart',
      contentHash: 'h-a',
      staged: false,
      ignoreWhitespace: false,
    );
    expect(cached, isNotNull);
    expect(cached!['size'], 2);
  });

  // --- cache replay ----------------------------------------------------------

  test('activate uses cached diff when hash matches — no RPC fired', () async {
    final cache = _FakeCache();
    // Pre-seed cache with the expected diff payload.
    await cache.putDiff(
      machineId: 'm',
      cwd: '/proj',
      path: 'a.dart',
      contentHash: 'h-a',
      staged: false,
      ignoreWhitespace: false,
      payload: {
        'path': 'a.dart',
        'hunks': [],
        'is_binary': false,
        'truncated': false,
        'size': 0,
      },
    );
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);

    await model.activate();

    expect(rpc.diffCalls, isEmpty,
        reason: 'cached entry should satisfy the fetch — no RPC');
    final entry = model.diffFor('a.dart', staged: false);
    expect(entry, isNotNull);
    expect(entry!.payload, isNotNull);
  });

  // --- refresh: content_hash invalidation ------------------------------------

  test('refresh re-fetches diff for file whose content_hash changed', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-old');
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(rpc.diffCalls, hasLength(1));

    rpc.diffCalls.clear();
    rpc.nextStatusPayload = _statusOneUnstaged('a.dart', 'h-new');

    await model.refresh();

    expect(rpc.diffCalls, hasLength(1));
    expect(rpc.diffCalls.single.path, 'a.dart');
  });

  test('refresh skips RPC when content_hash unchanged', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(rpc.diffCalls, hasLength(1));

    rpc.diffCalls.clear();
    rpc.nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    await model.refresh();
    expect(rpc.diffCalls, isEmpty,
        reason: 'same hash = cached diff still valid');
  });

  test('refresh drops diff for file no longer in status', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(model.diffFor('a.dart', staged: false), isNotNull);

    rpc.nextStatusPayload = {
      'branch': 'main',
      'ahead': 0,
      'behind': 0,
      'staged': [],
      'unstaged': [],
      'untracked': [],
    };
    await model.refresh();
    expect(model.diffFor('a.dart', staged: false), isNull);
  });

  // --- hide-whitespace toggle ------------------------------------------------

  test('toggleHideWhitespace re-fetches all diffs with new flag', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(rpc.diffCalls.single.ws, isFalse);

    rpc.diffCalls.clear();
    await model.toggleHideWhitespace();

    expect(rpc.diffCalls, hasLength(1));
    expect(rpc.diffCalls.single.ws, isTrue);
  });

  // --- concurrency cap -------------------------------------------------------

  test('initial activate caps diff RPCs at 6 in flight', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc(auto: false);
    // 50-file changeset.
    rpc.nextStatusPayload = {
      'branch': 'main',
      'ahead': 0,
      'behind': 0,
      'staged': [],
      'unstaged': [
        for (var i = 0; i < 50; i++)
          {
            'path': 'f$i.dart',
            'status': 'M',
            'additions': 1,
            'deletions': 0,
            'content_hash': 'h$i',
          }
      ],
      'untracked': [],
    };
    final model = _makeModel(cache, rpc);

    final activate = model.activate();
    // Complete the status call.
    expect(rpc.pendingStatus, hasLength(1));
    rpc.pendingStatus.single.complete(
      GitStatusResult.fromJson(rpc.nextStatusPayload!),
    );
    // Let the diff queue start.
    await Future.delayed(Duration.zero);
    await Future.delayed(Duration.zero);

    expect(rpc.pendingDiff.length, lessThanOrEqualTo(6),
        reason: 'no more than 6 diffs in flight at once');

    // Drain the queue so the test exits cleanly.
    while (rpc.pendingDiff.isNotEmpty || rpc.diffCalls.length < 50) {
      final next = rpc.pendingDiff.removeAt(0);
      next.complete(GitDiffResult.fromJson({
        'path': '',
        'hunks': [],
        'is_binary': false,
        'truncated': false,
        'size': 0,
      }));
      await Future.delayed(Duration.zero);
    }
    await activate;
    expect(rpc.diffCalls, hasLength(50));
  });

  // --- offline ---------------------------------------------------------------

  test('activate flips offline flag when status RPC errors with connectivity code',
      () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()..nextStatusError = GitOpsException('not_connected');
    final model = _makeModel(cache, rpc);

    await model.activate();

    expect(model.offline, isTrue);
    expect(model.status, isNull);
  });

  test('not_a_repo surfaces as statusError, not offline', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()..nextStatusError = GitOpsException('not_a_repo');
    final model = _makeModel(cache, rpc);

    await model.activate();
    expect(model.offline, isFalse);
    expect(model.statusError, 'not_a_repo');
  });

  // --- expansion default + persistence ---------------------------------------

  test('every file starts collapsed on first activate', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);

    await model.activate();
    expect(model.allCollapsed, isTrue);
    expect(model.isCollapsed('a.dart', staged: false), isTrue);
  });

  test('toggleFile flips a file open and persists the set', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();

    model.toggleFile('a.dart', staged: false);
    expect(model.isCollapsed('a.dart', staged: false), isFalse);
    // Same key flows through to the cache so reopening picks it up.
    expect(
      cache.getExpandedPaths(machineId: 'm', cwd: '/proj'),
      contains('a.dart|u'),
    );

    model.toggleFile('a.dart', staged: false);
    expect(model.isCollapsed('a.dart', staged: false), isTrue);
    expect(
      cache.getExpandedPaths(machineId: 'm', cwd: '/proj'),
      isEmpty,
    );
  });

  test('expanded paths round-trip across model re-creation', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final modelA = _makeModel(cache, rpc);
    await modelA.activate();
    modelA.toggleFile('a.dart', staged: false);

    // New model instance (different launch) reads the persisted set.
    final rpcB = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final modelB = _makeModel(cache, rpcB);
    await modelB.activate();
    expect(modelB.isCollapsed('a.dart', staged: false), isFalse);
  });

  test('toggleExpandAll opens every file when nothing is expanded', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = {
        'branch': 'main',
        'ahead': 0,
        'behind': 0,
        'staged': [
          {'path': 'a.dart', 'status': 'A', 'additions': 1, 'deletions': 0, 'content_hash': 'ha'},
        ],
        'unstaged': [
          {'path': 'b.dart', 'status': 'M', 'additions': 1, 'deletions': 0, 'content_hash': 'hb'},
        ],
        'untracked': [
          {'path': 'c.txt', 'status': '??', 'additions': 1, 'deletions': 0, 'content_hash': 'hc'},
        ],
      };
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(model.allCollapsed, isTrue);

    model.toggleExpandAll();
    expect(model.allCollapsed, isFalse);
    expect(model.isCollapsed('a.dart', staged: true), isFalse);
    expect(model.isCollapsed('b.dart', staged: false), isFalse);
    expect(model.isCollapsed('c.txt', staged: false), isFalse);
  });

  test('toggleExpandAll collapses everything when anything is expanded',
      () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();
    model.toggleFile('a.dart', staged: false);
    expect(model.allCollapsed, isFalse);

    model.toggleExpandAll();
    expect(model.allCollapsed, isTrue);
    expect(cache.getExpandedPaths(machineId: 'm', cwd: '/proj'), isEmpty);
  });

  // --- toolbar pref persistence ----------------------------------------------

  test('toggleWrapLines flips and persists the wrap flag', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(model.wrapLines, isTrue);

    model.toggleWrapLines();
    expect(model.wrapLines, isFalse);
    expect(cache.gitTabPrefs?.wrapLines, isFalse);
  });

  test('toggleHideWhitespace flips and persists', () async {
    final cache = _FakeCache();
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(model.hideWhitespace, isFalse);

    await model.toggleHideWhitespace();
    expect(model.hideWhitespace, isTrue);
    expect(cache.gitTabPrefs?.hideWhitespace, isTrue);
  });

  test('activate restores persisted toolbar prefs', () async {
    final cache = _FakeCache()
      ..gitTabPrefs = const GitTabPrefs(wrapLines: false, hideWhitespace: true);
    final rpc = _FakeRpc()
      ..nextStatusPayload = _statusOneUnstaged('a.dart', 'h-a');
    final model = _makeModel(cache, rpc);
    await model.activate();
    expect(model.wrapLines, isFalse);
    expect(model.hideWhitespace, isTrue);
  });
}
