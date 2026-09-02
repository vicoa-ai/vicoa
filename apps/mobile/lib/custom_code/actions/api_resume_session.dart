// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

// `RpcException` is not re-exported by the index.dart barrel; pull it from its
// own file to read the wire error code. Same pattern as fetch_slash_commands.
import 'ws_client.dart' show RpcException;
// SessionConfig.toSpawnMetadata rebuilds the daemon metadata from the stored
// config so a resume keeps its model / effort / permission mode.
import '/backend/agent_catalog.dart';

/// Relaunch a stopped session on the machine it came from.
///
/// A resume is a spawn that reuses the instance id, so it rides the same
/// `spawn-session` RPC. Passing `resume` makes the daemon skip minting a new
/// id, and the wrapper reattaches to the existing row instead of registering
/// (which would 409).
///
/// [agentSessionId] is the agent's *own* conversation handle recorded by the
/// previous run (codex thread id / ACP session id). It is deliberately separate
/// from the instance id: reattaching the row always works, restoring the
/// conversation may not. When it's absent the session still comes back — just
/// without memory of the conversation, which callers should surface.
///
/// Resume is machine- and directory-bound for every agent (Claude's transcript
/// is keyed by instance id under a cwd-derived path; codex's `thread/resume`
/// takes a cwd), so it only works against the original machine while its
/// daemon is online.
///
/// Returns `{success: true, agentInstanceId, contextLost}` or
/// `{success: false, error}`.
Future<Map<String, dynamic>> apiResumeSession(
  String machineId,
  String agentInstanceId,
  String directory, {
  String agent = 'claude',
  String? agentSessionId,
  Map<String, dynamic>? sessionConfig,
}) async {
  try {
    if (machineId.isEmpty || agentInstanceId.isEmpty || directory.isEmpty) {
      return {'success': false, 'error': 'Session cannot be resumed: missing machine or folder'};
    }

    // Rebuild the daemon `metadata` from the stored config so the resumed
    // session keeps its model / thinking effort / permission mode. Without this
    // the daemon sees no metadata and falls back to its defaults (permission
    // mode `default`), so an `auto`-mode session came back running as
    // `default`. Mirrors the web's resumeSpawnMetadata (session-resume.ts).
    final metadata = (sessionConfig != null && sessionConfig.isNotEmpty)
        ? SessionConfig.fromJson({...sessionConfig, 'agent': agent}).toSpawnMetadata()
        : <String, dynamic>{};

    final result = await VicoaWsClient.instance.callRpc(
      machineId,
      'spawn-session',
      {
        'directory': directory,
        'agent': agent,
        'resume': {
          'agent_instance_id': agentInstanceId,
          if (agentSessionId != null && agentSessionId.isNotEmpty) 'agent_session_id': agentSessionId,
        },
        if (metadata.isNotEmpty) 'metadata': metadata,
      },
    );

    if (result['error'] != null) {
      return {'success': false, 'error': result['error'].toString()};
    }

    return {
      'success': true,
      'agentInstanceId': agentInstanceId,
      // Claude needs no separate handle — its transcript is keyed by the
      // instance id — so a missing handle only means lost context elsewhere.
      'contextLost': (agentSessionId == null || agentSessionId.isEmpty) && agent != 'claude',
    };
  } on RpcException catch (e) {
    // Resume guards with resumeBlockedReason up front, but the machine can go
    // offline between that check and this call — surface the wire code so the
    // caller can show friendly guidance instead of a raw RpcException.
    debugPrint('Error resuming session: $e');
    return {'success': false, 'error': e.toString(), 'errorCode': e.code};
  } catch (e) {
    debugPrint('Error resuming session: $e');
    return {'success': false, 'error': e.toString()};
  }
}

/// The agent slug the daemon expects.
///
/// [sessionConfig]'s `agent` is the catalog id recorded at spawn and is what
/// the daemon validates against, so it wins. [agentTypeName] is the UserAgent
/// row's name -- user-editable and free-form -- so deriving the slug from it
/// alone silently fell back to "claude" for any agent whose display name
/// lacked a known keyword ("kimi cli" being the reported case). That launched
/// the Claude wrapper for an ACP session, which died with "Headless Claude
/// encountered a fatal error".
String resumeAgentSlug(String? agentTypeName, {Map<String, dynamic>? sessionConfig}) {
  final configured = sessionConfig?['agent'];
  if (configured is String && configured.trim().isNotEmpty) {
    return configured.trim().toLowerCase();
  }
  final name = (agentTypeName ?? '').toLowerCase();
  if (name.contains('codex')) return 'codex';
  if (name.contains('opencode')) return 'opencode';
  if (name.contains('cursor')) return 'cursor';
  if (name.contains('gemini')) return 'gemini';
  if (name.contains('copilot')) return 'copilot';
  if (name.contains('kimi')) return 'kimi';
  if (name.contains('hermes')) return 'hermes';
  return 'claude';
}

/// The agent's prior conversation handle, if the previous run recorded one.
/// Absent is normal, not an error — older sessions predate handle capture and
/// some agents can't reload at all.
String? resumeAgentSessionHandle(Map<String, dynamic>? instanceMetadata) {
  if (instanceMetadata == null) return null;
  final codex = instanceMetadata['codex_thread_id'];
  if (codex is String && codex.isNotEmpty) return codex;
  final acp = instanceMetadata['acp_session_id'];
  if (acp is String && acp.isNotEmpty) return acp;
  return null;
}

/// Expand a stored tilde path against the session's recorded home directory.
/// `project` is stored tilde-collapsed; the daemon needs a real path.
String resumeExpandProjectPath(String project, String? homeDir) {
  if (!project.startsWith('~')) return project;
  if (homeDir == null || homeDir.isEmpty) return project;
  return homeDir.replaceAll(RegExp(r'/$'), '') + project.substring(1);
}

