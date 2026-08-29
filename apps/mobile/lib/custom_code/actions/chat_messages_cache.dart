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

/// Per-instance disk cache for chat messages.
///
/// Replaces the old monolithic `ff_cachedChatMessages` SharedPreferences blob
/// that re-encoded every chat (~MBs) on every WS message arrival, blocking
/// the UI for 30–50 ms each time. With one file per instance, a write only
/// re-encodes that one chat's messages (~5–10 ms), and per-instance debounce
/// coalesces WS-burst writes into a single flush.
///
/// Memory is the source of truth during a session — disk is just persistence
/// across app restarts. `getSync` returns memory entries synchronously and
/// kicks off a background disk load on a miss (the first access to a chat
/// after a cold start).
class ChatMessagesCache {
  ChatMessagesCache._();
  static final ChatMessagesCache instance = ChatMessagesCache._();

  // Session-wide memory cache — sync reads/writes.
  final Map<String, List<dynamic>> _mem = {};
  // Per-instance debounce timers. A burst of WS-arrival writes for the same
  // chat collapses into a single disk flush.
  final Map<String, Timer> _flushTimers = {};
  // Per-instance guards so concurrent getSync() calls for the same chat
  // don't fan out into multiple disk reads.
  final Set<String> _loading = {};
  // Listeners notified when a lazy disk load completes — gives a widget that
  // hit the empty-memory path a chance to re-render once the data lands.
  final Map<String, List<VoidCallback>> _loadCompleteCallbacks = {};

  // Debounce window for flushes. WS bursts during active agent runs hit
  // this code at ~3 msg/s; 1.5 s coalesces those into one I/O.
  static const Duration _flushDebounce = Duration(milliseconds: 1500);

  Future<Directory> _cacheDir() async {
    final base = await getApplicationCacheDirectory();
    final dir = Directory('${base.path}/chat_messages');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  Future<File> _fileFor(String instanceId) async {
    final dir = await _cacheDir();
    // base64Url so the instance id (which contains characters like `-`) is
    // unambiguously filesystem-safe across platforms.
    final key = base64Url.encode(utf8.encode(instanceId));
    return File('${dir.path}/$key.json');
  }

  /// Sync access — memory hit returns immediately. Memory miss returns an
  /// empty list and kicks off a background disk read; pass [onLoaded] to
  /// be notified when the disk-loaded data is in memory.
  List<dynamic> getSync(String instanceId, {VoidCallback? onLoaded}) {
    final mem = _mem[instanceId];
    if (mem != null) return mem;
    if (onLoaded != null) {
      _loadCompleteCallbacks
          .putIfAbsent(instanceId, () => <VoidCallback>[])
          .add(onLoaded);
    }
    if (!_loading.contains(instanceId)) {
      _loading.add(instanceId);
      unawaited(_loadFromDisk(instanceId));
    }
    return const [];
  }

  Future<void> _loadFromDisk(String instanceId) async {
    try {
      final file = await _fileFor(instanceId);
      if (!await file.exists()) return;
      final body = await file.readAsString();
      final decoded = await compute(jsonDecode, body);
      if (decoded is List) {
        _mem[instanceId] = decoded;
        final callbacks = _loadCompleteCallbacks.remove(instanceId);
        if (callbacks != null) {
          for (final cb in callbacks) {
            try {
              cb();
            } catch (e) {
              debugPrint('ChatMessagesCache: onLoaded callback threw: $e');
            }
          }
        }
      }
    } catch (e) {
      debugPrint(
          'ChatMessagesCache: disk load failed for $instanceId: $e');
    } finally {
      _loading.remove(instanceId);
    }
  }

  /// Update memory immediately (cheap, sync) and schedule a debounced disk
  /// flush so a burst of in-place message updates from the agent collapses
  /// to one I/O.
  void set(String instanceId, List<dynamic> messages) {
    _mem[instanceId] = messages;
    _scheduleFlush(instanceId);
  }

  void _scheduleFlush(String instanceId) {
    _flushTimers[instanceId]?.cancel();
    _flushTimers[instanceId] = Timer(_flushDebounce, () {
      _flushTimers.remove(instanceId);
      unawaited(_flush(instanceId));
    });
  }

  Future<void> _flush(String instanceId) async {
    try {
      final messages = _mem[instanceId];
      if (messages == null) return;
      // jsonEncode in an isolate so a large chat (~100s of messages) doesn't
      // block the UI thread on encode. The encoded payload is also returned
      // off-thread, so the only main-isolate work is the file write call.
      final encoded = await compute<Object, String>(jsonEncode, messages);
      final file = await _fileFor(instanceId);
      await file.writeAsString(encoded);
    } catch (e) {
      debugPrint('ChatMessagesCache: flush failed for $instanceId: $e');
    }
  }

  void delete(String instanceId) {
    _mem.remove(instanceId);
    _flushTimers.remove(instanceId)?.cancel();
    unawaited(_deleteDisk(instanceId));
  }

  Future<void> _deleteDisk(String instanceId) async {
    try {
      final file = await _fileFor(instanceId);
      if (await file.exists()) await file.delete();
    } catch (e) {
      debugPrint(
          'ChatMessagesCache: disk delete failed for $instanceId: $e');
    }
  }

  /// Wipe every cached chat — memory and disk — for the logout / account
  /// deletion flows, so the next account on this device never reads the
  /// previous user's transcripts. Cancels pending flushes first so an
  /// in-flight debounce can't re-create a file after the directory is
  /// removed.
  Future<void> wipeAll() async {
    for (final timer in _flushTimers.values) {
      timer.cancel();
    }
    _flushTimers.clear();
    _mem.clear();
    _loading.clear();
    _loadCompleteCallbacks.clear();
    try {
      final base = await getApplicationCacheDirectory();
      final dir = Directory('${base.path}/chat_messages');
      if (await dir.exists()) await dir.delete(recursive: true);
    } catch (e) {
      debugPrint('ChatMessagesCache: wipeAll failed: $e');
    }
  }

  /// One-time migration entry-point — seeds the memory cache with the
  /// contents of the old monolithic `ff_cachedChatMessages` blob and
  /// schedules staggered per-instance flushes so the new disk layout is
  /// populated in the background.
  void seedMemoryFromMap(Map<String, List<dynamic>> initial) {
    _mem.addAll(initial);
    // Stagger flush start times so we don't spawn many compute() isolates
    // simultaneously. 100 ms between starts keeps memory pressure bounded.
    var delay = _flushDebounce;
    for (final id in initial.keys) {
      _flushTimers[id]?.cancel();
      _flushTimers[id] = Timer(delay, () {
        _flushTimers.remove(id);
        unawaited(_flush(id));
      });
      delay += const Duration(milliseconds: 100);
    }
  }
}
