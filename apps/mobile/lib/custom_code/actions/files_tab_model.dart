// State machine backing the Files tab.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C Files tab body.
//
// Pure ChangeNotifier — `listFiles` and `cache` are injected so the model is
// unit-testable without a live WebSocket or Hive box.

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'rpc_files.dart';

typedef ListFilesFn = Future<List<FilesEntry>> Function({
  required String machineId,
  required String cwd,
  required String path,
});

abstract class FilesTabCache {
  List<dynamic>? getListing({
    required String machineId,
    required String cwd,
    required String path,
  });
  Future<void> putListing({
    required String machineId,
    required String cwd,
    required String path,
    required List<dynamic> entries,
  });
  Set<String> getExpanded({required String machineId, required String cwd});
  Future<void> putExpanded({
    required String machineId,
    required String cwd,
    required Set<String> expanded,
  });
}

sealed class ListingState {
  const ListingState();
}

class ListingLoading extends ListingState {
  const ListingLoading();
}

class ListingLoaded extends ListingState {
  ListingLoaded(this.entries);
  final List<FilesEntry> entries;
}

class ListingError extends ListingState {
  ListingError(this.code);
  final String code;
}

class FilesTabModel extends ChangeNotifier {
  FilesTabModel({
    required this.machineId,
    required this.cwd,
    required this.listFiles,
    required this.cache,
  });

  final String machineId;
  final String cwd;
  final ListFilesFn listFiles;
  final FilesTabCache cache;

  final Map<String, ListingState> _listings = {};
  final Set<String> _expanded = <String>{};

  // RPC error codes that mean "couldn't reach the daemon" rather than a real
  // per-path failure. Surfaced as the persistent offline banner above the tabs
  // so the user still sees cached listings instead of a wiped screen.
  static const Set<String> _connectivityCodes = {
    'not_connected',
    'target_disconnected',
    'timeout',
    'no_handler',
  };

  String? _offlineCode;
  String? get offlineCode => _offlineCode;
  bool get isMachineOffline => _offlineCode != null;

  ListingState? listingFor(String path) => _listings[path];
  Set<String> get expanded => Set.unmodifiable(_expanded);

  Future<void> initialize() async {
    _expanded.addAll(cache.getExpanded(machineId: machineId, cwd: cwd));
    final futures = <Future<void>>[_loadInto('')];
    for (final p in _expanded) {
      futures.add(_loadInto(p));
    }
    await Future.wait(futures);
  }

  /// Re-fetch the root and every currently-expanded directory.
  /// Backs the pull-to-refresh gesture and lifecycle resume / WS reconnect hooks.
  Future<void> refresh() async {
    final paths = <String>{'', ..._expanded};
    await Future.wait(paths.map(_loadInto));
  }

  Future<void> toggleExpanded(String path) async {
    if (_expanded.contains(path)) {
      _expanded.remove(path);
    } else {
      _expanded.add(path);
      if (_listings[path] is! ListingLoaded) {
        // Fire-and-forget — caller can `await` if needed.
        unawaited(_loadInto(path));
      }
    }
    await cache.putExpanded(
      machineId: machineId,
      cwd: cwd,
      expanded: _expanded,
    );
    notifyListeners();
  }

  Future<void> _loadInto(String path) async {
    final cached = cache.getListing(
      machineId: machineId,
      cwd: cwd,
      path: path,
    );
    if (cached != null) {
      _listings[path] = ListingLoaded(
        cached
            .map(
              (e) => FilesEntry(
                name: e['name'] as String,
                isDir: e['type'] == 'dir',
                size: e['size'] as int?,
              ),
            )
            .toList(),
      );
    } else {
      _listings[path] = const ListingLoading();
    }
    notifyListeners();
    try {
      final entries = await listFiles(
        machineId: machineId,
        cwd: cwd,
        path: path,
      );
      _listings[path] = ListingLoaded(entries);
      _offlineCode = null;
      await cache.putListing(
        machineId: machineId,
        cwd: cwd,
        path: path,
        entries: entries
            .map(
              (e) => {
                'name': e.name,
                'type': e.isDir ? 'dir' : 'file',
                if (e.size != null) 'size': e.size,
              },
            )
            .toList(),
      );
    } on FileOpsException catch (exc) {
      _applyError(path, exc.code);
    } catch (_) {
      // Non-FileOps errors (RpcException, network-layer) are always
      // connectivity-flavoured by the time they reach the model.
      _applyError(path, 'not_connected');
    }
    notifyListeners();
  }

  /// Apply a fetch error to [path]. Connectivity errors flip the offline flag
  /// and preserve any cached listing already in [_listings]; per-path failures
  /// (path_not_found, permission_denied, …) overwrite to [ListingError] so
  /// the tab can show a precise message.
  void _applyError(String path, String code) {
    if (_connectivityCodes.contains(code)) {
      _offlineCode = code;
      if (_listings[path] is! ListingLoaded) {
        _listings[path] = ListingError(code);
      }
      // else: keep stale cached entries visible — banner above the tabs
      // tells the user why they look frozen.
    } else {
      _listings[path] = ListingError(code);
    }
  }
}
