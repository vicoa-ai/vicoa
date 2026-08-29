// Automatic FlutterFlow imports
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:convert';

import 'vicoa_api_request.dart' show vicoaApiRequestComputed;

/// Top-level parser used by [compute] (via [vicoaApiRequestComputed]) so the
/// JSON decode runs in a background isolate. Large projects can return 30k+
/// file paths (~1–2 MB JSON); decoding that on the UI thread blocks the chat
/// scroll for ~100–300 ms on open.
List<String> _decodeFileMentions(String body) {
  final decoded = json.decode(body);
  if (decoded is Map && decoded['files'] is List) {
    return (decoded['files'] as List).map((e) => e.toString()).toList();
  }
  return const [];
}

/// Fetches available file mentions for a project path from the backend API.
///
/// Returns a list of file path strings that can be mentioned with `@`.
/// Returns an empty list if the request fails or no files are available.
Future<List<String>> apiGetFileMentions(String? projectPath) async {
  try {
    String endpoint = '/api/v1/files';
    if (projectPath != null && projectPath.isNotEmpty) {
      endpoint += '?project_path=${Uri.encodeComponent(projectPath)}';
    }
    return await vicoaApiRequestComputed(
      'get',
      endpoint,
      null,
      _decodeFileMentions,
    );
  } catch (e) {
    debugPrint('Error fetching file mentions: $e');
    return const [];
  }
}
