// Automatic FlutterFlow imports
// ignore: unused_import
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'vicoa_api_config.dart';
import 'vicoa_api_request.dart' show getUserToken;

/// Uploads one picked file as multipart/form-data to POST /api/v1/attachments.
///
/// Images are re-encoded by the backend (EXIF stripped, long edge capped);
/// any other file type is stored verbatim (the backend enforces the size cap
/// and executable blocklist). [filename] overrides the multipart part name so
/// the backend resolves the correct type/extension for non-image picks whose
/// on-disk path may not carry the original name. Returns the attachment map
/// `{id, mime_type, size_bytes, width, height, filename}` or null on failure.
Future<dynamic> apiUploadAttachment(
  String instanceId,
  String filePath, [
  String? filename,
]) async {
  try {
    final token = await getUserToken();
    if (token == null) {
      debugPrint('Attachment upload skipped: no auth token');
      return null;
    }
    final uri = Uri.parse('${getVicoaApiBaseUrl()}/api/v1/attachments');
    final request = http.MultipartRequest('POST', uri)
      ..headers['Authorization'] = 'Bearer $token'
      ..fields['agent_instance_id'] = instanceId
      ..files.add(
          await http.MultipartFile.fromPath('file', filePath, filename: filename));
    final streamed = await request.send().timeout(const Duration(seconds: 60));
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 200) {
      debugPrint('Attachment upload failed (${streamed.statusCode}): $body');
      return null;
    }
    return json.decode(body);
  } catch (e) {
    debugPrint('Error uploading attachment: $e');
    return null;
  }
}
