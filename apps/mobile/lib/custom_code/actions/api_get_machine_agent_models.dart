// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// GET /machines/{id}/agent-models — the machine's cached, real per-agent model
/// lists (populated once an ACP agent has run there once). Lets the new-session
/// picker show real models before a session starts. Returns
/// `{agentId: [{id,label}]}`; empty map on any error or when nothing is cached
/// yet, so the caller cleanly falls back to the static catalog defaults.
Future<Map<String, List<Map<String, String>>>> apiGetMachineAgentModels(
    String machineId) async {
  final out = <String, List<Map<String, String>>>{};
  try {
    final result = await vicoaApiRequest(
        'get', '/api/v1/machines/$machineId/agent-models', null);
    final agentModels = (result is Map) ? result['agent_models'] : null;
    if (agentModels is Map) {
      agentModels.forEach((agent, models) {
        if (models is List) {
          out[agent.toString()] = [
            for (final m in models)
              if (m is Map && m['id'] != null)
                {
                  'id': m['id'].toString(),
                  'label': (m['label'] ?? m['id']).toString(),
                },
          ];
        }
      });
    }
  } catch (e) {
    debugPrint('apiGetMachineAgentModels($machineId): $e');
  }
  return out;
}
