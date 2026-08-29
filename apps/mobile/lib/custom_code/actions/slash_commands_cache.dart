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

import '/constants/slash_commands.dart';

/// Per-agent-type cache for the slash-commands list.
///
/// Two layers:
///   * **Memory** — populated on first read/write within a session; subsequent
///     chat opens for the same agent type skip even the async hop and avoid
///     the SlashCommand object-build loop entirely.
///   * **Disk** — TSV file (`command\tdescription` per line) persisted across
///     sessions. Reading + splitting runs in a background isolate so a large
///     custom-command list (~600+ entries) doesn't stutter the chat scroll on
///     the first open after an app restart.
///
/// Only the API-fetched *custom* commands are cached — defaults live in code
/// (`_getDefaultSlashCommandsForInstance`) and are merged in by the caller.
class SlashCommandsCache {
  SlashCommandsCache._();
  static final SlashCommandsCache instance = SlashCommandsCache._();

  final Map<String, List<SlashCommand>> _memCache = {};

  String _normalize(String agentType) => agentType.trim().toLowerCase();

  Future<Directory> _cacheDir() async {
    final base = await getApplicationCacheDirectory();
    final dir = Directory('${base.path}/slash_commands');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  Future<File> _fileFor(String agentType) async {
    final dir = await _cacheDir();
    final key = base64Url.encode(utf8.encode(_normalize(agentType)));
    return File('${dir.path}/$key.tsv');
  }

  /// Sidecar holding the daemon's `scan-commands` index hash for [agentType].
  /// A match lets the daemon reply `unchanged` instead of resending the list.
  Future<File> _hashFileFor(String agentType) async {
    final dir = await _cacheDir();
    final key = base64Url.encode(utf8.encode(_normalize(agentType)));
    return File('${dir.path}/$key.hash');
  }

  /// The `known_hash` to send with the next `scan-commands`, or null if unknown.
  Future<String?> readHash(String agentType) async {
    try {
      final file = await _hashFileFor(agentType);
      if (!await file.exists()) return null;
      final hash = (await file.readAsString()).trim();
      return hash.isEmpty ? null : hash;
    } catch (e) {
      debugPrint('SlashCommandsCache.readHash failed: $e');
      return null;
    }
  }

  /// Record the index hash without rewriting the list — used on `unchanged`,
  /// and to reset the staleness clock that [ageOnDisk] reads.
  Future<void> touch(String agentType, {String? hash}) async {
    try {
      if (hash != null && hash.isNotEmpty) {
        await (await _hashFileFor(agentType)).writeAsString(hash);
      }
      final file = await _fileFor(agentType);
      if (await file.exists()) {
        await file.setLastModified(DateTime.now());
      }
    } catch (e) {
      debugPrint('SlashCommandsCache.touch failed: $e');
    }
  }

  /// Synchronous memory lookup — used to short-circuit a full async cache
  /// read when the agent type has already been resolved this session.
  List<SlashCommand>? readFromMemory(String agentType) =>
      _memCache[_normalize(agentType)];

  /// Whether a cache entry exists (memory or disk).
  Future<bool> exists(String agentType) async {
    if (_memCache.containsKey(_normalize(agentType))) return true;
    try {
      final file = await _fileFor(agentType);
      return await file.exists();
    } catch (_) {
      return false;
    }
  }

  /// How long ago the on-disk cache for [agentType] was last written, or
  /// `null` if there is no entry. Memory-only entries (no disk file yet)
  /// also return `null`. Used to decide whether to kick off a background
  /// refresh on chat open.
  Future<Duration?> ageOnDisk(String agentType) async {
    try {
      final file = await _fileFor(agentType);
      if (!await file.exists()) return null;
      final stat = await file.stat();
      return DateTime.now().difference(stat.modified);
    } catch (e) {
      debugPrint('SlashCommandsCache.ageOnDisk failed: $e');
      return null;
    }
  }

  /// Returns the cached custom-command list (commands + skills), or `null` if
  /// there is no entry. This is what the `/` menu reads.
  Future<List<SlashCommand>?> read(String agentType) async {
    final key = _normalize(agentType);
    final mem = _memCache[key];
    if (mem != null) return mem;
    try {
      final file = await _fileFor(agentType);
      if (!await file.exists()) return null;
      final body = await file.readAsString();
      final parsed = await compute(_parseTsv, body);
      _memCache[key] = parsed;
      return parsed;
    } catch (e) {
      debugPrint('SlashCommandsCache.read failed: $e');
      return null;
    }
  }

  /// Cached plain commands only (kind == 'command'). Split accessor over the
  /// same kind-tagged store as [readSkills].
  Future<List<SlashCommand>?> readCommands(String agentType) async {
    final all = await read(agentType);
    return all?.where((c) => !c.isSkill).toList();
  }

  /// Cached skills only (kind == 'skill'). Lets a future Skills tab read the
  /// installed skills without the command list. Backward compatible: derived
  /// from the same store, so an old cache (all 'command') yields an empty list.
  Future<List<SlashCommand>?> readSkills(String agentType) async {
    final all = await read(agentType);
    return all?.where((c) => c.isSkill).toList();
  }

  /// Synchronous skills lookup from memory, or `null` if not loaded this
  /// session. The Skills-tab counterpart of [readFromMemory].
  List<SlashCommand>? readSkillsFromMemory(String agentType) =>
      _memCache[_normalize(agentType)]?.where((c) => c.isSkill).toList();

  Future<void> write(String agentType, List<SlashCommand> commands,
      {String? hash}) async {
    final key = _normalize(agentType);
    _memCache[key] = commands;
    try {
      final file = await _fileFor(agentType);
      // Columns: command \t description \t kind \t insert. Older files with
      // only the first two columns are still read (see [_parseTsv]).
      final body = commands.map((c) {
        final desc = c.description.replaceAll('\n', ' ').replaceAll('\t', ' ');
        final insert = (c.insert ?? '').replaceAll('\n', ' ').replaceAll('\t', ' ');
        return '${c.command}\t$desc\t${c.kind}\t$insert';
      }).join('\n');
      await file.writeAsString(body);
      // Keep the hash sidecar in lockstep with the list it describes: only an
      // RPC fetch carries a hash. A REST/DB write clears it so a later
      // `scan-commands` can't wrongly match a stale daemon hash and reply
      // `unchanged` against a list that didn't come from that daemon.
      final hashFile = await _hashFileFor(agentType);
      if (hash != null && hash.isNotEmpty) {
        await hashFile.writeAsString(hash);
      } else if (await hashFile.exists()) {
        await hashFile.delete();
      }
    } catch (e) {
      debugPrint('SlashCommandsCache.write failed: $e');
    }
  }

  /// Clears memory cache and deletes every on-disk entry. Call on debug reset
  /// so the next chat open re-fetches from the backend.
  Future<void> clearAll() async {
    _memCache.clear();
    try {
      final dir = await _cacheDir();
      await for (final entity in dir.list()) {
        if (entity is File) await entity.delete();
      }
    } catch (e) {
      debugPrint('SlashCommandsCache.clearAll failed: $e');
    }
  }
}

/// Top-level so it can be invoked through [compute].
///
/// Tolerates both the legacy 2-column format (`command\tdescription`) and the
/// current 4-column one (`command\tdescription\tkind\tinsert`); a missing kind
/// defaults to 'command' and a blank insert to null.
List<SlashCommand> _parseTsv(String body) {
  if (body.isEmpty) return const [];
  final lines = body.split('\n');
  final result = <SlashCommand>[];
  for (final line in lines) {
    if (line.isEmpty) continue;
    final parts = line.split('\t');
    final command = parts.isNotEmpty ? parts[0] : '';
    if (command.isEmpty) continue;
    final description = parts.length > 1 ? parts[1] : '';
    final kind = parts.length > 2 && parts[2] == 'skill' ? 'skill' : 'command';
    final insert = parts.length > 3 && parts[3].isNotEmpty ? parts[3] : null;
    result.add(SlashCommand(
      command: command,
      description: description,
      source: 'custom',
      kind: kind,
      insert: insert,
    ));
  }
  return result;
}
