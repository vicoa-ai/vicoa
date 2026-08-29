/// Shared user-scoped WebSocket client for vicoa-app (websocket-migration plan
/// §2.1-2.10, Phase 4b). One connection carries every realtime update for the
/// signed-in user; the home and chat screens attach to it and filter locally
/// (§2.3), replacing the per-stream SSE connections.
///
/// Socket I/O and reconnect/lifecycle orchestration live here; the order-
/// sensitive merge/dedupe semantics are the pure functions in `ws_protocol.dart`.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '/backend/supabase/supabase.dart';
import 'user_agents_cache.dart';
import 'vicoa_api_config.dart';
import 'vicoa_api_request.dart' show getUserToken;
import 'ws_protocol.dart';

// No frame (not even a server ping every 30s) for this long means a dead
// socket the OS has not surfaced yet — force a reconnect.
const Duration _livenessTimeout = Duration(seconds: 70);
const Duration _idleCloseGrace = Duration(seconds: 1);

// Per-RPC wall-clock timeout. The server emits `rpc-error timeout` after 30s
// (shared/websocket/rpc.py); the client waits 5s longer so the server's own
// error frame is the expected outcome. Without this, an RPC on a healthy
// connection whose response frame never lands would leave callRpc hanging
// forever — ping/pong keeps the liveness watcher quiet.
const Duration _rpcRequestTimeout = Duration(seconds: 35);

/// A failed `rpc-call` (websocket-migration §2.8). `code` is a wire error code
/// (`no_handler`, `target_disconnected`, `timeout`) or a client-side reason.
class RpcException implements Exception {
  const RpcException(this.code);

  final String code;

  @override
  String toString() => 'RpcException($code)';
}

/// One chat session the client is catching up / delivering messages for.
class _WatchedInstance {
  _WatchedInstance(this.instanceId, this.watermark);

  final String instanceId;

  /// `created_at` of the newest delivered message — the reconnect cursor (§2.6).
  String? watermark;

  /// Buffers live `new-message` rows while a catch-up fetch is in flight.
  final CatchUpBuffer buffer = CatchUpBuffer(createAppendTracker());

  /// Rows accumulated across the pages of the current catch-up fetch.
  List<Map<String, dynamic>> accum = [];
}

class _ConnectedWaiter {
  _ConnectedWaiter(this.completer, this.timer);

  final Completer<void> completer;
  final Timer timer;
}

class _PendingRpc {
  _PendingRpc(this.completer, this.timer);

  final Completer<Map<String, dynamic>> completer;
  final Timer timer;
}

/// Process-wide WebSocket client. Mobile lifecycle (background suspend, resume,
/// network change) is handled here so the home/chat models stay simple (§4b).
class VicoaWsClient with WidgetsBindingObserver {
  VicoaWsClient._() {
    // Mirror Supabase JWT lifecycle into the WS connection (§4b):
    //   tokenRefreshed / signedIn → reconnect so server-side auth sees the
    //   fresh JWT (also drops a previous user's authenticated socket on an
    //   account switch); signedOut → close and stop reconnecting until the
    //   next signedIn. SupaFlow is initialized in main() before any screen
    //   touches `VicoaWsClient.instance`, so this listen is safe at field
    //   init time.
    _authSub = SupaFlow.client.auth.onAuthStateChange.listen(_handleAuthChange);
  }

  static final VicoaWsClient instance = VicoaWsClient._();

  final StreamController<Map<String, dynamic>> _events =
      StreamController<Map<String, dynamic>>.broadcast();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _channelSub;
  bool _connected = false;
  bool _destroyed = false;
  bool _observingLifecycle = false;
  int _retainCount = 0;
  int _reconnectAttempt = 0;
  int _requestSeq = 0;
  Timer? _reconnectTimer;
  Timer? _livenessTimer;
  Timer? _idleCloseTimer;
  StreamSubscription<AuthState>? _authSub;

  final Map<String, _WatchedInstance> _watched = {};
  // request_id → the catch-up job awaiting that fetch_messages_response.
  final Map<String, _WatchedInstance> _pendingFetches = {};
  // request_id → the caller awaiting an rpc-result / rpc-error (§2.8). The
  // timer is the client-side defensive timeout — see `_rpcRequestTimeout`.
  final Map<String, _PendingRpc> _pendingRpc = {};
  final Set<_ConnectedWaiter> _connectedWaiters = {};
  // Drops out-of-order `instance-update` frames by `updated_at` (§2.6).
  final RowTracker _instanceTracker = createMutableTracker();

