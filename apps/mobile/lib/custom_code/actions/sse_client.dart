// Automatic FlutterFlow imports
import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'vicoa_api_request.dart' show getUserToken;
import 'vicoa_api_config.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Open an authenticated SSE connection to the Vicoa backend and return a
/// stream of parsed events.  Each emitted map has:
///   - 'event': the SSE event-type field (e.g. 'instance_updated', 'message',
///              'heartbeat', 'connected'). Defaults to 'message' when the
///              server omits the `event:` line.
///   - 'data':  the JSON-decoded payload from the `data:` line, or `null`
///              if the payload couldn't be parsed.
///
/// `path` is the URL path including any path params (e.g.
/// `/api/v1/agent-instances/stream` or
/// `/api/v1/agent-instances/{id}/messages/stream`).  Authentication is added
/// as a `?token=…` query parameter; do not include it in `path`.
///
/// Throws `Exception` if the connection can't be established (no auth token,
/// non-2xx response, network failure).
Future<Stream<Map<String, dynamic>>> openSseStream(String path) async {
  final userToken = await getUserToken();
  if (userToken == null) {
    throw Exception('User not authenticated.');
  }

  final baseUrl = getVicoaApiBaseUrl();
  final url = Uri.parse('$baseUrl$path').replace(
    queryParameters: {'token': userToken},
  );

  final request = http.Request('GET', url);
  request.headers.addAll({
    'Accept': 'text/event-stream',
    'Cache-Control': 'no-cache',
  });

  final response = await request.send();
  if (response.statusCode != 200) {
    throw Exception('SSE stream returned ${response.statusCode}');
  }

  return _parseSseFrames(response.stream);
}

/// Pure parser: chunked-bytes-from-http → map-per-event stream.  Exposed
/// separately so tests don't need a live HTTP connection.
Stream<Map<String, dynamic>> _parseSseFrames(http.ByteStream byteStream) {
  String? currentEvent;
  return byteStream
      .transform(utf8.decoder)
      .transform(const LineSplitter())
      .map<Map<String, dynamic>?>((line) {
        if (line.startsWith('event: ')) {
          currentEvent = line.substring(7).trim();
          return null;
        }
        if (line.startsWith('data: ')) {
          final jsonData = line.substring(6);
          final event = currentEvent ?? 'message';
          currentEvent = null;
          try {
            return {'event': event, 'data': jsonDecode(jsonData)};
          } catch (e) {
            debugPrint('SSE: malformed data payload for event=$event: $e');
            return null;
          }
        }
        if (line.trim().isEmpty) {
          // Empty line ends an event frame — reset the event tag so the next
          // unprefixed data: line doesn't inherit it.
          currentEvent = null;
        }
        // Other SSE field lines (id:, retry:, comments) are ignored.
        return null;
      })
      .where((e) => e != null)
      .cast<Map<String, dynamic>>();
}
