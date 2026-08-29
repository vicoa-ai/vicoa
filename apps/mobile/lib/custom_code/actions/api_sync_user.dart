// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiSyncUser() async {
  try {
    // Get current user info from Supabase
    final user = SupaFlow.client.auth.currentUser;
    if (user == null) {
      print('No authenticated user found');
      return null;
    }

    if (user.email == null) {
      print('User email is required');
      return null;
    }

    final metadata = user.userMetadata ?? const {};
    final displayName = (metadata['full_name'] ??
            metadata['name'] ??
            metadata['display_name'] ??
            '')
        .toString();

    // Prepare request body according to SyncUserRequest schema
    final body = {
      'id': user.id,
      'email': user.email,
      'display_name': displayName,
    };

    // Call the correct API endpoint
    final result = await vicoaApiRequest('post', '/api/v1/auth/sync-user', body);
    return result;
  } catch (e) {
    debugPrint('Error syncing user: $e');
    return null;
  }
}
