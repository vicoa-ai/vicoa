// Hive-backed SWR cache for the Files tab.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers + §2 #13.

import 'dart:convert';

import 'package:hive/hive.dart';
import 'package:path_provider/path_provider.dart';

class FilesCache {
  FilesCache._(this._box, this._maxEntries);

  static const String _boxName = 'files_cache_v1';

  // Insertion-order eviction approximates LRU at very low cost (Hive Box
  // preserves put order). Plan §2 #13 calls for ~50 MB; per-entry cap maps to
  // that at ~5 KB avg listing × 1000 ≈ 5 MB, plus a few cached file contents.
  // Plan §Risks accepts revisiting on telemetry evidence; this is the v1.
  static const int _defaultMaxEntries = 1000;

  final Box<String> _box;
  final int _maxEntries;

  static bool _initialized = false;

  static Future<void> _ensureInit() async {
    if (_initialized) return;
    try {
      final dir = await getApplicationDocumentsDirectory();
      Hive.init(dir.path);
    } catch (_) {
      // flutter_test (or other sandboxed) environment — the caller is
      // expected to have called `Hive.init(...)` themselves. `Hive.init` is
      // idempotent, so a no-op here is safe.
    }
    _initialized = true;
  }

  static Future<FilesCache> open({int maxEntries = _defaultMaxEntries}) async {
    await _ensureInit();
    final box = await Hive.openBox<String>(_boxName);
    return FilesCache._(box, maxEntries);
  }

  /// Wipe every cached listing/content without needing a live FilesCache
  /// instance — call this from the logout flow. Safe to invoke whether the
  /// box is currently open or not.
  static Future<void> wipeStatic() async {
    await _ensureInit();
    final box = Hive.isBoxOpen(_boxName)
        ? Hive.box<String>(_boxName)
        : await Hive.openBox<String>(_boxName);
    await box.clear();
  }

  Future<void> close() => _box.close();

  String _listingKey({
    required String machineId,
    required String cwd,
    required String path,
  }) => 'L|$machineId|$cwd|$path';

  String _contentKey({
    required String machineId,
    required String cwd,
    required String path,
  }) => 'C|$machineId|$cwd|$path';

  // Diff cache: content-addressed via contentHash so a working-tree edit
  // invalidates the entry automatically (plan §2 #13 / §Cache).
  String _diffKey({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
  }) {
    final s = staged ? 's' : 'u';
    final w = ignoreWhitespace ? 'w' : '.';
    return 'D|$machineId|$cwd|$path|$contentHash|$s|$w';
  }

  // Last-status: single slot per (machineId, cwd) — overwritten on every
  // successful status fetch, read only for offline-fallback rendering.
  String _lastStatusKey({
    required String machineId,
    required String cwd,
  }) => 'S|$machineId|$cwd';

  // Expanded-file set: persisted Git-tab "user has opened these files"
  // state per (machineId, cwd). Stored as a JSON list of DiffKey strings
  // (the model's `_diffKey` format: `<path>|s` or `<path>|u`).
  String _expandedPathsKey({
    required String machineId,
    required String cwd,
  }) => 'EX|$machineId|$cwd';

  // Git-tab toolbar prefs (wrap / hide-whitespace). Global — the user's
  // reading preference, not per-repo. Single slot.
  static const String _gitPrefsKey = 'GP';

  // Last-opened FilesScreen tab index (0 = Files, 1 = Git). Single slot,
  // global — restored on next entry to FilesScreen.
  static const String _lastFilesTabIndexKey = 'LFT';

  Future<void> _put(String key, String value) async {
    if (_box.containsKey(key)) {
      await _box.delete(key);  // Move to most-recent slot on re-put.
    }
    await _box.put(key, value);
    if (_box.length > _maxEntries) {
      final overflow = _box.length - _maxEntries;
      final victims = _box.keys.take(overflow).toList();
      await _box.deleteAll(victims);
    }
  }

  Future<void> putListing({
    required String machineId,
    required String cwd,
    required String path,
    required List<dynamic> entries,
  }) async {
    final key = _listingKey(machineId: machineId, cwd: cwd, path: path);
    await _put(key, jsonEncode(entries));
  }

