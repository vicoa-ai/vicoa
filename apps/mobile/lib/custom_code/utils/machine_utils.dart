// Helpers for reading machine maps. Machine data reaches the app in two
// shapes that use different key names, so every accessor normalizes both:
//   - REST (GET/PATCH /machines):   `machine_id`, `metadata`
//   - WS `machine-update` envelope: `id`,         `machine_metadata`
// Reading through these helpers lets the list merge a WS update into a
// REST-fetched row without caring which shape produced it.

/// Default online cutoff: 3 missed 30s heartbeats (machine-management D5).
const Duration kMachineOnlineThreshold = Duration(seconds: 90);

String? getMachineHomeDir(dynamic machine) {
  if (machine is! Map) return null;
  if (machine['home_dir'] is String) return machine['home_dir'] as String;
  final metadata = machineMetadata(machine);
  if (metadata != null && metadata['home_dir'] is String) {
    return metadata['home_dir'] as String;
  }
  return null;
}

/// The machine's id from either shape (`machine_id` or `id`).
String? machineId(dynamic machine) {
  if (machine is! Map) return null;
  final id = machine['machine_id'] ?? machine['id'];
  return id?.toString();
}

/// The metadata blob from either shape (`metadata` or `machine_metadata`).
Map<dynamic, dynamic>? machineMetadata(dynamic machine) {
  if (machine is! Map) return null;
  final meta = machine['metadata'] ?? machine['machine_metadata'];
  return meta is Map ? meta : null;
}

/// Display name with sensible fallbacks: explicit name → hostname → generic.
String machineDisplayName(dynamic machine) {
  if (machine is Map) {
    final name = machine['display_name'];
    if (name is String && name.trim().isNotEmpty) return name.trim();
    final host = machine['hostname'];
    if (host is String && host.trim().isNotEmpty) return host.trim();
  }
  return 'Unnamed machine';
}

/// Parse a heartbeat value (ISO string or DateTime) into a UTC DateTime.
DateTime? machineLastHeartbeat(dynamic value) {
  if (value is DateTime) return value.toUtc();
  if (value is String && value.isNotEmpty) {
    return DateTime.tryParse(value)?.toUtc();
  }
  return null;
}

/// Whether a machine counts as online given its last heartbeat. Accepts a
/// DateTime, an ISO string, or null (→ offline). Used both with a raw
/// heartbeat value and re-evaluated on a local ticker as time passes.
bool isMachineOnline(
  dynamic lastHeartbeatAt, {
  Duration threshold = kMachineOnlineThreshold,
}) {
  final hb = machineLastHeartbeat(lastHeartbeatAt);
  if (hb == null) return false;
  final age = DateTime.now().toUtc().difference(hb);
  return age <= threshold;
}

/// Convenience: online check straight from a machine map.
bool isMachineOnlineFromMap(
  dynamic machine, {
  Duration threshold = kMachineOnlineThreshold,
}) {
  if (machine is! Map) return false;
  return isMachineOnline(machine['last_heartbeat_at'], threshold: threshold);
}

/// Order machines for display: online first, then most-recently-seen first
/// (machine-management D16). Accepts any value; a non-list yields []. Shared by
/// the machines list and the New Session picker so both screens agree.
List<dynamic> sortMachinesByStatus(dynamic source) {
  final list = source is List ? List<dynamic>.from(source) : <dynamic>[];
  list.sort((a, b) {
    final aOnline = isMachineOnlineFromMap(a) ? 0 : 1;
    final bOnline = isMachineOnlineFromMap(b) ? 0 : 1;
    if (aOnline != bOnline) return aOnline - bOnline;
    final aHb = machineLastHeartbeat(a is Map ? a['last_heartbeat_at'] : null)
            ?.millisecondsSinceEpoch ??
        0;
    final bHb = machineLastHeartbeat(b is Map ? b['last_heartbeat_at'] : null)
            ?.millisecondsSinceEpoch ??
        0;
    return bHb.compareTo(aHb);
  });
  return list;
}

/// Per-agent install map from `metadata.available_agents`, e.g.
/// `{claude: true, codex: false, opencode: true}`. Returns null when the
/// daemon hasn't reported it yet (older daemon) — the UI renders "unknown"
/// rather than "Not found" in that case (machine-management D12).
Map<String, bool>? parseAvailableAgents(dynamic machine) {
  final meta = machineMetadata(machine);
  final raw = meta?['available_agents'];
  if (raw is! Map) return null;
  final result = <String, bool>{};
  raw.forEach((key, value) {
    if (key != null) result[key.toString()] = value == true;
  });
  return result;
}

/// Whether the machine's daemon advertises git-worktree support via
/// `metadata.capabilities` (e.g. `["worktree"]`).
///
/// Unlike [parseAvailableAgents], a MISSING capability reads as UNsupported,
/// not "supports everything": an old daemon silently ignores the spawn-session
/// `worktree` param and would spawn in the base dir, an invisible wrong result.
/// So the app shows the worktree option only when explicitly advertised.
bool machineSupportsWorktree(dynamic machine) {
  final meta = machineMetadata(machine);
  final raw = meta?['capabilities'];
  if (raw is! List) return false;
  return raw.any((c) => c?.toString() == 'worktree');
}

/// Normalize a machine map (REST or WS-envelope shape) into the canonical REST
/// shape (`machine_id`, `metadata`). Merging a raw WS update (`id`,
/// `machine_metadata`) into a REST-fetched row would otherwise leave the stale
/// `metadata` shadowing the fresh `machine_metadata`; normalizing first keeps
/// cached rows consistent regardless of which source produced them.
Map<String, dynamic> normalizeMachine(dynamic machine) {
  final out = <String, dynamic>{};
  if (machine is! Map) return out;
  final id = machineId(machine);
  if (id != null) out['machine_id'] = id;
  for (final key in const [
    'display_name',
    'hostname',
    'platform',
    'home_dir',
    'last_heartbeat_at',
    'recent_directories',
    'created_at',
    'updated_at',
  ]) {
    if (machine.containsKey(key)) out[key] = machine[key];
  }
  final meta = machineMetadata(machine);
  if (meta != null) out['metadata'] = meta;
  return out;
}

/// Vicoa CLI version from `metadata.cli_version` (machine-management D4).
String? cliVersion(dynamic machine) {
  final meta = machineMetadata(machine);
  final v = meta?['cli_version'];
  return v is String && v.isNotEmpty ? v : null;
}

/// Human last-seen line for a machine: "Active now" when online, else a
/// relative "Last seen 5m ago", or "Never connected" with no heartbeat.
String lastSeenLabel(dynamic machine) {
  final hb = machineLastHeartbeat(
      machine is Map ? machine['last_heartbeat_at'] : null);
  if (hb == null) return 'Never connected';
  if (isMachineOnline(hb)) return 'Active now';
  final age = DateTime.now().toUtc().difference(hb);
  return 'Last seen ${humanizeDuration(age)} ago';
}

/// Compact duration: "45s", "5m", "3h", "2d".
String humanizeDuration(Duration d) {
  if (d.inSeconds < 60) return '${d.inSeconds}s';
  if (d.inMinutes < 60) return '${d.inMinutes}m';
  if (d.inHours < 24) return '${d.inHours}h';
  return '${d.inDays}d';
}

/// Python version reported alongside cli_version, if present.
String? pythonVersion(dynamic machine) {
  final meta = machineMetadata(machine);
  final v = meta?['python_version'];
  return v is String && v.isNotEmpty ? v : null;
}
