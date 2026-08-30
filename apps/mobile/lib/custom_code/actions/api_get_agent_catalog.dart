// Automatic FlutterFlow imports
import '/backend/agent_catalog.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Fetch the per-agent catalog from the backend.
///
/// Falls back to the baked-in catalog (`agentCatalogFallback()`) on any
/// HTTP failure so the new-session sheet always has something to render.
/// Plan §3.11 / §7.1: SWR semantics live in the calling model layer.
Future<AgentCatalog> apiGetAgentCatalog() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/agent-catalog', null);
    if (result is Map) {
      return AgentCatalog.fromJson(Map<String, dynamic>.from(result));
    }
    debugPrint('apiGetAgentCatalog: unexpected response type ${result.runtimeType}');
    return agentCatalogFallback();
  } catch (e) {
    debugPrint('apiGetAgentCatalog: $e — using baked-in fallback');
    return agentCatalogFallback();
  }
}
