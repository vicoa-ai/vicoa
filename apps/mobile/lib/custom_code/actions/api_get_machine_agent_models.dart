// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// A machine's cached per-agent lists from GET /machines/{id}/agent-models:
/// real model lists (populated once an ACP agent has run there, or once the
/// desktop's Providers page Checked/Added it) and, for agents whose source
/// reported them, ACP session modes. Both `{agentId: [{id,label}]}`; both
/// empty on any error or when nothing is cached yet, so the caller cleanly
/// falls back to the static catalog defaults.
class MachineAgentModelsCache {
  const MachineAgentModelsCache({this.models = const {}, this.modes = const {}});
  final Map<String, List<Map<String, String>>> models;
  final Map<String, List<Map<String, String>>> modes;
  bool get isEmpty => models.isEmpty && modes.isEmpty;
}

Map<String, List<Map<String, String>>> _parseEntryLists(dynamic raw) {
  final out = <String, List<Map<String, String>>>{};
  if (raw is! Map) return out;
  raw.forEach((agent, entries) {
    if (entries is List) {
      out[agent.toString()] = [
        for (final m in entries)
          if (m is Map && m['id'] != null)
            {
              'id': m['id'].toString(),
              'label': (m['label'] ?? m['id']).toString(),
            },
      ];
    }
  });
  return out;
}

/// GET /machines/{id}/agent-models — see [MachineAgentModelsCache]. Lets the
/// new-session picker show real models (and modes) before a session starts.
Future<MachineAgentModelsCache> apiGetMachineAgentModels(String machineId) async {
  try {
    final result = await vicoaApiRequest(
        'get', '/api/v1/machines/$machineId/agent-models', null);
    if (result is Map) {
      return MachineAgentModelsCache(
        models: _parseEntryLists(result['agent_models']),
        modes: _parseEntryLists(result['agent_modes']),
      );
    }
  } catch (e) {
    debugPrint('apiGetMachineAgentModels($machineId): $e');
  }
  return const MachineAgentModelsCache();
}
