// Automatic FlutterFlow imports
import '/auth/supabase_auth/supabase_user_provider.dart';
import '/backend/supabase/supabase.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

/// What [apiAddEmail] did; the Add email page picks its message from it.
enum AddEmailOutcome { added, taken, invalid, failed }

/// Gives the signed-in account an email when it has none. Some Apple IDs
/// (registered with a phone number) share no address, and the backend cannot
/// create an account without one, so every API call 401s until this is done.
///
/// The backend writes the address to Supabase, then the session is refreshed
/// so the token carries it and the next request creates the account.
Future<AddEmailOutcome> apiAddEmail(String email) async {
  try {
    await vicoaApiRequest('post', '/api/v1/auth/email', {'email': email});
  } on ApiException catch (e) {
    final outcome = addEmailFailureOutcome(e.statusCode, e.details);
    if (outcome != null) {
      debugPrint('apiAddEmail failed: $e');
      return outcome;
    }
  } catch (e) {
    debugPrint('apiAddEmail failed: $e');
    return AddEmailOutcome.failed;
  }

  try {
    await SupaFlow.client.auth.refreshSession();
  } catch (e) {
    debugPrint('apiAddEmail: session refresh failed: $e');
    return AddEmailOutcome.failed;
  }
  final user = SupaFlow.client.auth.currentUser;
  if (user == null || (user.email ?? '').isEmpty) {
    return AddEmailOutcome.failed;
  }
  // The auth stream debounces token refreshes by a second; update now so
  // `currentUserEmail` is right for whatever runs next (postAuth reads it).
  final authUser = VicoaSupabaseUser(user);
  currentUser = authUser;
  AppStateNotifier.instance.update(authUser);
  FFAppState().updateUserStruct((e) => e..email = user.email);
  return AddEmailOutcome.added;
}

/// Reads a refused `POST /auth/email`. Null means the account has an email
/// already: an earlier attempt saved it, then its session refresh failed, so
/// the caller should carry on and refresh again.
AddEmailOutcome? addEmailFailureOutcome(int statusCode, dynamic details) {
  final detail = details is Map ? details['detail'] : null;
  if (statusCode == 409 && detail == 'account_has_email') return null;
  if (statusCode == 409 && detail == 'email_taken') return AddEmailOutcome.taken;
  if (statusCode == 422) return AddEmailOutcome.invalid;
  return AddEmailOutcome.failed;
}
