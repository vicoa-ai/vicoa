// Automatic FlutterFlow imports
import 'sse_client.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Connect to the SSE endpoint /api/v1/agent-instances/stream and return a
/// stream of parsed events. Each event is a map with keys:
///   'event': 'instance_created' | 'instance_updated' | 'heartbeat' | 'connected'
///   'data': dynamic (parsed JSON)
Future<Stream<Map<String, dynamic>>> apiStreamAgentInstances() {
  return openSseStream('/api/v1/agent-instances/stream');
}
