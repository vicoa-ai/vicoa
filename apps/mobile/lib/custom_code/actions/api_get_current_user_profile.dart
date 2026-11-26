import 'package:flutter/foundation.dart';

import 'index.dart';

/// GET /api/v1/auth/me: the signed-in user's backend profile (`id`,
/// `display_name`, `email`, `avatar_image_uri`, `avatar_emoji`, `updated_at`),
/// or null when it can't be read. See `apiGetCurrentUserId` for why the id is
/// not always `currentUserUid`.
Future<Map<String, dynamic>?> apiGetCurrentUserProfile() async {
  try {
    final profile = await vicoaApiRequest('get', '/api/v1/auth/me', null);
    return profile is Map ? Map<String, dynamic>.from(profile) : null;
  } catch (e) {
    debugPrint('Error getting current user profile: $e');
    return null;
  }
}
