// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Cancels a still-queued USER message before the agent has consumed it.
/// The authoritative status flip (`message_metadata.queue.status` ->
/// `cancelled`) arrives over the realtime WS `message-update` patch, so the
/// caller doesn't need to optimistically mutate local state — just show an
/// in-flight indicator while this is pending.
Future<bool> apiCancelQueuedMessage(String instanceId, String messageId) async {
  try {
    final result = await vicoaApiRequest(
      'post',
      '/api/v1/agent-instances/$instanceId/messages/$messageId/cancel',
      null,
    );
    return result is Map && result['cancelled'] == true;
  } catch (e) {
    debugPrint('Error cancelling queued message: $e');
    return false;
  }
}