  List<dynamic>? getListing({
    required String machineId,
    required String cwd,
    required String path,
  }) {
    final key = _listingKey(machineId: machineId, cwd: cwd, path: path);
    final raw = _box.get(key);
    if (raw == null) return null;
    return jsonDecode(raw) as List<dynamic>;
  }

  Future<void> putContent({
    required String machineId,
    required String cwd,
    required String path,
    required String content,
    required String encoding,
    required bool isBinary,
    required int size,
    required bool truncated,
  }) async {
    final key = _contentKey(machineId: machineId, cwd: cwd, path: path);
    await _put(
      key,
      jsonEncode({
        'content': content,
        'encoding': encoding,
        'is_binary': isBinary,
        'size': size,
        'truncated': truncated,
      }),
    );
  }

  Map<String, dynamic>? getContent({
    required String machineId,
    required String cwd,
    required String path,
  }) {
    final key = _contentKey(machineId: machineId, cwd: cwd, path: path);
    final raw = _box.get(key);
    if (raw == null) return null;
    return jsonDecode(raw) as Map<String, dynamic>;
  }

  Future<void> putDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
    required Map<String, dynamic> payload,
  }) async {
    final key = _diffKey(
      machineId: machineId,
      cwd: cwd,
      path: path,
      contentHash: contentHash,
      staged: staged,
      ignoreWhitespace: ignoreWhitespace,
    );
    await _put(key, jsonEncode(payload));
  }

  Map<String, dynamic>? getDiff({
    required String machineId,
    required String cwd,
    required String path,
    required String contentHash,
    required bool staged,
    required bool ignoreWhitespace,
  }) {
    final key = _diffKey(
      machineId: machineId,
      cwd: cwd,
      path: path,
      contentHash: contentHash,
      staged: staged,
      ignoreWhitespace: ignoreWhitespace,
    );
    final raw = _box.get(key);
    if (raw == null) return null;
    return jsonDecode(raw) as Map<String, dynamic>;
  }

  Future<void> putLastStatus({
    required String machineId,
    required String cwd,
    required Map<String, dynamic> payload,
  }) async {
    final key = _lastStatusKey(machineId: machineId, cwd: cwd);
    await _put(key, jsonEncode(payload));
  }

  Map<String, dynamic>? getLastStatus({
    required String machineId,
    required String cwd,
  }) {
    final key = _lastStatusKey(machineId: machineId, cwd: cwd);
    final raw = _box.get(key);
    if (raw == null) return null;
    return jsonDecode(raw) as Map<String, dynamic>;
  }

  Set<String> getExpandedPaths({
    required String machineId,
    required String cwd,
  }) {
    final key = _expandedPathsKey(machineId: machineId, cwd: cwd);
    final raw = _box.get(key);
    if (raw == null) return <String>{};
    final decoded = jsonDecode(raw);
    if (decoded is! List) return <String>{};
    return decoded.map((e) => e.toString()).toSet();
  }

  Future<void> putExpandedPaths({
    required String machineId,
    required String cwd,
    required Set<String> paths,
  }) async {
    final key = _expandedPathsKey(machineId: machineId, cwd: cwd);
    await _put(key, jsonEncode(paths.toList()));
  }

  Map<String, dynamic>? getGitTabPrefsRaw() {
    final raw = _box.get(_gitPrefsKey);
    if (raw == null) return null;
    final decoded = jsonDecode(raw);
    if (decoded is! Map) return null;
    return Map<String, dynamic>.from(decoded);
  }

  Future<void> putGitTabPrefsRaw(Map<String, dynamic> payload) =>
      _put(_gitPrefsKey, jsonEncode(payload));

  int? getLastFilesTabIndex() {
    final raw = _box.get(_lastFilesTabIndexKey);
    if (raw == null) return null;
    return int.tryParse(raw);
  }

  Future<void> putLastFilesTabIndex(int index) =>
      _put(_lastFilesTabIndexKey, index.toString());

  Future<void> wipeAll() async {
    await _box.clear();
  }
}
