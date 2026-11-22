// Loads one file for the viewer: live from the machine, falling back to the
// last cached copy when the machine can't be reached. The image gallery keeps
// one per page around the current one, so a neighbour can load before it is
// swiped in.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import '/custom_code/actions/files_cache.dart';
import '/custom_code/actions/rpc_files.dart';

class FileContentLoader extends ChangeNotifier {
  FileContentLoader({
    required this.machineId,
    required this.cwd,
    required this.path,
    required Future<FilesCache> cache,
    required RpcCaller call,
    required bool Function() isConnected,
    bool viewed = true,
  })  : _cache = cache,
        _call = call,
        _isConnected = isConnected,
        _viewed = viewed;

  final String machineId;
  final String cwd;
  final String path;
  final Future<FilesCache> _cache;
  final RpcCaller _call;
  final bool Function() _isConnected;

  // RPC failures matching these mean "machine unreachable" rather than a
  // per-file error. Mirrors FilesTabModel's set.
  static const Set<String> _connectivityCodes = {
    'not_connected',
    'target_disconnected',
    'timeout',
    'no_handler',
  };

  FileContent? _content;
  FileContent? get content => _content;
  String? errorCode;
  bool loading = true;
  // True when the live fetch failed for a connectivity reason; drives the
  // offline banner. Independent of whether a cached copy was found — that's
  // `content != null`.
  bool offline = false;

  // A preloaded neighbour is fetched but not cached: only a file the user
  // actually looked at earns a cache slot (images are big; see FilesCache).
  bool _viewed;
  FileContent? _unsaved;
  Uint8List? _imageBytes;
  Future<void>? _pending;
  bool _disposed = false;

  /// The decoded image, decoded once rather than on every build. Null unless
  /// the content is a non-empty base64 image.
  Uint8List? get imageBytes {
    final c = _content;
    if (c == null || c.encoding != 'base64' || !c.isBinary || c.content.isEmpty) return null;
    return _imageBytes ??= base64Decode(c.content);
  }

  /// Completes when the load in flight (or the last one) settles.
  Future<void> get settled => _pending ?? Future<void>.value();

  Future<void> load() => _pending = _load();

  /// The user landed on this file: cache it if it was fetched as a preload.
  void markViewed() {
    if (_viewed) return;
    _viewed = true;
    final unsaved = _unsaved;
    if (unsaved != null) unawaited(_save(unsaved));
  }

  Future<void> _load() async {
    loading = true;
    errorCode = null;
    _notify();
    final cache = await _cache;
    if (_disposed) return;

    // Fast path: WS already down — surface offline immediately, don't sit on
    // callRpc's wait-then-timeout cycle (~30s).
    if (!_isConnected()) {
      _renderOfflineFromCache(cache);
      return;
    }

    try {
      final content = await rpcReadFile(call: _call, machineId: machineId, cwd: cwd, path: path);
      if (_disposed) return;
      _setContent(content);
      loading = false;
      offline = false;
      if (_viewed) {
        // Fire-and-forget — the UI is already painting.
        unawaited(_save(content));
      } else {
        _unsaved = content;
      }
      _notify();
    } on FileOpsException catch (e) {
      if (_disposed) return;
      if (_connectivityCodes.contains(e.code)) {
        _renderOfflineFromCache(cache);
      } else {
        errorCode = e.code;
        loading = false;
        offline = false;
        _notify();
      }
    } catch (_) {
      if (_disposed) return;
      _renderOfflineFromCache(cache);
    }
  }

  Future<void> _save(FileContent content) async {
    _unsaved = null;
    final cache = await _cache;
    try {
      await cache.putContent(
        machineId: machineId,
        cwd: cwd,
        path: path,
        content: content.content,
        encoding: content.encoding,
        isBinary: content.isBinary,
        size: content.size,
        truncated: content.truncated,
      );
    } catch (_) {
      // Best effort: the Files screen closes the shared box when it goes
      // away, which can land mid-write. A missed cache entry only costs an
      // offline view.
    }
  }

  void _renderOfflineFromCache(FilesCache cache) {
    final cached = cache.getContent(machineId: machineId, cwd: cwd, path: path);
    loading = false;
    offline = true;
    errorCode = null;
    _setContent(cached == null
        ? null
        : FileContent(
            content: cached['content'] as String,
            encoding: cached['encoding'] as String,
            isBinary: cached['is_binary'] as bool,
            size: cached['size'] as int,
            truncated: cached['truncated'] as bool,
          ));
    _notify();
  }

  void _setContent(FileContent? content) {
    _content = content;
    _imageBytes = null;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