  /// True once the hello/server_info handshake has completed.
  bool get isConnected => _connected;

  /// Invoke an RPC method on a daemon over the shared connection (§2.8) — e.g.
  /// `spawn-session`. Completes with the daemon's result, or fails with an
  /// [RpcException] carrying the wire error code.
  Future<Map<String, dynamic>> callRpc(
    String machineId,
    String method,
    Map<String, dynamic> params,
  ) async {
    final transientRetain = _retainCount == 0;
    if (transientRetain) retain();
    try {
      await _waitUntilConnected();
      final requestId = 'rpc${_requestSeq += 1}';
      final completer = Completer<Map<String, dynamic>>();
      final timer = Timer(_rpcRequestTimeout, () {
        final pending = _pendingRpc.remove(requestId);
        if (pending != null && !pending.completer.isCompleted) {
          pending.completer.completeError(const RpcException('timeout'));
        }
      });
      _pendingRpc[requestId] = _PendingRpc(completer, timer);
      _send({
        'type': 'rpc-call',
        'request_id': requestId,
        'machine_id': machineId,
        'method': method,
        'params': params,
      });
      return await completer.future;
    } on RpcException {
      rethrow;
    } catch (_) {
      throw const RpcException('not_connected');
    } finally {
      if (transientRetain) release();
    }
  }

  /// Resolve when the next event for `(entity, entityId)` arrives over the
  /// shared WS, or `null` on timeout. Used after `spawn-session` to await the
  /// daemon-spawned agent's self-registration without polling REST.
  ///
  /// For `agent_instances` the returned map is the envelope body enriched
  /// with `agent_type_name` (resolved client-side from `UserAgentsCache`),
  /// so callers can render directly without a follow-up REST detail fetch.
  ///
  /// Currently scoped to `agent_instances`; extend with per-entity streams
  /// when more entity types need the same hook.
  ///
  /// CALLER POLICY: do not wrap this in per-flow REST polling. If you find
  /// yourself wanting a REST fallback, the correct fix is to unify catch-up
  /// rows into the same dispatch path as live frames (so `fetch_*_response`
  /// rows go through `_dispatchUpdate` and a reconnect catch-up resolves
  /// this future automatically). The spawn-session widgets keep a contained
  /// REST fallback as a known exception until that unification lands.
  Future<Map<String, dynamic>?> waitForEntity(
    String entity,
    String entityId, {
    Duration timeout = const Duration(seconds: 15),
  }) {
    if (entity != 'agent_instances') return Future.value(null);
    final completer = Completer<Map<String, dynamic>?>();
    late StreamSubscription<Map<String, dynamic>> sub;
    final timer = Timer(timeout, () {
      if (!completer.isCompleted) {
        sub.cancel();
        completer.complete(null);
      }
    });
    sub = instanceEvents.listen((event) {
      final data = event['data'];
      if (data is Map && data['id']?.toString() == entityId) {
        timer.cancel();
        sub.cancel();
        if (!completer.isCompleted) {
          completer.complete(Map<String, dynamic>.from(data));
        }
      }
    });
    return completer.future;
  }

  /// Instance-list events for the home screen: `instance_created`,
  /// `instance_updated`, `connected`, `disconnected`.
  Stream<Map<String, dynamic>> get instanceEvents => _events.stream.where((e) {
        final ev = e['event'];
        return ev == 'instance_created' ||
            ev == 'instance_updated' ||
            ev == 'connected' ||
            ev == 'disconnected';
      });

  /// Machine-list events for the machines screen: `machine_updated`, plus
  /// connection transitions so the list can reflect liveness of the pipe.
  Stream<Map<String, dynamic>> get machineEvents => _events.stream.where((e) {
        final ev = e['event'];
        return ev == 'machine_updated' ||
            ev == 'connected' ||
            ev == 'disconnected';
      });

