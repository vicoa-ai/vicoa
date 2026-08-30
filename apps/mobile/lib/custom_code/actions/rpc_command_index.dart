// Typed wrapper around `ws_client.callRpc('scan-commands', ...)` — the live
// slash-command/skill index. Counterpart to `rpc_file_index.dart`'s
// `scan-files` for the composer's `/` menu: reads the machine's current
// ~/.claude, ~/.codex and ~/.agents dirs instead of the copy the CLI synced
// into the DB at session start.
//
// Reuses `RpcCaller` from `rpc_file_index.dart`. An empty result is a valid
// answer here (an agent may have no custom commands), so unlike scan-files
// there are no authoritative disk-error codes to honor — every failure falls
// back to the DB copy in `fetch_slash_commands.dart`.

import '/constants/slash_commands.dart';
import 'rpc_file_index.dart' show RpcCaller;

class CommandIndexException implements Exception {
  CommandIndexException(this.code);
  final String code;

  @override
  String toString() => 'CommandIndexException($code)';
}

/// One `scan-commands` reply. [commands] is null when the daemon answered
/// `unchanged` — the caller's `knownHash` still matches, so it should keep
/// what it already has rather than rebuilding an identical list.
class CommandIndexResult {
  CommandIndexResult({required this.hash, this.commands});

  final String hash;
  final List<SlashCommand>? commands;

  bool get unchanged => commands == null;
}

Future<CommandIndexResult> rpcScanCommands({
  required RpcCaller call,
  required String machineId,
  required String agentType,
  String? cwd,
  String? knownHash,
}) async {
  final result = await call(machineId, 'scan-commands', {
    'agent_type': agentType,
    if (cwd != null && cwd.isNotEmpty) 'cwd': cwd,
    if (knownHash != null && knownHash.isNotEmpty) 'known_hash': knownHash,
  });
  final err = result['error'];
  if (err is String) throw CommandIndexException(err);
  if (result['unchanged'] == true) {
    return CommandIndexResult(hash: result['hash'] as String? ?? '');
  }
  final raw = result['commands'];
  final commands = <SlashCommand>[];
  if (raw is List) {
    for (final entry in raw) {
      if (entry is Map) {
        commands.add(SlashCommand.fromMap(Map<String, dynamic>.from(entry)));
      }
    }
  }
  return CommandIndexResult(
    hash: result['hash'] as String? ?? '',
    commands: commands,
  );
}
