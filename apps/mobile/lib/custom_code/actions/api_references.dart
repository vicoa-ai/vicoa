// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// Candidates for the composer's `#` panel: the user's own sessions, tasks and
/// automations matching [query] (empty = what's live and recent), already
/// kind-ordered so the panel draws a header wherever `kind` changes.
///
/// Errors propagate as [ApiException] so the caller can tell a backend that
/// predates the endpoint (404: hide the trigger) from a passing failure.
Future<List<Map<String, dynamic>>> apiListReferences(
  String query, {
  String? excludeSessionId,
}) async {
  final params = <String, String>{'q': query};
  if (excludeSessionId != null && excludeSessionId.isNotEmpty) {
    params['exclude_session_id'] = excludeSessionId;
  }
  final endpoint =
      Uri(path: '/api/v1/references', queryParameters: params).toString();
  final result = await vicoaApiRequest('get', endpoint, null);
  final items = result is Map ? result['items'] : null;
  if (items is! List) return const [];
  return [
    for (final item in items)
      if (item is Map) Map<String, dynamic>.from(item),
  ];
}

/// One pick expanded into the block appended to the outgoing message
/// (`{kind, id, label, token, context}`). Null on any failure: the composer
/// keeps the one-line fallback it already has.
Future<Map<String, dynamic>?> apiGetReference(String kind, String id) async {
  try {
    final result =
        await vicoaApiRequest('get', '/api/v1/references/$kind/$id', null);
    return result is Map ? Map<String, dynamic>.from(result) : null;
  } catch (e) {
    debugPrint('Error expanding # reference: $e');
    return null;
  }
}
