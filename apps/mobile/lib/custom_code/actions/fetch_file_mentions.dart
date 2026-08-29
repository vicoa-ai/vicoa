// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter/foundation.dart';

import 'rpc_file_index.dart';
// Direct import, not via index.dart: that barrel re-exports only
// `VicoaWsClient`, and this needs `RpcException` to tell a too-old daemon
// (`no_handler`) apart from a transient drop. Same pattern as
// `files_tab_model.dart` importing `rpc_files.dart`.
import 'ws_client.dart';

/// Source selection for the `@`-mention file index.
/// See `plans/todos/file-mentions-live-rpc.md` §Phase 3.
///
/// Prefers the live daemon index (`scan-files`) so files the agent just
/// created are mentionable, and falls back to the CLI-synced copy in Postgres
/// when the machine is unknown, offline, or too old to serve it. That fallback
/// is load-bearing, not a safety net: roughly a third of recent sessions carry
/// no `machine_id` at all, and a phone is usually reaching for a laptop that
/// is asleep.
enum FileMentionsSource { rpc, rest }

class FileMentionsFetch {
  const FileMentionsFetch({
    required this.source,
    this.files,
    this.hash,
  });

  final FileMentionsSource source;

  /// Null means "keep what you have" — the daemon matched [hash] against the
  /// caller's `knownHash` and skipped resending an identical list.
  final List<String>? files;
  final String? hash;

  bool get unchanged => files == null;
}

/// Machines whose daemon predates `scan-files`. Skips the RPC — and the
/// server's 3s no-handler grace window — on every later mention for that
/// machine. Process-lifetime only: a daemon upgrade takes effect on the next
/// app launch rather than needing a cache bust.
final Set<String> _withoutFileIndex = <String>{};

/// Daemon-reported errors about its own disk. The daemon is authoritative
/// here, so these do NOT fall back to the (possibly stale) DB copy — the path
/// really is gone on that machine.
const _authoritativeCodes = {
  'path_not_found',
  'not_a_directory',
  'permission_denied',
};

@visibleForTesting
void resetFileIndexSupport() => _withoutFileIndex.clear();

/// Resolve the file index for [projectPath], preferring the live daemon.
///
/// [call] defaults to the shared WS client; tests inject a fake. Never throws
/// for a transport failure — it degrades to the DB copy, and to an empty list
/// only when both sources have nothing.
Future<FileMentionsFetch> fetchFileMentions({
  required String projectPath,
  String? machineId,
  String? knownHash,
  RpcCaller? call,
}) async {
  final rpcCall = call ?? VicoaWsClient.instance.callRpc;
  final canTryRpc = machineId != null &&
      machineId.isNotEmpty &&
      !_withoutFileIndex.contains(machineId);

  if (canTryRpc) {
    try {
      final result = await rpcScanFiles(
        call: rpcCall,
        machineId: machineId,
        cwd: projectPath,
        knownHash: knownHash,
      );
      return FileMentionsFetch(
        source: FileMentionsSource.rpc,
        files: result.files,
        hash: result.hash,
      );
    } on FileIndexException catch (e) {
      if (_authoritativeCodes.contains(e.code)) {
        return const FileMentionsFetch(
          source: FileMentionsSource.rpc,
          files: <String>[],
        );
      }
      debugPrint('scan-files returned ${e.code}; falling back to the DB copy');
    } on RpcException catch (e) {
      if (e.code == 'no_handler') {
        // Daemon is too old. Remember, so no later `@` pays the grace window.
        _withoutFileIndex.add(machineId);
      }
      debugPrint('scan-files unavailable (${e.code}); using the DB copy');
    } catch (e) {
      debugPrint('scan-files failed ($e); falling back to the DB copy');
    }
  }

  final files = await apiGetFileMentions(projectPath);
  return FileMentionsFetch(source: FileMentionsSource.rest, files: files);
}
