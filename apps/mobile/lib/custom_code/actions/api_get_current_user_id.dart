import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/auth/me — the signed-in user's id as the backend stores it, or
/// null when it can't be read. Task assignees and question addressees carry
/// this id. It is not always `currentUserUid`: an account re-created at the
/// identity provider with the same email gets a new login id but keeps its
/// old row (`find_local_user` in the backend).
Future<String?> apiGetCurrentUserId() async {
  try {
    final profile = await vicoaApiRequest('get', '/api/v1/auth/me', null);
    final id = profile is Map ? profile['id']?.toString() : null;
    return id == null || id.isEmpty ? null : id;
  } catch (e) {
    debugPrint('Error getting current user: $e');
    return null;
  }
}
