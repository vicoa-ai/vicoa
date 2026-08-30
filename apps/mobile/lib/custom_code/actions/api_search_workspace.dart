// Automatic FlutterFlow imports
import 'index.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Workspace search — the mobile counterpart of vicoa-web's ⌘K palette. Fans
/// out to sessions + tasks + automations via `GET /api/v1/search` and returns
/// the three grouped lists as raw maps (the app's session/task/automation code
/// all reads dynamic maps, so this stays untyped for consistency).
///
/// Error semantics are left to the caller via [ApiException.statusCode]:
///  * 503 — the backend aborted a slow query; its `detail` asks to refine the
///    term. The caller surfaces a distinct "timed out" message.
///  * 404 — a backend that predates the endpoint (older CLI/desktop-local
///    daemon). The caller degrades to client-side session-only filtering.
Future<Map<String, dynamic>> apiSearchWorkspace(
  String query, {
  int limit = 20,
}) async {
  final term = query.trim();
  if (term.isEmpty) {
    return {'sessions': const [], 'tasks': const [], 'automations': const []};
  }

  final endpoint =
      '/api/v1/search?q=${Uri.encodeQueryComponent(term)}&limit=$limit';
  final result = await vicoaApiRequest('get', endpoint, null);

  if (result is Map) {
    return {
      'sessions': (result['sessions'] as List?) ?? const [],
      'tasks': (result['tasks'] as List?) ?? const [],
      'automations': (result['automations'] as List?) ?? const [],
    };
  }
  return {'sessions': const [], 'tasks': const [], 'automations': const []};
}
