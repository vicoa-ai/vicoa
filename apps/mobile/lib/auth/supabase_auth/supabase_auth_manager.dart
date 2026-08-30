import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:gotrue/gotrue.dart' as gotrue;
import 'package:purchases_flutter/purchases_flutter.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:superwallkit_flutter/superwallkit_flutter.dart';
import '/auth/auth_manager.dart';
import '/backend/posthog/posthog_analytics.dart';
import '/backend/supabase/supabase.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/info_dialog/info_dialog_widget.dart';
import '/pages/snack_bar/snack_bar_widget.dart';
import 'email_auth.dart';

import 'supabase_user_provider.dart';

export '/auth/base_auth_user_provider.dart';

class SupabaseAuthManager extends AuthManager
    with EmailSignInManager, AppleSignInManager, GoogleSignInManager {
  static const String _googleWebClientId = '780704364741-evit6ouabplm9nrne6t2e33v2uhf2hah.apps.googleusercontent.com';
  static const String _googleIosClientId = '780704364741-tircrntvs9720p2m07mnk6ved37ptql7.apps.googleusercontent.com';
  static const String _appleServiceId = 'app.vicoa.login';

  // google_sign_in v7.0.0+ uses a singleton pattern
  GoogleSignIn get _googleSignIn => GoogleSignIn.instance;

  @override
  Future signOut() async {
    // Reset billing SDK identity so the next account on this device starts
    // from a fresh anonymous alias. Without this, getRevenueCatUserId() /
    // getSuperWallUserId() on the auth page would still return the previous
    // user's uuid and end up written into the new profile.
    try {
      await Purchases.logOut();
    } catch (e) {
      debugPrint('Purchases.logOut failed: $e');
    }
    try {
      await Superwall.shared.reset();
    } catch (e) {
      debugPrint('Superwall.reset failed: $e');
    }
    await SupaFlow.client.auth.signOut();
  }

  @override
  Future deleteUser(BuildContext context) async {
    try {
      if (!loggedIn) {
        print('Error: delete user attempted with no logged in user!');
        return;
      }
      await currentUser?.delete();
    } on AuthException catch (e) {
      await _showSnackBarSheet(context, '${e.message!}');
    }
  }

  @override
  Future updateEmail({
    required String email,
    required BuildContext context,
  }) async {
    try {
      if (!loggedIn) {
        print('Error: update email attempted with no logged in user!');
        return;
      }
      await currentUser?.updateEmail(email);
    } on AuthException catch (e) {
      await _showSnackBarSheet(context, '${e.message!}');
      return;
    }
    if (!context.mounted) return;
    await _showSnackBarSheet(context, AppLocalizations.of(context).authEmailChangeConfirmationSent);
  }

  @override
  Future updatePassword({
    required String newPassword,
    required BuildContext context,
  }) async {
    try {
      if (!loggedIn) {
        print('Error: update password attempted with no logged in user!');
        return;
      }
      await currentUser?.updatePassword(newPassword);
    } on AuthException catch (e) {
      await _showSnackBarSheet(context, '${e.message!}');
      return;
    }
    await _showSnackBarSheet(context, 'Password updated successfully');
  }

  @override
  Future resetPassword({
    required String email,
    required BuildContext context,
    String? redirectTo,
  }) async {
    try {
      await SupaFlow.client.auth
          .resetPasswordForEmail(email, redirectTo: redirectTo);
    } on AuthException catch (e) {
      await _showSnackBarSheet(context, '${e.message!}');
      return null;
    }
    await _showSnackBarSheet(context, 'Password reset email sent');
  }

  @override
  Future<BaseAuthUser?> signInWithEmail(
    BuildContext context,
    String email,
    String password,
  ) =>
      _signInOrCreateAccount(
        context,
        () => emailSignInFunc(email, password),
      );

  @override
  Future<BaseAuthUser?> createAccountWithEmail(
    BuildContext context,
    String email,
    String password,
  ) =>
      _signInOrCreateAccount(
        context,
        () => emailCreateAccountFunc(email, password),
      );

  @override
  Future<BaseAuthUser?> signInWithApple(BuildContext context) async {
    if (!_isMobilePlatform) {
      return _signInWithOAuth(context, gotrue.OAuthProvider.apple);
    }
    try {
      if (!await SignInWithApple.isAvailable()) {
        return _signInWithOAuth(context, gotrue.OAuthProvider.apple);
      }
      final rawNonce = _generateNonce();
      final hashedNonce = _sha256ofString(rawNonce);
      final credential = await SignInWithApple.getAppleIDCredential(
        scopes: [
          AppleIDAuthorizationScopes.email,
          AppleIDAuthorizationScopes.fullName,
        ],
        nonce: hashedNonce,
      );
      final idToken = credential.identityToken;
      if (idToken == null || idToken.isEmpty) {
        posthogCapture('onboarding_signin_error', properties: {
          'method': 'apple',
          'stage': 'native_no_id_token',
        });
        return null;
      }
      final nonceForSupabase = _idTokenContainsNonceClaim(idToken) ? rawNonce : null;
      final authResponse = await SupaFlow.client.auth.signInWithIdToken(
        provider: gotrue.OAuthProvider.apple,
        idToken: idToken,
        nonce: nonceForSupabase,
      );
      final user = authResponse.user ?? SupaFlow.client.auth.currentUser;
      if (user == null) {
        posthogCapture('onboarding_signin_error', properties: {
          'method': 'apple',
          'stage': 'native_supabase_no_user',
        });
        return null;
      }
      final authUser = VicoaSupabaseUser(user);
      currentUser = authUser;
      AppStateNotifier.instance.update(authUser);
      return authUser;
    } on AuthException catch (e) {
      posthogCapture('onboarding_signin_error', properties: {
        'method': 'apple',
        'stage': 'native_supabase_exchange',
        'error_code': e.statusCode?.toString() ?? '',
        'error_message': _truncateError(e.message),
      });
      await _showAuthFailureDialog(context, 'Error: ${e.message!}');
      return null;
    } catch (e) {
      // Includes user cancellation (SignInWithAppleAuthorizationException),
      // which is expected — error_type lets us separate cancels from real failures.
      posthogCapture('onboarding_signin_error', properties: {
        'method': 'apple',
        'stage': 'native',
        'error_type': e.runtimeType.toString(),
        'error_message': _truncateError(e.toString()),
      });
      return null;
    }
  }

  @override
  Future<BaseAuthUser?> signInWithGoogle(BuildContext context) async {
    if (!_isMobilePlatform) {
      return _signInWithOAuth(context, gotrue.OAuthProvider.google);
    }
    try {
      // Generate a fresh raw nonce for each sign-in attempt
      final rawNonce = _generateNonce();

      // Google expects a hashed nonce during initialization
      final hashedNonce = _sha256ofString(rawNonce);

      // Initialize Google Sign In with the HASHED nonce
      await _initializeGoogleSignIn(hashedNonce);

      // In v7.0.0+, use authenticate() instead of signIn()
      // Pass scopes as scopeHint
      final googleUser = await _googleSignIn.authenticate(
        scopeHint: ['profile', 'email'],
      );
      final auth = googleUser.authentication;
      final idToken = auth.idToken;
      if (idToken == null || idToken.isEmpty) {
        posthogCapture('onboarding_signin_error', properties: {
          'method': 'google',
          'stage': 'native_no_id_token',
        });
        await _showAuthFailureDialog(
          context,
          'Failed to sign in with Google. Please try again or reach out to us at hi@vicoa.ai.',
        );
        return null;
      }

      // Check if the ID token contains a nonce claim
      final idTokenNonce = _extractIdTokenNonce(idToken);

      // Pass the RAW (unhashed) nonce to Supabase if ID token has nonce, otherwise null
      // This is the correct approach per https://github.com/supabase/auth/issues/1926
      final String? nonceForSupabase = idTokenNonce != null ? rawNonce : null;

      // Sign in to Supabase with the RAW nonce
      final authResponse = await SupaFlow.client.auth.signInWithIdToken(
        provider: gotrue.OAuthProvider.google,
        idToken: idToken,
        nonce: nonceForSupabase,
      );

      final user = authResponse.user ?? SupaFlow.client.auth.currentUser;
      if (user == null) {
        posthogCapture('onboarding_signin_error', properties: {
          'method': 'google',
          'stage': 'native_supabase_no_user',
        });
        return null;
      }
      final authUser = VicoaSupabaseUser(user);
      currentUser = authUser;
      AppStateNotifier.instance.update(authUser);
      return authUser;
    } on AuthException catch (e) {
      debugPrint('Native Google sign-in AuthException: ${e.message} (code: ${e.statusCode})');
      posthogCapture('onboarding_signin_error', properties: {
        'method': 'google',
        'stage': 'native_supabase_exchange',
        'error_code': e.statusCode?.toString() ?? '',
        'error_message': _truncateError(e.message),
      });
      await _showAuthFailureDialog(context, 'Failed to sign in with Google. Please try again or reach out to us at hi@vicoa.ai.');
      return _signInWithOAuth(context, gotrue.OAuthProvider.google);
    } catch (e) {
      // Common cause: SHA-1 fingerprint for this build not registered in Google
      // Cloud Console. Add debug/release SHA-1 fingerprints to fix native flow.
      debugPrint('Native Google sign-in failed (falling back to web OAuth): $e');
      posthogCapture('onboarding_signin_error', properties: {
        'method': 'google',
        'stage': 'native',
        'error_type': e.runtimeType.toString(),
        'error_message': _truncateError(e.toString()),
      });
      return _signInWithOAuth(context, gotrue.OAuthProvider.google);
    }
  }

  /// Tries to sign in or create an account using Supabase Auth.
  /// Returns the User object if sign in was successful.
  Future<BaseAuthUser?> _signInOrCreateAccount(
    BuildContext context,
    Future<User?> Function() signInFunc,
  ) async {
    try {
      final user = await signInFunc();
      final authUser = user == null ? null : VicoaSupabaseUser(user);

      // Update currentUser here in case user info needs to be used immediately
      // after a user is signed in. This should be handled by the user stream,
      // but adding here too in case of a race condition where the user stream
      // doesn't assign the currentUser in time.
      if (authUser != null) {
        currentUser = authUser;
        AppStateNotifier.instance.update(authUser);
      }
      return authUser;
    } on AuthException catch (e) {
      final errorMsg = e.message.contains('User already registered')
          ? 'The email is already in use by a different account'
          : e.message.contains('Invalid login credentials')
              ? 'Wrong email or password'
              : '${e.message!}';
      await _showSnackBarSheet(context, errorMsg);
      return null;
    }
  }

  Future<BaseAuthUser?> _signInWithOAuth(
    BuildContext context,
    gotrue.OAuthProvider provider,
  ) async {
    StreamSubscription<gotrue.AuthState>? authSub;
    try {
      // Platform-specific redirect URL
      // iOS: vicoa://login-callback (scheme only)
      // Android: vicoa://vicoa.app/login-callback (requires host as per AndroidManifest.xml)
      final redirectTo = Platform.isIOS
          ? 'vicoa://login-callback'
          : 'vicoa://vicoa.app/login-callback';

      final authCompleter = Completer<User?>();
      authSub = SupaFlow.client.auth.onAuthStateChange.listen(
        (authState) {
          final user =
              authState.session?.user ?? SupaFlow.client.auth.currentUser;
          if (!authCompleter.isCompleted && user != null) {
            authCompleter.complete(user);
          }
        },
        onError: (_) {
          if (!authCompleter.isCompleted) {
            authCompleter.complete(null);
          }
        },
      );

      await SupaFlow.client.auth.signInWithOAuth(
        provider,
        redirectTo: redirectTo,
        authScreenLaunchMode: LaunchMode.externalApplication,
      );

      final user = await authCompleter.future.timeout(
        Duration(seconds: 90),
        onTimeout: () {
          // OAuth may already have completed with no stream event delivered.
          return SupaFlow.client.auth.currentUser;
        },
      );
      if (user == null) {
        posthogCapture('onboarding_signin_error', properties: {
          'method': provider.name,
          'stage': 'oauth_fallback_no_user',
        });
        return null;
      }

      final authUser = VicoaSupabaseUser(user);
      currentUser = authUser;
      AppStateNotifier.instance.update(authUser);
      return authUser;
    } on AuthException catch (e) {
      posthogCapture('onboarding_signin_error', properties: {
        'method': provider.name,
        'stage': 'oauth_fallback_supabase_exchange',
        'error_code': e.statusCode?.toString() ?? '',
        'error_message': _truncateError(e.message),
      });
      await _showAuthFailureDialog(context, 'Error: ${e.message!}');
      return null;
    } catch (e) {
      // Catch any other errors (timeout, cancelled, etc.)
      posthogCapture('onboarding_signin_error', properties: {
        'method': provider.name,
        'stage': 'oauth_fallback',
        'error_type': e.runtimeType.toString(),
        'error_message': _truncateError(e.toString()),
      });
      return null;
    } finally {
      await authSub?.cancel();
    }
  }

  bool get _isMobilePlatform => !kIsWeb && (Platform.isIOS || Platform.isAndroid);

  String _generateNonce([int length = 32]) {
    const charset = '0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._';
    final random = Random.secure();
    return List.generate(length, (_) => charset[random.nextInt(charset.length)]).join();
  }

  /// Truncate error strings before sending to PostHog so we never ship PII
  /// (e.g. tokens, emails) or blow past property size limits.
  String _truncateError(String? raw) {
    if (raw == null || raw.isEmpty) return '';
    final flat = raw.replaceAll(RegExp(r'\s+'), ' ').trim();
    return flat.length > 200 ? '${flat.substring(0, 200)}…' : flat;
  }

  String _sha256ofString(String input) {
    final bytes = utf8.encode(input);
    final digest = sha256.convert(bytes);
    return digest.toString();
  }

  bool _idTokenContainsNonceClaim(String idToken) {
    return _extractIdTokenNonce(idToken) != null;
  }

  String? _extractIdTokenNonce(String idToken) {
    try {
      final parts = idToken.split('.');
      if (parts.length < 2) {
        return null;
      }
      final payload = utf8.decode(base64Url.decode(base64Url.normalize(parts[1])));
      final payloadMap = jsonDecode(payload) as Map<String, dynamic>;
      final nonce = payloadMap['nonce'];
      return nonce is String && nonce.isNotEmpty ? nonce : null;
    } catch (_) {
      return null;
    }
  }

  Future<void> _showAuthFailureDialog(BuildContext context, String content) async {
    if (!context.mounted) {
      return;
    }
    await showDialog(
      context: context,
      builder: (dialogContext) {
        return Dialog(
          elevation: 0,
          insetPadding: EdgeInsets.zero,
          backgroundColor: Colors.transparent,
          alignment: AlignmentDirectional(0.0, 0.0).resolve(Directionality.of(context)),
          child: GestureDetector(
            onTap: () {
              FocusScope.of(dialogContext).unfocus();
              FocusManager.instance.primaryFocus?.unfocus();
            },
            child: InfoDialogWidget(
              title: 'Sign in Failed',
              content: content,
            ),
          ),
        );
      },
    );
  }

  Future<void> _showSnackBarSheet(BuildContext context, String content) async {
    final scaffold = Scaffold.maybeOf(context);
    if (scaffold == null) {
      return;
    }
    scaffold.showBottomSheet(
      (context) {
        return Align(
          alignment: AlignmentDirectional(0.0, 1.0)
              .resolve(Directionality.of(context)),
          child: SnackBarWidget(
            content: content,
            waitTime: 2200,
          ),
        );
      },
      backgroundColor: Colors.transparent,
      enableDrag: false,
    );
  }

  Future<void> _initializeGoogleSignIn(String nonce) {
    // clientId is iOS-only; passing it on Android breaks initialization
    final iosClientId = (!kIsWeb && Platform.isIOS && _googleIosClientId.isNotEmpty)
        ? _googleIosClientId
        : null;
    return _googleSignIn.initialize(
      clientId: iosClientId,
      serverClientId: _googleWebClientId.isEmpty ? null : _googleWebClientId,
      nonce: nonce,
    );
  }

}