  /// Message/status/instance events for one chat session, plus connection
  /// transitions. `instance_updated` flows here so the chat page can react
  /// to canonical row changes (status, session_config, project, etc.) the
  /// moment the backend broadcasts them — required for the gear-pill sheet
  /// to reflect a mid-session permission_mode or model change without the
  /// user closing + reopening the chat page. `message_metadata_update`
  /// flows here too — a metadata-only patch for an existing message (see
  /// `message-update` in `_dispatchUpdate`), distinct from `message` which
  /// is always a new row.
  Stream<Map<String, dynamic>> messageEventsFor(String instanceId) =>
      _events.stream.where((e) {
        final ev = e['event'];
        if (ev == 'connected' || ev == 'disconnected') return true;
        if (ev == 'message' ||
            ev == 'status_update' ||
            ev == 'instance_updated' ||
            ev == 'message_metadata_update') {
          return e['instance_id'] == instanceId;
        }
        return false;
      });

  /// Fires once per `new-message` arrival across all instances, without going
  /// through the per-instance ordering buffer. The home screen uses this to
  /// advance the session row's `latest_message_at` even for sessions the chat
  /// page isn't currently watching. The data payload is the raw `new-message`
  /// body (`instance_id`, `created_at`, `content`, ...).
  Stream<Map<String, dynamic>> get messageArrivedEvents =>
      _events.stream.where((e) => e['event'] == 'message_arrived');

  /// Keep the connection alive while a screen needs it; the first retainer
  /// opens the socket, the last to leave tears it down.
  void retain() {
    _retainCount += 1;
    _idleCloseTimer?.cancel();
    _idleCloseTimer = null;
    _ensureAuthListener();
    if (_retainCount == 1) {
      _destroyed = false;
      if (!_observingLifecycle) {
        WidgetsBinding.instance.addObserver(this);
        _observingLifecycle = true;
      }
      unawaited(_connect());
    }
  }

  void release() {
    if (_retainCount > 0) _retainCount -= 1;
    if (_retainCount == 0 && _idleCloseTimer == null) {
      _idleCloseTimer = Timer(_idleCloseGrace, () {
        _idleCloseTimer = null;
        if (_retainCount == 0) _teardown();
      });
    }
  }

  /// Register interest in a chat session so catch-up fetches it on (re)connect.
  /// [watermark] is the `created_at` of the newest message already rendered.
  void watchInstance(String instanceId, {String? watermark}) {
    final existing = _watched[instanceId];
    if (existing != null) {
      if (watermark != null) existing.watermark = watermark;
    } else {
      _watched[instanceId] = _WatchedInstance(instanceId, watermark);
    }
    if (_connected) _startCatchUp(_watched[instanceId]!);
  }

  void unwatchInstance(String instanceId) {
    _watched.remove(instanceId);
  }

  // --- connection lifecycle -------------------------------------------------

  Future<void> _connect() async {
    if (_channel != null || _retainCount == 0 || _destroyed) return;

    String? token;
    try {
      token = await getUserToken();
    } catch (e) {
      debugPrint('[ws] failed to read auth token: $e');
    }
    if (_channel != null || _retainCount == 0 || _destroyed) return;
    if (token == null) {
      _scheduleReconnect();
      return;
    }

    final channel = WebSocketChannel.connect(
      Uri.parse(getVicoaWsUrl()),
      protocols: ['vicoa-ws', 'vicoa-supabase.$token'],
    );
    _channel = channel;

    try {
      await channel.ready;
    } catch (e) {
      debugPrint('[ws] connect failed: $e');
      _handleDown(channel);
      return;
    }
    if (channel != _channel) return; // superseded while awaiting

    channel.sink.add(jsonEncode({'type': 'hello', 'scope': 'user-scoped'}));
    _channelSub = channel.stream.listen(
      (raw) {
        _resetLiveness();
        _handleFrame(raw);
      },
      onError: (_) => _handleDown(channel),
      onDone: () => _handleDown(channel),
    );
    _resetLiveness();
  }

  void _handleDown(WebSocketChannel channel) {
    if (channel != _channel) return;
    _channel = null;
    _connected = false;
    _channelSub?.cancel();
    _channelSub = null;
    _clearLiveness();
    _failPendingRpc('disconnected');
    _failConnectedWaiters();
    _emit({'event': 'disconnected'});
    if (!_destroyed && _retainCount > 0) _scheduleReconnect();
  }

  /// Fail every in-flight RPC so a caller never hangs past a disconnect.
  void _failPendingRpc(String code) {
    for (final pending in _pendingRpc.values) {
      pending.timer.cancel();
      if (!pending.completer.isCompleted) {
        pending.completer.completeError(RpcException(code));
      }
    }
    _pendingRpc.clear();
  }

