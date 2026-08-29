// Automatic FlutterFlow imports
import 'package:flutter/foundation.dart';
import 'sse_client.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Connect to the per-instance message SSE endpoint and return a stream of
/// parsed events. Each event is a map with keys:
///   'event': 'message' | 'message_update' | 'status_update' | 'git_diff_update'
///            | 'agent_heartbeat' | 'heartbeat' | 'connected' | 'terminate'
///   'data': dynamic (parsed JSON)
Future<Stream<Map<String, dynamic>>> apiStreamInstanceMessages(
    String instanceId) async {
  debugPrint('[SSE] opening message stream for instance=$instanceId');
  final stream = await openSseStream(
      '/api/v1/agent-instances/$instanceId/messages/stream');
  // Wrap so we can see every raw frame coming off the wire — including
  // heartbeats and any event types we don't dispatch yet. Useful for
  // confirming status_update / message_update arrival.
  // return debugStream(stream);
  return stream;
}

Stream<Map<String, dynamic>> debugStream(Stream<Map<String, dynamic>> stream) {
  return stream.map((event) {
    final eventType = event['event'];
    if (eventType == 'heartbeat') {
      // Quiet; otherwise it spams every 15s.
      return event;
    }
    if (eventType == "message") {
      return event;
    }
    debugPrint('[SSE] raw event="$eventType" data=${event['data']}');
    return event;
  });
}