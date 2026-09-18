// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:async';

import '/backend/posthog/posthog_analytics.dart';

Future<dynamic> apiChatWithAgent(
  String instanceId,
  String message, {
  List<String> attachmentIds = const [],
}) async {
  try {
    final body = {
      'content': message,
      if (attachmentIds.isNotEmpty) 'attachment_ids': attachmentIds,
    };

    final result = await vicoaApiRequest('post', '/api/v1/agent-instances/$instanceId/messages', body);
    return result;
  } catch (e) {
    debugPrint('Error chatting with agent: $e');
    // Callers only ever see `null`, so this is the last place the reason for a
    // failed send still exists. Record it so send failures show up in
    // analytics instead of only in a user's bug report.
    await posthogCapture('mobile_message_send_failed', properties: {
      'reason': _sendFailureReason(e),
    });
    return null;
  }
}

/// Coarse bucket for a failed send, following the exception types
/// [vicoaApiRequest] raises. Deliberately low-cardinality so it groups in
/// analytics; a stalled request reaches us as a [TimeoutException] wrapped in
/// whichever class the reachability probe picked.
String _sendFailureReason(Object error) {
  if (error is ServiceUnavailableException) {
    return error.originalError is TimeoutException
        ? 'timeout'
        : 'service_unavailable';
  }
  if (error is NetworkException) {
    return error.originalError is TimeoutException ? 'timeout' : 'network';
  }
  if (error is AuthenticationException) return 'auth';
  if (error is ApiException) return 'api_${error.statusCode}';
  return 'unknown';
}