  void _onRpcResponse(Map<String, dynamic> frame) {
    final pending = _pendingRpc.remove(frame['request_id']);
    if (pending == null) return;
    pending.timer.cancel();
    if (pending.completer.isCompleted) return;
    if (frame['type'] == 'rpc-error') {
      pending.completer.completeError(
        RpcException((frame['code'] ?? 'rpc_failed').toString()),
      );
      return;
    }
    final result = frame['result'];
    pending.completer.complete(
      result is Map ? Map<String, dynamic>.from(result) : <String, dynamic>{},
    );
  }

  void _scheduleReconnect() {
    if (_reconnectTimer != null) return;
    final delay = reconnectDelayMs(_reconnectAttempt);
    _reconnectAttempt += 1;
    _reconnectTimer = Timer(Duration(milliseconds: delay.round()), () {
      _reconnectTimer = null;
      unawaited(_connect());
    });
  }

  /// Drop the current socket and reconnect immediately — used on app resume,
  /// when the OS has likely suspended the socket while backgrounded (§4b).
  void _forceReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _reconnectAttempt = 0;
    final channel = _channel;
    _channel = null;
    _connected = false;
    _channelSub?.cancel();
    _channelSub = null;
    _clearLiveness();
    _failPendingRpc('disconnected');
    _failConnectedWaiters();
    channel?.sink.close();
    if (_retainCount > 0 && !_destroyed) unawaited(_connect());
  }

  void _teardown() {
    _destroyed = true;
    _idleCloseTimer?.cancel();
    _idleCloseTimer = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _clearLiveness();
    _reconnectAttempt = 0;
    _pendingFetches.clear();
    _failPendingRpc('disconnected');
    _failConnectedWaiters();
    _watched.clear();
    if (_observingLifecycle) {
      WidgetsBinding.instance.removeObserver(this);
      _observingLifecycle = false;
    }
    final channel = _channel;
    _channel = null;
    _connected = false;
    _channelSub?.cancel();
    _channelSub = null;
    channel?.sink.close();
  }

  void _ensureAuthListener() {
    _authSub ??=
        SupaFlow.client.auth.onAuthStateChange.listen(_handleAuthChange);
  }

  Future<void> _waitUntilConnected({
    Duration timeout = const Duration(seconds: 10),
  }) {
    if (_connected) return Future.value();
    if (_channel == null && _retainCount > 0) unawaited(_connect());

    final completer = Completer<void>();
    late final _ConnectedWaiter waiter;
    waiter = _ConnectedWaiter(
      completer,
      Timer(timeout, () {
        _connectedWaiters.remove(waiter);
        if (!completer.isCompleted) {
          completer.completeError(const RpcException('not_connected'));
        }
      }),
    );
    _connectedWaiters.add(waiter);
    return completer.future;
  }

  void _resolveConnectedWaiters() {
    for (final waiter in _connectedWaiters) {
      waiter.timer.cancel();
      if (!waiter.completer.isCompleted) waiter.completer.complete();
    }
    _connectedWaiters.clear();
  }

  void _failConnectedWaiters() {
    for (final waiter in _connectedWaiters) {
      waiter.timer.cancel();
      if (!waiter.completer.isCompleted) {
        waiter.completer.completeError(const RpcException('not_connected'));
      }
    }
    _connectedWaiters.clear();
  }

  void _resetLiveness() {
    _clearLiveness();
    _livenessTimer = Timer(_livenessTimeout, () {
      // Stale socket the OS has not closed — drop it to trigger a reconnect.
      _channel?.sink.close();
    });
  }

  void _clearLiveness() {
    _livenessTimer?.cancel();
    _livenessTimer = null;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      if (_retainCount > 0) _forceReconnect();
    } else if (state == AppLifecycleState.paused) {
      // The OS suspends the socket while backgrounded; close it cleanly now
      // rather than leave a zombie. Resume reconnects via _forceReconnect.
      final channel = _channel;
      _channel = null;
      _connected = false;
      _channelSub?.cancel();
      _channelSub = null;
      _clearLiveness();
      _failPendingRpc('disconnected');
      _failConnectedWaiters();
      channel?.sink.close();
    }
  }

  void _handleAuthChange(AuthState authState) {
    switch (authState.event) {
      case AuthChangeEvent.signedIn:
      case AuthChangeEvent.tokenRefreshed:
        // A fresh JWT — reconnect so server-side auth is aligned with the
        // client's current session. On signedIn after an account switch
        // this also drops the previous user's authenticated socket. Skip
        // when not yet connected: a pending _connect() reads the same
        // fresh token from currentSession, so re-firing would just thrash
        // the in-flight handshake.
        if (_retainCount > 0 && !_destroyed && _connected) {
          debugPrint('[ws] auth ${authState.event.name} → reconnecting');
          _forceReconnect();
        }
        break;
      case AuthChangeEvent.signedOut:
        // No authenticated user — close the socket and stop reconnecting.
        // _watched is cleared too: if UI hasn't yet released its instance
        // subscriptions (e.g. token-expiry-driven signedOut beats screen
        // teardown), the next signedIn must not re-watch the previous
        // user's instances under the new user's connection.
        debugPrint('[ws] auth signedOut → closing socket');
        _reconnectTimer?.cancel();
        _reconnectTimer = null;
        final channel = _channel;
        _channel = null;
        _connected = false;
        _channelSub?.cancel();
        _channelSub = null;
        _clearLiveness();
        _failPendingRpc('signed_out');
        _failConnectedWaiters();
        _watched.clear();
        channel?.sink.close();
        break;
      default:
        break;
    }
  }

  // --- frame handling -------------------------------------------------------

  void _handleFrame(dynamic raw) {
    Map<String, dynamic> frame;
    try {
      frame = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (e) {
      debugPrint('[ws] dropped unparseable frame: $e');
      return;
    }

    switch (frame['type']) {
      case 'ping':
        _send({'type': 'pong'});
        break;
      case 'server_info':
        _reconnectAttempt = 0;
        _connected = true;
        _resolveConnectedWaiters();
        _emit({'event': 'connected'});
        // Keep the local user_agents cache fresh: every successful handshake
        // is also our cold-start and reconnect signal. Fire-and-forget — a
        // failed refresh leaves the previously-cached list in place.
        // We can consider remove it if not needed.
        unawaited(UserAgentsCache.instance.refresh());
        for (final w in _watched.values) {
          _startCatchUp(w);
        }
        break;
      case 'update':
        _dispatchUpdate(frame['payload']);
        break;
      case 'fetch_messages_response':
      case 'resync_required':
        _onFetchResponse(frame);
        break;
      case 'rpc-result':
      case 'rpc-error':
        _onRpcResponse(frame);
        break;
      // 'ephemeral' and unknown frames are ignored.
    }
  }

  void _dispatchUpdate(dynamic payload) {
    if (payload is! Map) return;
    final rawBody = payload['body'];
    if (rawBody is! Map) return;
    final body = Map<String, dynamic>.from(rawBody);

    switch (body['t']) {
      case 'new-message':
        final instanceId = body['instance_id']?.toString();
        // Notify the session list (home screen) on every arrival — the chat
        // page's catch-up buffer below is gated on `_watched`, but the home
        // screen needs to advance `latest_message_at` for any instance.
        if (instanceId != null) {
          _emit({
            'event': 'message_arrived',
            'data': body,
            'instance_id': instanceId,
          });
        }
        final watched = instanceId != null ? _watched[instanceId] : null;
        if (watched != null) {
          for (final ready in watched.buffer.bufferLive(body)) {
            _deliverMessage(watched, ready);
          }
        }
        break;
      case 'message-update':
        // A metadata-only patch for an existing message (e.g. background-task
        // progress) — never a new row, so it bypasses the CatchUpBuffer
        // ordering used for `new-message` entirely. The chat page finds the
        // message by `id` and replaces its `message_metadata` in place; an
        // id it doesn't have yet is a no-op there (see
        // ws_protocol.applyMessageMetadataUpdate).
        _emit({
          'event': 'message_metadata_update',
          'data': body,
          'instance_id': body['instance_id']?.toString(),
        });
        break;
      case 'instance-created':
        _emitInstanceCreated(body);
        break;
      case 'instance-update':
        if (_instanceTracker.accept(body)) {
          final instanceId = body['id']?.toString();
          _emit({
            'event': 'instance_updated',
            'data': body,
            'instance_id': instanceId,
          });
          _emit({
            'event': 'status_update',
            'data': {'status': body['status']},
            'instance_id': instanceId,
          });
        }
        break;
      case 'machine-update':
        // Live machine status/metadata for the machines list + detail page
        // (machine-management D13). The body uses `id`/`machine_metadata`
        // (vs the REST `machine_id`/`metadata`); machine_utils normalizes both.
        _emit({
          'event': 'machine_updated',
          'data': body,
          'machine_id': body['id']?.toString(),
        });
        break;
    }
  }

  void _emitInstanceCreated(Map<String, dynamic> body) {
    if (body['id'] == null) return;
    // Compose `agent_type_name` client-side from the local user_agents cache
    // (§2.4: envelopes carry the canonical row only; presentation fields are
    // not joined on the broadcast path). If the cache has it, emit sync.
    // On miss, refresh once and emit with the refreshed name — covers the
    // "user_agent created on web seconds ago" race without a per-event REST
    // fetch on the broadcast happy path.
    final hit = _enrichInstanceBody(body);
    if (hit != null) {
      _emit({'event': 'instance_created', 'data': hit});
      return;
    }
    unawaited(() async {
      final enriched = await _enrichInstanceBodyAsync(body);
      _emit({'event': 'instance_created', 'data': enriched});
    }());
  }

  /// Returns the enriched body if `agent_type_name` is already present or
  /// resolvable from the cache; `null` to signal a cache miss the caller
  /// should resolve asynchronously.
  Map<String, dynamic>? _enrichInstanceBody(Map<String, dynamic> body) {
    if (body['agent_type_name'] is String &&
        (body['agent_type_name'] as String).isNotEmpty) {
      return body;
    }
    final userAgentId = body['user_agent_id']?.toString();
    final name = UserAgentsCache.instance.lookupName(userAgentId);
    if (name != null) {
      return Map<String, dynamic>.from(body)..['agent_type_name'] = name;
    }
    return null;
  }

  Future<Map<String, dynamic>> _enrichInstanceBodyAsync(
    Map<String, dynamic> body,
  ) async {
    final userAgentId = body['user_agent_id']?.toString();
    final name =
        await UserAgentsCache.instance.lookupOrRefreshName(userAgentId);
    final out = Map<String, dynamic>.from(body);
    if (name != null) out['agent_type_name'] = name;
    return out;
  }

  // --- message catch-up (§2.6) ---------------------------------------------

  void _startCatchUp(_WatchedInstance watched) {
    watched.buffer.beginCatchUp();
    watched.accum = [];
    final after = watched.watermark != null
        ? {'created_at': watched.watermark, 'id': null}
        : null;
    _sendFetchMessages(watched, after);
  }

  void _sendFetchMessages(
      _WatchedInstance watched, Map<String, dynamic>? after) {
    final requestId = 'r${_requestSeq += 1}';
    _pendingFetches[requestId] = watched;
    _send({
      'type': 'fetch_messages_request',
      'request_id': requestId,
      'instance_id': watched.instanceId,
      'after': after,
    });
  }

  void _onFetchResponse(Map<String, dynamic> frame) {
    final watched = _pendingFetches.remove(frame['request_id']);
    if (watched == null) return;

    if (frame['type'] == 'resync_required') {
      // The watermark is unservable — drop it and re-fetch the tail.
      watched.watermark = null;
      watched.buffer.beginCatchUp();
      watched.accum = [];
      _sendFetchMessages(watched, null);
      return;
    }

    final rows = ((frame['rows'] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
    watched.accum.addAll(rows);

    if (frame['has_more'] == true && rows.isNotEmpty) {
      final last = rows.last;
      _sendFetchMessages(
        watched,
        {'created_at': last['created_at'], 'id': last['id']},
      );
      return;
    }

    final delivered = watched.buffer.completeFetch(watched.accum);
    watched.accum = [];
    for (final body in delivered) {
      _deliverMessage(watched, body);
    }
  }

  void _deliverMessage(_WatchedInstance watched, Map<String, dynamic> body) {
    watched.watermark =
        latestTimestamp(watched.watermark, [body], 'created_at');
    _emit({
      'event': 'message',
      'data': body,
      'instance_id': watched.instanceId,
    });
  }

  // --- helpers --------------------------------------------------------------

  void _send(Map<String, dynamic> frame) {
    final channel = _channel;
    if (channel == null) return;
    try {
      channel.sink.add(jsonEncode(frame));
    } catch (e) {
      debugPrint('[ws] send failed: $e');
    }
  }

  void _emit(Map<String, dynamic> event) {
    if (!_events.isClosed) _events.add(event);
  }
}
