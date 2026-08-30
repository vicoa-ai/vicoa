// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

// `RpcException` is not re-exported by the index.dart barrel; pull it from its
// own file to read the wire error code. Same pattern as fetch_slash_commands.
import 'ws_client.dart' show RpcException;

/// Spawn a remote session on a machine over WebSocket RPC (websocket-migration
/// §2.8, Phase 5). The call resolves once the daemon has launched the agent —
/// there is no spawn-request row to poll. The optional [prompt] travels in
/// `metadata` because that is how the daemon's command builder consumes it.
///
/// Pass [worktree] as `{'new': true}` to have the daemon fork a fresh branch +
/// checkout off [directory]'s HEAD and run the agent there; the daemon computes
/// the path and returns it as `worktreePath`/`branch`. Omit for today's
/// spawn-in-[directory] behavior.
///
/// Returns `{success: true, agentInstanceId, machineId, worktreePath?, branch?}`
/// on success, or `{success: false, error}` on failure.
Future<Map<String, dynamic>> apiSpawnSession(
  String machineId,
  String directory, {
  String agent = 'claude',
  String prompt = '',
  Map<String, dynamic>? extraMetadata,
  Map<String, dynamic>? worktree,
}) async {
  try {
    final trimmedPrompt = prompt.trim();
    final metadata = <String, dynamic>{
      if (trimmedPrompt.isNotEmpty) 'prompt': trimmedPrompt,
      if (extraMetadata != null) ...extraMetadata,
    };
    // `prompt` from extraMetadata should not clobber the trimmed value above
    // — re-apply after the spread so the explicit prompt wins (or drop it
    // entirely if the user submitted blank, so the daemon omits --prompt and
    // the session starts empty waiting for input).
    if (trimmedPrompt.isNotEmpty) {
      metadata['prompt'] = trimmedPrompt;
    } else {
      metadata.remove('prompt');
    }

    final result = await VicoaWsClient.instance.callRpc(
      machineId,
      'spawn-session',
      {
        'directory': directory,
        'agent': agent,
        'metadata': metadata,
        if (worktree != null) 'worktree': worktree,
      },
    );

    if (result['error'] != null) {
      return {'success': false, 'error': result['error'].toString()};
    }

    return {
      'success': true,
      'agentInstanceId': result['agent_instance_id'],
      'machineId': machineId,
      // Present only when the daemon created a worktree — for immediate display.
      if (result['worktree_path'] != null) 'worktreePath': result['worktree_path'],
      if (result['branch'] != null) 'branch': result['branch'],
    };
  } on RpcException catch (e) {
    // Pass the wire code through as `errorCode` so the UI can show friendly
    // guidance (rpc_error_messages.dart) and mark the machine offline locally,
    // instead of dumping the raw `RpcException(no_handler)` string on the user.
    debugPrint('Error spawning remote session: $e');
    return {'success': false, 'error': e.toString(), 'errorCode': e.code};
  } catch (e) {
    debugPrint('Error spawning remote session: $e');
    return {'success': false, 'error': e.toString()};
  }
}
