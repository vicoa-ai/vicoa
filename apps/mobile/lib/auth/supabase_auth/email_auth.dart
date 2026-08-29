import '/backend/supabase/supabase.dart';

Future<User?> emailSignInFunc(
  String email,
  String password,
) async {
  final AuthResponse res = await SupaFlow.client.auth
      .signInWithPassword(email: email, password: password);
  return res.user;
}

Future<User?> emailCreateAccountFunc(
  String email,
  String password,
) async {
  final AuthResponse res =
      await SupaFlow.client.auth.signUp(email: email, password: password);

  // If the Supabase project is configured to not let users sign in until the
  // email has been confirmed, the user returned in the AuthResponse still has
  // all the user info. But since the user shouldn't be able to sign in without
  // their email verified, return a null User.
  return res.user?.lastSignInAt == null ? null : res.user;
}
