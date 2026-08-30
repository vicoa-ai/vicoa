// Automatic FlutterFlow imports
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Client-side cache of the user's `user_agents` list.
///
/// `agent_instances` broadcasts carry the canonical row only (websocket-
/// migration plan §2.4), without joined presentation fields such as
/// `agent_type_name`. The home list, session info sheet, agent chat header,
/// and slash-command lookup all need that name. The fix is the §2.4 intent —
/// "client composes presentation fields itself" — backed by a local cache
/// keyed by `user_agent_id`.
///
/// Cache backing: `FFAppState.cachedAgents` (persisted to SharedPreferences).
/// That field existed for an older home-page caching scheme that was removed
/// in commit 53358b7; we reactivate it here for the WS-enrich use case.
///
/// Freshness:
///   - cold start: deserialized from prefs (handled by FFAppState init)
///   - every WS handshake (server_info): a background refresh fires
///   - cache miss (unknown user_agent_id): an inline refresh fires, deduped
///   - logout: cleared by FFAppState.clearAllUserData
class UserAgentsCache {
  UserAgentsCache._();
  static final UserAgentsCache instance = UserAgentsCache._();

  Future<void>? _pendingRefresh;

  /// Synchronous lookup. Returns `null` on miss.
  String? lookupName(String? userAgentId) {
    if (userAgentId == null || userAgentId.isEmpty) return null;
    for (final entry in FFAppState().cachedAgents) {
      if (entry is Map && entry['id']?.toString() == userAgentId) {
        final name = entry['name'];
        if (name is String && name.isNotEmpty) return name;
        return null;
      }
    }
    return null;
  }

  /// Sync lookup first; on miss, fire a (deduped) refresh and look up again.
  /// Caller is responsible for ordering — the result reflects the post-refresh
  /// cache so a freshly-created `user_agent` (e.g. created on web seconds ago)
  /// becomes resolvable without an app restart.
  Future<String?> lookupOrRefreshName(String? userAgentId) async {
    final hit = lookupName(userAgentId);
    if (hit != null) return hit;
    await refresh();
    return lookupName(userAgentId);
  }

  /// Refresh the cache from `/api/v1/user-agents`. Concurrent callers share
  /// one in-flight request to avoid stampedes (e.g. several `instance-created`
  /// events for unknown agents arriving back-to-back).
  Future<void> refresh() {
    return _pendingRefresh ??= _doRefresh().whenComplete(() {
      _pendingRefresh = null;
    });
  }

  Future<void> _doRefresh() async {
    try {
      final agents = await apiGetAgents();
      FFAppState().cachedAgents = agents;
      FFAppState().cachedAgentsTimestamp = DateTime.now();
    } on AuthenticationException {
      // Auth issue — leave the existing cache in place; the user will hit a
      // sign-in flow soon enough and the next handshake refresh will retry.
    } catch (e) {
      debugPrint('[user-agents] refresh failed: $e');
    }
  }
}
