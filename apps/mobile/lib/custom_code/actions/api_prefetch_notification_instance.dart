// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:async';
import 'dart:convert';

// getUserToken is the only symbol not already re-exported by index.dart, so it
// is the only one imported directly (importing the rest here too would clash).
import 'vicoa_api_request.dart' show getUserToken;

/// Outcome of pre-fetching an agent session before opening its chat page from
/// a push notification. See [apiPrefetchNotificationInstance].
class NotificationPrefetchResult {
  /// The instance was reached and is valid — safe to open the chat page.
  final bool ok;

  /// The backend confirmed the instance no longer exists (HTTP 404). Kept
  /// distinct from a transient failure so the caller can decide what to do.
  final bool gone;

  /// The canonical `agent_instances` row (chat header + streaming gate), or
  /// null when [ok] is false.
  final dynamic instanceData;

  /// The already-decoded, blank-filtered transcript. Best-effort: may be empty
  /// even when [ok] is true — either a valid session with no messages yet, or
  /// only the messages fetch failed while the instance fetch succeeded.
  final List<dynamic> messages;

  const NotificationPrefetchResult({
    this.ok = false,
    this.gone = false,
    this.instanceData,
    this.messages = const [],
  });
}

/// Top-level parser (required by [vicoaApiRequestComputed]'s `compute`) — a
/// mirror of the filter in api_get_instance_messages.dart: accept a bare list
/// or `{messages:[...]}` and drop blank-content rows.
List<dynamic> _decodeMessages(String body) {
  final decoded = json.decode(body);
  List<dynamic> messages = const [];
  if (decoded is List) {
    messages = decoded;
  } else if (decoded is Map && decoded['messages'] is List) {
    messages = decoded['messages'] as List;
  }
  final result = <dynamic>[];
  for (final message in messages) {
    if (message == null || message is! Map) continue;
    final content = message['content']?.toString().trim() ?? '';
    if (content.isEmpty) continue;
    result.add(message);
  }
  return result;
}

/// Block briefly until Supabase has restored the session token. On a cold start
/// / background notification tap the handler runs before auth is ready, so the
/// first API call would 401. Returns as soon as a token exists, or when the
/// budget elapses (the retry loop below still covers a token that arrives late).
Future<void> _waitForSession({
  Duration budget = const Duration(seconds: 2),
  Duration step = const Duration(milliseconds: 200),
}) async {
  final deadline = DateTime.now().add(budget);
  while (DateTime.now().isBefore(deadline)) {
    if (await getUserToken() != null) return;
    await Future.delayed(step);
  }
}

/// Resolve an agent session by id BEFORE its chat page is opened from a push
/// notification. Waits for the auth token, then retries the instance fetch so a
/// transient cold-start failure doesn't masquerade as an empty session (the
/// swallow-to-`[]`/`null` behaviour of the shared fetchers is exactly what made
/// a failed load render as a permanently-empty "Waiting for messages" chat).
///
/// - Confirmed 404 → `gone = true` (no retry; the session really is gone).
/// - Reachable + valid → `ok = true` with `instanceData` (+ best-effort
///   `messages` to seed the chat and avoid an empty flash).
/// - Still failing after [attempts] tries → `ok = false, gone = false`
///   (transient); the caller keeps the user on Home rather than opening a dead
///   page it would only have to bounce back.
Future<NotificationPrefetchResult> apiPrefetchNotificationInstance(
  String instanceId, {
  int attempts = 3,
}) async {
  await _waitForSession();

  for (var attempt = 0; attempt < attempts; attempt++) {
    try {
      final instance = await vicoaApiRequest(
          'get', '/api/v1/agent-instances/$instanceId', null);
      if (instance is Map) {
        // The instance is valid; messages are a best-effort bonus. A messages
        // failure must NOT block opening a session we know exists — the chat
        // page re-fetches + streams on open anyway.
        List<dynamic> messages = const [];
        try {
          messages = await vicoaApiRequestComputed<List<dynamic>>(
            'get',
            '/api/v1/agent-instances/$instanceId/messages?limit=10000',
            null,
            _decodeMessages,
          );
        } catch (e) {
          debugPrint('[notif-prefetch] messages fetch failed (non-fatal): $e');
        }
        return NotificationPrefetchResult(
            ok: true, instanceData: instance, messages: messages);
      }
      // Unexpected non-Map body — treat as transient and retry.
      debugPrint('[notif-prefetch] unexpected instance body shape');
    } on ApiException catch (e) {
      // 404 is authoritative: the session no longer exists. Anything else
      // (5xx, empty body, ...) is transient → retry.
      if (e.statusCode == 404) return const NotificationPrefetchResult(gone: true);
      debugPrint('[notif-prefetch] api error ${e.statusCode}: ${e.message}');
    } on AuthenticationException catch (e) {
      debugPrint('[notif-prefetch] auth not ready (${e.statusCode})');
    } on NetworkException catch (e) {
      debugPrint('[notif-prefetch] network error: ${e.message}');
    } on ServiceUnavailableException catch (e) {
      debugPrint('[notif-prefetch] service unavailable: ${e.message}');
    } catch (e) {
      debugPrint('[notif-prefetch] unexpected error: $e');
    }

    // Backoff before the next attempt (skip after the final one).
    if (attempt < attempts - 1) {
      await Future.delayed(Duration(milliseconds: 300 * (attempt + 1)));
    }
  }

  return const NotificationPrefetchResult();
}
