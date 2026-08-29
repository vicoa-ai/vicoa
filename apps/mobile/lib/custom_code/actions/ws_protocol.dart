/// Pure WebSocket protocol helpers for vicoa-app (websocket-migration plan
/// §2.6, §2.10). Merge/dedupe semantics and reconnect timing live here,
/// separated from socket I/O (`ws_client.dart`) so they are unit-testable
/// under `flutter test` without a live connection.
library;

import 'dart:math';

/// Decides whether an incoming row is fresh and should be applied. The §2.6
/// merge model has two rules — append-only (messages) and mutable-by-
/// updated_at (instances) — each expressed as a tracker.
abstract class RowTracker {
  /// True if the row is new/applicable; updates internal seen-state when so.
  bool accept(Map<String, dynamic> row);
}

class _AppendTracker implements RowTracker {
  final Set<String> _seen = {};

  @override
  bool accept(Map<String, dynamic> row) {
    final id = row['id']?.toString();
    if (id == null || _seen.contains(id)) return false;
    _seen.add(id);
    return true;
  }
}

/// Append-only dedupe (§2.6): first write wins. A second row with an id already
/// seen is a duplicate (e.g. the reconnect safety-window overlap) and dropped.
RowTracker createAppendTracker() => _AppendTracker();

class _MutableTracker implements RowTracker {
  final Map<String, String> _lastUpdatedAt = {};

  @override
  bool accept(Map<String, dynamic> row) {
    final id = row['id']?.toString();
    if (id == null) return false;
    final incoming = (row['updated_at'] ?? '').toString();
    final seen = _lastUpdatedAt[id];
    if (seen != null && incoming.compareTo(seen) <= 0) return false;
    _lastUpdatedAt[id] = incoming;
    return true;
  }
}

/// Mutable-entity merge (§2.6): an incoming row replaces local state only when
/// its `updated_at` is strictly later than the last seen value for that id.
/// Equal or earlier `updated_at` is a stale/out-of-order frame and dropped.
RowTracker createMutableTracker() => _MutableTracker();

/// Buffers live `update` rows that arrive while a catch-up `fetch_*` is still
/// in flight (§2.6) so history renders in order. Live rows are held back until
/// the fetch response lands, then fetch rows are delivered first, followed by
/// the buffered live rows — all filtered through the entity's [RowTracker] so a
/// row delivered by both paths is emitted once. The tracker's seen-state
/// outlives a [beginCatchUp], so the reconnect safety-window overlap is not
/// re-delivered.
class CatchUpBuffer {
  final RowTracker _tracker;
  List<Map<String, dynamic>> _buffered = [];
  bool _fetchComplete = false;

  CatchUpBuffer(this._tracker);

  /// Start a fresh catch-up cycle (called on every (re)connect).
  void beginCatchUp() {
    _buffered = [];
    _fetchComplete = false;
  }

  /// Take a live row; return rows ready to deliver (empty while catching up).
  List<Map<String, dynamic>> bufferLive(Map<String, dynamic> row) {
    if (_fetchComplete) {
      return _tracker.accept(row) ? [row] : [];
    }
    _buffered.add(row);
    return [];
  }

  /// Catch-up response arrived: deliver its rows, then the buffered live rows.
  List<Map<String, dynamic>> completeFetch(List<Map<String, dynamic>> rows) {
    final delivered = [...rows, ..._buffered].where(_tracker.accept).toList();
    _buffered = [];
    _fetchComplete = true;
    return delivered;
  }
}

/// Full-jitter reconnect backoff (§2.10): `random(0, min(cap, base * 2^attempt))`,
/// applied from attempt 0 so even the first reconnect is jittered and a mass
/// disconnect herd spreads over the window instead of retrying in lockstep.
double reconnectDelayMs(int attempt, {double base = 1000, double cap = 30000}) {
  final ceiling = min(cap, base * pow(2, attempt));
  return Random().nextDouble() * ceiling;
}

/// Applies a `message-update` wire frame to a chat's message list in place.
/// The frame (`{t: "message-update", id, instance_id, message_metadata}`)
/// carries a *replacement* for one existing message's `message_metadata` —
/// it is not a new row, so unlike the trackers above there is no dedupe
/// state: whichever frame is applied last wins, and only the
/// `message_metadata` key is touched (every other field, and the key order
/// of the message map, is left exactly as it was). Returns `true` if
/// `body['id']` matched a message in [messages] (and patched it), `false`
/// for a no-op — an absent/null id, a `body` missing the `message_metadata`
/// key entirely (malformed/contract-drift frame; guards against wiping an
/// existing message's metadata with a stray `null`), or an id not yet
/// present (e.g. the update raced ahead of catch-up delivering the original
/// message; the server is expected to reflect the latest metadata on that
/// row too, so nothing is lost).
bool applyMessageMetadataUpdate(
  List<dynamic> messages,
  Map<String, dynamic> body,
) {
  final id = body['id'];
  if (id == null) return false;
  // Guard against a malformed/contract-drift frame that's missing the
  // `message_metadata` key entirely: without this check the loop below
  // would happily assign `null`, wiping out a real message's existing
  // metadata. A key that's present-but-null is still applied (that's a
  // legitimate "clear the metadata" instruction from the server).
  if (!body.containsKey('message_metadata')) return false;
  for (final message in messages) {
    if (message is Map && message['id'] == id) {
      message['message_metadata'] = body['message_metadata'];
      return true;
    }
  }
  return false;
}

/// Advances a reconnect watermark: the maximum of [current] and [field] across
/// [rows]. ISO 8601 timestamps compare correctly as strings. Used for the
/// `messages` `created_at` cursor and the instance `updated_at` cursor (§2.6).
String? latestTimestamp(
  String? current,
  List<Map<String, dynamic>> rows,
  String field,
) {
  var max = current;
  for (final row in rows) {
    final value = row[field];
    if (value is String && (max == null || value.compareTo(max) > 0)) {
      max = value;
    }
  }
  return max;
}
