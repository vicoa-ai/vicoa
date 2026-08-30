// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter/foundation.dart';

import '/constants/slash_commands.dart';
// `rpcScanCommands`/`CommandIndexException` come via the `index.dart` barrel;
// `RpcCaller` is not re-exported there, so pull it from its own file.
import 'rpc_file_index.dart' show RpcCaller;
// Direct import, not via index.dart: this needs `RpcException` to tell a
// too-old daemon (`no_handler`) apart from a transient drop. Same pattern as
// `fetch_file_mentions.dart`.
import 'ws_client.dart';

/// Source selection for the custom slash-command / skill index.
///
/// Prefers the live daemon index (`scan-commands`) so a skill installed
/// mid-session shows up without a restart, and falls back to the CLI-synced
/// copy in Postgres when the machine is unknown, offline, or too old to serve
/// it. Only Claude sessions write that DB copy today, so for Codex the RPC is
/// the only source of custom commands — but the fallback is still load-bearing
/// for the common no-machine / asleep-laptop case.
enum SlashCommandsSource { rpc, rest }

class SlashCommandsFetch {
  const SlashCommandsFetch({
    required this.source,
    this.commands,
    this.hash,
  });

  final SlashCommandsSource source;

  /// Null means "keep what you have" — the daemon matched [hash] against the
  /// caller's `knownHash` and skipped resending an identical list.
  final List<SlashCommand>? commands;
  final String? hash;

  bool get unchanged => commands == null;
}

/// Machines whose daemon predates `scan-commands`. Skips the RPC — and the
/// server's 3s no-handler grace window — on every later `/` for that machine.
/// Process-lifetime only: a daemon upgrade takes effect on the next app launch.
final Set<String> _withoutCommandIndex = <String>{};

@visibleForTesting
void resetCommandIndexSupport() => _withoutCommandIndex.clear();

/// Convert the REST/DB response (a list of `{name, description, kind, insert}`
/// maps) into [SlashCommand]s.
List<SlashCommand> _decodeRest(List<dynamic> raw) {
  final result = <SlashCommand>[];
  for (final entry in raw) {
    if (entry is Map<String, dynamic>) {
      result.add(SlashCommand.fromMap(entry));
    } else if (entry is Map) {
      result.add(SlashCommand.fromMap(Map<String, dynamic>.from(entry)));
    }
  }
  return result;
}

/// Resolve the custom command index for [agentType], preferring the live
/// daemon. Never throws for a transport failure — it degrades to the DB copy.
Future<SlashCommandsFetch> fetchSlashCommands({
  required String agentType,
  String? machineId,
  String? projectPath,
  String? knownHash,
  RpcCaller? call,
}) async {
  final rpcCall = call ?? VicoaWsClient.instance.callRpc;
  final canTryRpc = machineId != null &&
      machineId.isNotEmpty &&
      !_withoutCommandIndex.contains(machineId);

  if (canTryRpc) {
    try {
      final result = await rpcScanCommands(
        call: rpcCall,
        machineId: machineId,
        agentType: agentType,
        cwd: projectPath,
        knownHash: knownHash,
      );
      return SlashCommandsFetch(
        source: SlashCommandsSource.rpc,
        commands: result.commands,
        hash: result.hash,
      );
    } on CommandIndexException catch (e) {
      // An empty result is a valid answer, not an error, so scan-commands has
      // no authoritative codes; any error just means "try the DB instead".
      debugPrint('scan-commands returned ${e.code}; using the DB copy');
    } on RpcException catch (e) {
      if (e.code == 'no_handler') {
        _withoutCommandIndex.add(machineId);
      }
      debugPrint('scan-commands unavailable (${e.code}); using the DB copy');
    } catch (e) {
      debugPrint('scan-commands failed ($e); falling back to the DB copy');
    }
  }

  final raw = await apiGetSlashCommands(agentType);
  return SlashCommandsFetch(
    source: SlashCommandsSource.rest,
    commands: _decodeRest(raw),
  );
}
