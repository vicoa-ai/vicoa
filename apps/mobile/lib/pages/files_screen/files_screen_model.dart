// Page model for FilesScreen. Owns the FilesTabModel + cache lifecycle.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C.

import 'dart:async';

import 'package:flutter/widgets.dart';

import '/custom_code/actions/files_cache.dart';
import '/custom_code/actions/files_tab_model.dart';
import '/custom_code/actions/git_tab_model.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_files.dart';
import '/custom_code/actions/rpc_git.dart';
import '/flutter_flow/flutter_flow_model.dart';
import 'files_screen_widget.dart';

class FilesScreenModel extends FlutterFlowModel<FilesScreenWidget> {
  bool _initialized = false;
  FilesCache? _cache;
  FilesTabModel? tab;
  GitTabModel? gitTab;
  String? _machineId;
  String? _cwd;

  VoidCallback? _notify;
  void setNotify(VoidCallback fn) => _notify = fn;
  void _bump() => _notify?.call();

  int? get lastFilesTabIndex => _cache?.getLastFilesTabIndex();

  Future<void> persistLastFilesTabIndex(int index) async {
    await _cache?.putLastFilesTabIndex(index);
  }

  Future<void> initialize({required String machineId, required String cwd}) async {
    if (_initialized) return;
    _initialized = true;
    _machineId = machineId;
    _cwd = cwd;
    actions.VicoaWsClient.instance.retain();
    _cache = await FilesCache.open();
    final cacheAdapter = _CacheAdapter(_cache!);
    tab = FilesTabModel(
      machineId: machineId,
      cwd: cwd,
      cache: cacheAdapter,
      // Fast-fail the RPC if the WS is already disconnected, so the offline
      // banner shows immediately instead of waiting for callRpc's
      // wait-then-timeout path (~30s).
      listFiles: ({required machineId, required cwd, required path}) async {
        final client = actions.VicoaWsClient.instance;
        if (!client.isConnected) throw FileOpsException('not_connected');
        return rpcListFiles(
          call: client.callRpc,
          machineId: machineId,
          cwd: cwd,
          path: path,
        );
      },
    );
    tab!.addListener(_bump);
    await tab!.initialize();
  }

  /// Lazy-init for the Git tab: only built the first time the user lands on
  /// it, so users who never open Git don't pay the activation cost.
  Future<void> activateGitTab() async {
    if (gitTab != null || _cache == null) return;
    final machineId = _machineId!;
    final cwd = _cwd!;
    final gitCacheAdapter = _GitCacheAdapter(_cache!);
    gitTab = GitTabModel(
      machineId: machineId,
      cwd: cwd,
      cache: gitCacheAdapter,
      gitStatus: ({required machineId, required cwd}) async {
        final client = actions.VicoaWsClient.instance;
        if (!client.isConnected) throw GitOpsException('not_connected');
        return rpcGitStatus(
          call: client.callRpc,
          machineId: machineId,
          cwd: cwd,
        );
      },
      gitDiff: ({
        required machineId,
        required cwd,
        required path,
        required staged,
        required ignoreWhitespace,
      }) async {
        final client = actions.VicoaWsClient.instance;
        if (!client.isConnected) throw GitOpsException('not_connected');
        return rpcGitDiff(
          call: client.callRpc,
          machineId: machineId,
          cwd: cwd,
          path: path,
          staged: staged,
          ignoreWhitespace: ignoreWhitespace,
        );
      },
    );
    gitTab!.addListener(_bump);
    await gitTab!.activate();
  }

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    tab?.removeListener(_bump);
    gitTab?.removeListener(_bump);
    _cache?.close();
    actions.VicoaWsClient.instance.release();
  }
}

class _GitCacheAdapter implements GitTabCache {
  _GitCacheAdapter(this._inner);
  final FilesCache _inner;

  @override
  Map<String, dynamic>? getDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
  }) =>
      _inner.getDiff(
        machineId: machineId,
        cwd: cwd,
        path: path,
        contentHash: contentHash,
        staged: staged,
        ignoreWhitespace: ignoreWhitespace,
      );

  @override
  Future<void> putDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
    required Map<String, dynamic> payload,
  }) =>
      _inner.putDiff(
        machineId: machineId,
        cwd: cwd,
        path: path,
        contentHash: contentHash,
        staged: staged,
        ignoreWhitespace: ignoreWhitespace,
        payload: payload,
      );

  @override
  Map<String, dynamic>? getLastStatus({
    required String machineId,
    required String cwd,
  }) =>
      _inner.getLastStatus(machineId: machineId, cwd: cwd);

  @override
  Future<void> putLastStatus({
    required String machineId,
    required String cwd,
    required Map<String, dynamic> payload,
  }) =>
      _inner.putLastStatus(machineId: machineId, cwd: cwd, payload: payload);

  @override
  Set<String> getExpandedPaths({
    required String machineId,
    required String cwd,
  }) =>
      _inner.getExpandedPaths(machineId: machineId, cwd: cwd);

  @override
  Future<void> putExpandedPaths({
    required String machineId,
    required String cwd,
    required Set<String> paths,
  }) =>
      _inner.putExpandedPaths(machineId: machineId, cwd: cwd, paths: paths);

  @override
  GitTabPrefs? getGitTabPrefs() {
    final raw = _inner.getGitTabPrefsRaw();
    if (raw == null) return null;
    return GitTabPrefs(
      wrapLines: raw['wrap'] as bool? ?? true,
      hideWhitespace: raw['hide_ws'] as bool? ?? false,
    );
  }

  @override
  Future<void> putGitTabPrefs(GitTabPrefs prefs) =>
      _inner.putGitTabPrefsRaw({
        'wrap': prefs.wrapLines,
        'hide_ws': prefs.hideWhitespace,
      });
}

class _CacheAdapter implements FilesTabCache {
  _CacheAdapter(this._inner);
  final FilesCache _inner;

  @override
  List<dynamic>? getListing({required String machineId, required String cwd, required String path}) =>
      _inner.getListing(machineId: machineId, cwd: cwd, path: path);

  @override
  Future<void> putListing({required String machineId, required String cwd, required String path, required List<dynamic> entries}) =>
      _inner.putListing(machineId: machineId, cwd: cwd, path: path, entries: entries);

  // Expanded set is persisted via the same Hive box under a distinct key prefix.
  // Cap to 200 entries per the §Risks table; oldest evicted by Set ordering.
  @override
  Set<String> getExpanded({required String machineId, required String cwd}) {
    final raw = _inner.getListing(machineId: machineId, cwd: cwd, path: '__expanded__');
    if (raw == null) return <String>{};
    return raw.map((e) => e.toString()).toSet();
  }

  @override
  Future<void> putExpanded({required String machineId, required String cwd, required Set<String> expanded}) async {
    final list = expanded.toList();
    final trimmed = list.length > 200 ? list.sublist(list.length - 200) : list;
    await _inner.putListing(machineId: machineId, cwd: cwd, path: '__expanded__', entries: trimmed);
  }
}