/// Statuses where the session is closed on purpose. Mirrors the web's
/// `CLOSED_BY_DESIGN_STATUSES` and the backend's terminal set.
const Set<String> kClosedByDesignStatuses = {'COMPLETED', 'FAILED', 'KILLED', 'DISCONNECTED'};

/// Why Resume can't run right now, or null when it can.
///
/// Mirrors `resumeBlockedReason` in vicoa-web's lib/session-resume.ts — the two
/// must agree, or the same session offers Resume on one client and refuses it
/// on the other.
String? resumeBlockedReason({
  required String? status,
  required String? machineId,
  required String? project,
  required String? liveState,
}) {
  final upper = (status ?? '').toUpperCase();
  if (upper == 'DELETED') return 'This session was deleted, so there is nothing to resume.';
  // Legacy TUI-started rows have no machine linkage — no daemon to address.
  if (machineId == null || machineId.isEmpty) return 'This session is not linked to a computer, so it cannot be resumed.';
  if (project == null || project.isEmpty) return 'This session has no recorded folder, so it cannot be resumed.';
  // Without this the app offered Resume against an offline daemon and the RPC
  // came back as no_handler, which surfaced as a raw RpcException.
  if (liveState == 'machine_offline') return 'Your computer is offline. Bring it back online to resume.';
  // A session closed on purpose is resumable straight away: its heartbeat can
  // linger for the whole online threshold while the agent shuts down, and
  // waiting that out made Resume appear minutes late.
  if (kClosedByDesignStatuses.contains(upper)) return null;
  if (liveState == 'live' || liveState == 'reconnecting') return 'This session is already running.';
  return null;
}

/// Whether Resume should appear at all. Shown (disabled, with a reason) while
/// the computer is offline — hiding it would read as "unsupported" rather than
/// "not right now".
bool canResumeSession({
  required String? status,
  required String? machineId,
  required String? project,
  required String? liveState,
}) {
  final upper = (status ?? '').toUpperCase();
  if (upper == 'DELETED') return false;
  if (machineId == null || machineId.isEmpty) return false;
  if (project == null || project.isEmpty) return false;
  if (kClosedByDesignStatuses.contains(upper)) return true;
  if (liveState == 'machine_offline') return true;
  return liveState == 'agent_stopped';
}

/// Liveness states the backend derives (shared/database/liveness.py).
/// Derived at read time from the instance + machine heartbeats, never stored.
const String kLiveStateLive = 'live';
const String kLiveStateReconnecting = 'reconnecting';
const String kLiveStateAgentStopped = 'agent_stopped';
const String kLiveStateMachineOffline = 'machine_offline';
const String kLiveStateUnknown = 'unknown';

/// Whether a message sent right now has a live agent to receive it.
bool liveStateIsReachable(String? liveState) =>
    liveState == kLiveStateLive || liveState == kLiveStateReconnecting;

/// Whether the composer should refuse input, the way an archived session does.
///
/// `unknown` deliberately does NOT block: it covers legacy rows and old-backend
/// responses, where refusing to send would break working sessions on no
/// evidence. Mirrors `blocksSending` in vicoa-web/lib/session-liveness.ts.
bool liveStateBlocksSending(String? liveState) =>
    liveState == kLiveStateAgentStopped || liveState == kLiveStateMachineOffline;

/// Why the session can't be reached, phrased as an instruction rather than a
/// promise — sending is blocked in these states, so "we'll deliver it later"
/// would be a lie. Null when there is nothing worth saying.
String? liveStateHint(String? liveState) {
  switch (liveState) {
    case kLiveStateAgentStopped:
      return "This session's agent isn't running. Resume it to send messages.";
    case kLiveStateMachineOffline:
      return 'Your computer is offline. Bring it back online to send messages.';
    default:
      return null;
  }
}

/// Short label for a session row, e.g. under the title in the home list.
String? liveStateShortLabel(String? liveState) {
  switch (liveState) {
    case kLiveStateAgentStopped:
      return 'Stopped';
    case kLiveStateMachineOffline:
      return 'Computer offline';
    default:
      return null;
  }
}

/// Sessions resumed in this app session, and when. Mirrors the module-level
/// `recentResumes` registry in vicoa-web/lib/session-resume.ts.
///
/// A relaunched agent won't heartbeat for up to ~30s, so the server keeps
/// reporting `agent_stopped` in that window. Any surface that derives liveness
/// from that value — the chat composer AND the home-list dot — would show the
/// session as stopped right after the user resumed it. This registry lets both
/// surfaces treat a just-resumed session as reachable until the agent beats,
/// from one source of truth (so the home dot and the composer never disagree).
///
/// Process-lived and deliberately not persisted: it's a short-lived UI grace,
/// and a stale entry surviving an app restart would hide a genuinely dead dot.
final Map<String, DateTime> _recentResumes = {};

/// Matches the web's LIVENESS_STARTUP_GRACE_MS so the two clients agree.
const Duration kResumeGrace = Duration(seconds: 120);

/// Record that [instanceId] was just resumed.
void markResumed(String instanceId) {
  if (instanceId.isEmpty) return;
  _recentResumes[instanceId] = DateTime.now();
}

/// Whether a resume is recent enough that the agent may not have beaten yet.
bool isWithinResumeGrace(String? instanceId) {
  if (instanceId == null || instanceId.isEmpty) return false;
  final at = _recentResumes[instanceId];
  if (at == null) return false;
  if (DateTime.now().difference(at) >= kResumeGrace) {
    _recentResumes.remove(instanceId);
    return false;
  }
  return true;
}
