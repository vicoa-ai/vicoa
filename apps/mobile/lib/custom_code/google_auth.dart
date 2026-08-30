import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';

GoogleSignIn get _googleSignIn => GoogleSignIn.instance;
Future<void>? _googleInitFuture;

Future<UserCredential?> googleSignInFunc() async {
  if (kIsWeb) {
    // Once signed in, return the UserCredential
    return await FirebaseAuth.instance.signInWithPopup(GoogleAuthProvider());
  }

  _googleInitFuture ??= _googleSignIn.initialize();
  await _googleInitFuture;

  await signOutWithGoogle().catchError((_) => null);
  final user = await _googleSignIn.authenticate(
    scopeHint: ['profile', 'email'],
  );
  final auth = user.authentication;
  if (auth.idToken == null || auth.idToken!.isEmpty) {
    return null;
  }
  final credential = GoogleAuthProvider.credential(
      idToken: auth.idToken);
  return FirebaseAuth.instance.signInWithCredential(credential);
}

Future signOutWithGoogle() => _googleSignIn.signOut();
