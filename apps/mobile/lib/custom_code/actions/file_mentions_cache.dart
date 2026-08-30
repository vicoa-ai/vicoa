// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

/// Per-project disk cache for the @-mention file list. Large monorepos can
/// return 30k+ paths (~1–2 MB JSON); persisting the parsed list across
/// sessions turns subsequent chat-opens into a near-zero-cost read instead of
/// a fresh network fetch + JSON decode.
///
/// Storage format is newline-separated text (no JSON envelope), so writing
/// and reading are dominated by raw file I/O rather than parsing.
class FileMentionsCache {
  FileMentionsCache._();
  static final FileMentionsCache instance = FileMentionsCache._();

  Future<Directory> _cacheDir() async {
    final base = await getApplicationCacheDirectory();
    final dir = Directory('${base.path}/file_mentions');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  String _keyFor(String projectPath) =>
      base64Url.encode(utf8.encode(projectPath));

  Future<File> _fileFor(String projectPath) async {
    final dir = await _cacheDir();
    return File('${dir.path}/${_keyFor(projectPath)}.txt');
  }

  /// Sidecar holding the daemon's index hash for [projectPath]. Kept beside
  /// the list rather than inside it so the body stays plain newline-separated
  /// text — [read] splits it in a background isolate and a header line would
  /// have to be stripped on every load.
  Future<File> _hashFileFor(String projectPath) async {
    final dir = await _cacheDir();
    return File('${dir.path}/${_keyFor(projectPath)}.hash');
  }

  /// The `known_hash` to send with the next `scan-files`, or null if unknown.
  /// A match lets the daemon reply `unchanged` instead of resending the list.
  Future<String?> readHash(String projectPath) async {
    try {
      final file = await _hashFileFor(projectPath);
      if (!await file.exists()) return null;
      final hash = (await file.readAsString()).trim();
      return hash.isEmpty ? null : hash;
    } catch (e) {
      debugPrint('FileMentionsCache.readHash failed: $e');
      return null;
    }
  }

  /// Record the index hash without rewriting the list — used on `unchanged`,
  /// and to reset the staleness clock that [ageOnDisk] reads.
  Future<void> touch(String projectPath, {String? hash}) async {
    try {
      if (hash != null && hash.isNotEmpty) {
        await (await _hashFileFor(projectPath)).writeAsString(hash);
      }
      final file = await _fileFor(projectPath);
      if (await file.exists()) {
        await file.setLastModified(DateTime.now());
      }
    } catch (e) {
      debugPrint('FileMentionsCache.touch failed: $e');
    }
  }

  /// Cheap existence check — used to decide whether to kick off a network
  /// fetch on chat open vs. defer loading until the user actually types `@`.
  Future<bool> exists(String projectPath) async {
    try {
      final file = await _fileFor(projectPath);
      return await file.exists();
    } catch (_) {
      return false;
    }
  }

  /// How long ago the on-disk cache for [projectPath] was last written, or
  /// `null` if there is no entry. Backed by `File.stat().modified`, which is
  /// bumped automatically by every [write] — no sidecar metadata needed.
  Future<Duration?> ageOnDisk(String projectPath) async {
    try {
      final file = await _fileFor(projectPath);
      if (!await file.exists()) return null;
      final stat = await file.stat();
      return DateTime.now().difference(stat.modified);
    } catch (e) {
      debugPrint('FileMentionsCache.ageOnDisk failed: $e');
      return null;
    }
  }

  /// Returns the cached file list, or `null` if there is no cache entry. The
  /// newline split runs in a background isolate so a large cache doesn't
  /// block the UI thread.
  Future<List<String>?> read(String projectPath) async {
    try {
      final file = await _fileFor(projectPath);
      if (!await file.exists()) return null;
      final body = await file.readAsString();
      return await compute(_splitLines, body);
    } catch (e) {
      debugPrint('FileMentionsCache.read failed: $e');
      return null;
    }
  }

  Future<void> write(String projectPath, List<String> files,
      {String? hash}) async {
    try {
      final file = await _fileFor(projectPath);
      await file.writeAsString(files.join('\n'));
      if (hash != null && hash.isNotEmpty) {
        await (await _hashFileFor(projectPath)).writeAsString(hash);
      }
    } catch (e) {
      debugPrint('FileMentionsCache.write failed: $e');
    }
  }

  /// Deletes every cached file list. Call on debug reset so the next chat
  /// open re-fetches from the backend rather than serving stale data.
  Future<void> clearAll() async {
    try {
      final dir = await _cacheDir();
      await for (final entity in dir.list()) {
        if (entity is File) await entity.delete();
      }
    } catch (e) {
      debugPrint('FileMentionsCache.clearAll failed: $e');
    }
  }
}

List<String> _splitLines(String body) {
  if (body.isEmpty) return const [];
  return body.split('\n').where((s) => s.isNotEmpty).toList(growable: false);
}
