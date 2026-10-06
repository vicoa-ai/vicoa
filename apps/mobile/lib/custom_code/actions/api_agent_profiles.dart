import 'package:flutter/foundation.dart';

import 'index.dart';

/// REST client for the caller's saved agents (`/api/v1/agents`). Read-only on
/// mobile: agents are created and edited on the web; the app only offers them
/// where a run can use one (the automation editor's Agent picker).

/// GET /api/v1/agents → the saved agents the caller may run (their own and
/// their teams'), archived ones excluded. Returns null on failure so the caller
/// can tell "error" from "none yet".
Future<List<dynamic>?> apiListAgentProfiles() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/agents', null);
    if (result is List) return List<dynamic>.from(result);
    return null;
  } catch (e) {
    debugPrint('Error fetching agents: $e');
    return null;
  }
}

/// GET /api/v1/teams → the caller's teams, used only to name the team groups
/// in the agent picker. Returns null on failure.
Future<List<dynamic>?> apiListTeams() async {
  try {
    final result = await vicoaApiRequest('get', '/api/v1/teams', null);
    if (result is List) return List<dynamic>.from(result);
    return null;
  } catch (e) {
    debugPrint('Error fetching teams: $e');
    return null;
  }
}
