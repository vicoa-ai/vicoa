import 'package:flutter/foundation.dart';

import 'index.dart';

/// REST client for /api/v1/automations (scheduled agent runs). Mirrors the
/// web dashboard's backend-api.ts automation methods; the server owns all
/// next-run computation — the app only reads/writes the stored schedule.

/// GET /api/v1/automations → list of automation maps (created_at DESC).
/// Returns null on failure so the caller can distinguish "error" from "empty".
Future<List<dynamic>?> apiGetAutomations() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/automations', null);
    if (result is List) return List<dynamic>.from(result);
    return null;
  } catch (e) {
    debugPrint('Error fetching automations: $e');
    return null;
  }
}

/// POST /api/v1/automations. [body] is a CreateAutomationRequest map.
/// Returns the created automation, or null on failure.
Future<Map<String, dynamic>?> apiCreateAutomation(
    Map<String, dynamic> body) async {
  try {
    final result = await vicoaApiRequest('post', '/api/v1/automations', body);
    if (result is Map) return Map<String, dynamic>.from(result);
    return null;
  } catch (e) {
    debugPrint('Error creating automation: $e');
    return null;
  }
}

/// PATCH /api/v1/automations/{id}. Partial update — only the keys present in
/// [body] are applied (toggling `enabled` alone does not recompute the
/// schedule server-side). Returns the updated automation, or null on failure.
Future<Map<String, dynamic>?> apiUpdateAutomation(
    String automationId, Map<String, dynamic> body) async {
  try {
    final result = await vicoaApiRequest(
        'patch', '/api/v1/automations/$automationId', body);
    if (result is Map) return Map<String, dynamic>.from(result);
    return null;
  } catch (e) {
    debugPrint('Error updating automation: $e');
    return null;
  }
}

/// DELETE /api/v1/automations/{id}. The endpoint returns 204 No Content; the
/// shared request helper flags an empty body as an error, so a *successful*
/// delete still lands in the catch below — detect that case and report success.
Future<bool> apiDeleteAutomation(String automationId) async {
  try {
    await vicoaApiRequest('delete', '/api/v1/automations/$automationId', null);
    return true;
  } catch (e) {
    if (e.toString().contains('Empty response')) return true;
    debugPrint('Error deleting automation: $e');
    return false;
  }
}

/// GET /api/v1/automations/{id}/runs → run history (fired_at DESC, limit 50).
Future<List<dynamic>> apiGetAutomationRuns(String automationId) async {
  try {
    final result = await vicoaApiRequest(
        'get', '/api/v1/automations/$automationId/runs', null);
    if (result is List) return List<dynamic>.from(result);
    return [];
  } catch (e) {
    debugPrint('Error fetching automation runs: $e');
    return [];
  }
}

/// POST /api/v1/automations/{id}/run — records the outcome of a client-side
/// "Run now" (it does NOT dispatch; the app spawns the session itself first).
/// [status] is one of fired | missed_offline | failed | skipped.
Future<Map<String, dynamic>?> apiRecordAutomationRun(
  String automationId, {
  required String status,
  String? agentInstanceId,
  String? detail,
}) async {
  try {
    final result = await vicoaApiRequest(
      'post',
      '/api/v1/automations/$automationId/run',
      <String, dynamic>{
        'status': status,
        if (agentInstanceId != null) 'agent_instance_id': agentInstanceId,
        if (detail != null) 'detail': detail,
      },
    );
    if (result is Map) return Map<String, dynamic>.from(result);
    return null;
  } catch (e) {
    debugPrint('Error recording automation run: $e');
    return null;
  }
}
