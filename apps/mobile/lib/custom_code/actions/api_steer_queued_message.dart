// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Asks for a still-queued USER message to be steered into the agent's
/// running turn instead of waiting for it to end (the queue sheet's Steer
/// action). The backend only flips `message_metadata.queue.status` to
/// `steer` and broadcasts it; the daemon delivers the message mid-turn and
/// settles the row to `consumed` (with `steered: true`) or back to `queued`.
/// Every flip arrives over the realtime WS `message-update` patch, so the
/// caller only manages an in-flight indicator. Returns false when the message
/// was no longer plainly queued (already picked up, or cancelled).
Future<bool> apiSteerQueuedMessage(String instanceId, String messageId) async {
  try {
    final result = await vicoaApiRequest(
      'post',
      '/api/v1/agent-instances/$instanceId/messages/$messageId/steer',
      null,
    );
    return result is Map && result['steered'] == true;
  } catch (e) {
    debugPrint('Error steering queued message: $e');
    return false;
  }
}
