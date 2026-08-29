import '/actions/actions.dart' as action_blocks;
import '/auth/supabase_auth/auth_util.dart';
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/custom_functions.dart' as functions;
import '/l10n/app_localizations.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/backend/posthog/posthog_analytics.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/index.dart';
import 'dart:io' show Platform;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class AuthOptionsWidget extends StatefulWidget {
  const AuthOptionsWidget({super.key});

  static String routeName = 'AuthOptions';
  static String routePath = '/authOptions';

  @override
  State<AuthOptionsWidget> createState() => _AuthOptionsWidgetState();
}

class _AuthOptionsWidgetState extends State<AuthOptionsWidget> with RouteAware {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  bool _isSocialSignInInProgress = false;
  String? _superWallUserId;
  String? _revenueCatUserId;
  DateTime? _screenEnteredAt;
  bool _authMethodPicked = false;

  @override
  void initState() {
    super.initState();
    _screenEnteredAt = DateTime.now();
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'AuthOptions'});
    posthogScreen('AuthOptions');
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      logFirebaseEvent('AUTH_OPTIONS_PAGE_ON_INIT_STATE');
      _superWallUserId = await actions.getSuperWallUserId();
      _revenueCatUserId = await actions.getRevenueCatUserId();
      if (FFAppState().user == null) {
        FFAppState().user = UserStruct(
          superWallUserId: _superWallUserId,
          revenueCatId: _revenueCatUserId,
        );
      }
      if (FFAppState().credit == null) {
        FFAppState().credit = CreditStruct(balance: 0);
      }
      if (mounted) {
        setState(() {});
      }
    });
  }

  @override
  void dispose() {
    // Diagnoses the news→auth 45% funnel drop: distinguishes "saw the screen
    // and bounced fast" from "sat and read it." Tap-through is captured via
    // [_authMethodPicked]; PostHog's $screen already records arrivals.
    final enteredAt = _screenEnteredAt;
    if (enteredAt != null) {
      final ms = DateTime.now().difference(enteredAt).inMilliseconds;
      posthogCapture('onboarding_auth_options_left', properties: {
        'time_on_screen_ms': ms,
        'picked_method': _authMethodPicked,
      });
    }
    routeObserver.unsubscribe(this);
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final route = DebugModalRoute.of(context);
    if (route != null) {
      routeObserver.subscribe(this, route);
    }
    debugLogGlobalProperty(context);
  }

  Future<void> _handleSocialSignIn(
    Future<BaseAuthUser?> Function() signIn,
    String method,
  ) async {
    if (_isSocialSignInInProgress) {
      return;
    }

    try {
      final user = await signIn();
      final recoveredSupabaseUser = SupaFlow.client.auth.currentUser;
      if (user == null && recoveredSupabaseUser == null) {
        logFirebaseEvent('AUTH_OPTIONS_SIGNIN_${method.toUpperCase()}_FAILED');
        // Manager already captured a granular onboarding_signin_error with a
        // 'stage'; this top-level event closes the funnel so we can compare
        // method-selected vs. silent-return rates regardless of stage.
        posthogCapture('onboarding_signin_error', properties: {
          'method': method,
          'stage': 'returned_null',
        });
        return;
      }

      // Sign-in succeeded, disable other buttons
      if (mounted) {
        setState(() {
          _isSocialSignInInProgress = true;
        });
      }

      final supabaseUser = recoveredSupabaseUser;
      final metadata = supabaseUser?.userMetadata ?? const {};
      final resolvedEmail = supabaseUser?.email ?? currentUserEmail;
      final resolvedName = (metadata['full_name'] ?? metadata['name'] ?? metadata['display_name'] ?? currentUserDisplayName).toString();

      FFAppState().updateUserStruct((user) => user
        ..id = currentUserUid
        ..email = resolvedEmail
        ..name = resolvedName);

      final existingProfile = await SupaFlow.client.from('profiles').select('id').eq('id', currentUserUid).maybeSingle();
      final isNewUser = existingProfile == null;

      if (isNewUser) {
        await actions.supabaseCreateProfile(currentUserUid, _superWallUserId, _revenueCatUserId);
      }

      try {
        await actions.supabaseSyncDown(DateTime.now());
      } catch (e) {
        debugPrint('Failed to sync down after social sign-in: $e');
      }
      try {
        await actions.apiSyncUser();
      } catch (e) {
        debugPrint('Failed to sync user after social sign-in: $e');
      }
      await action_blocks.postAuth(context, superWallUserId: _superWallUserId, revenueCatUserId: _revenueCatUserId);

      final hasSignUpCredit = FFAppState().creditTransactions.any((e) => e.name == 'Sign Up');
      if (!hasSignUpCredit) {
        await action_blocks.grantCredit(context, creditGranted: 50, name: 'Sign Up');
      }

      if (isNewUser) {
        await actions.apiKitSubscription(FFAppState().user.email);
        logFirebaseEvent('AUTH_OPTIONS_SIGNUP_${method.toUpperCase()}_COMPLETED');
        posthogCapture('onboarding_signup_completed', properties: {'method': method});
        posthogIdentify(
          userId: currentUserUid,
          userProperties: {'email': resolvedEmail, 'name': resolvedName, 'signup_method': method},
          userPropertiesSetOnce: {'signup_origin': 'app'},
        );
      } else {
        logFirebaseEvent('AUTH_OPTIONS_SIGNIN_${method.toUpperCase()}_COMPLETED');
        posthogCapture('onboarding_signin_completed', properties: {'method': method});
        posthogIdentify(
          userId: currentUserUid,
          userProperties: {'email': resolvedEmail, 'name': resolvedName},
        );
      }

      if (mounted) {
        context.goNamedAuth(HomeWidget.routeName, context.mounted);
      }
    } catch (e) {
      logFirebaseEvent('AUTH_OPTIONS_SIGNIN_${method.toUpperCase()}_ERROR');
      posthogCapture('onboarding_signin_error', properties: {'method': method});
      debugPrint('Social sign-in flow failed: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isSocialSignInInProgress = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    context.watch<FFAppState>();

    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
        FocusManager.instance.primaryFocus?.unfocus();
      },
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
        body: SafeArea(
          top: true,
          child: Row(
            mainAxisSize: MainAxisSize.max,
            children: [
              Expanded(
                child: SingleChildScrollView(
                  child: Container(
                    width: double.infinity,
                    constraints: BoxConstraints(maxWidth: 430.0),
                    padding: EdgeInsetsDirectional.fromSTEB(24.0, 18.0, 24.0, 24.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Align(
                          alignment: AlignmentDirectional(0.0, 0.0),
                          child: Padding(
                            padding: EdgeInsetsDirectional.fromSTEB(0.0, 8.0, 0.0, 0.0),
                            child: Container(
                              width: 70.0,
                              height: 70.0,
                              decoration: BoxDecoration(
                                color: FlutterFlowTheme.of(context).secondaryBackground,
                                borderRadius: BorderRadius.circular(20.0),
                                boxShadow: [BoxShadow(blurRadius: 12.0, color: Color(0x1A000000), offset: Offset(0.0, 4.0))],
                              ),
                              alignment: AlignmentDirectional(0.0, 0.0),
                              child: ClipRRect(
                                borderRadius: BorderRadius.circular(8.0),
                                child: Image.asset('assets/images/vicoa-light.webp', width: 45.0, height: 45.0, fit: BoxFit.cover),
                              ),
                            ),
                          ),
                        ),
                        Align(
                          alignment: AlignmentDirectional(0.0, 0.0),
                          child: Padding(
                            padding: EdgeInsetsDirectional.fromSTEB(0.0, 24.0, 0.0, 32.0),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  l10n.authOptionsTitle,
                                  textAlign: TextAlign.center,
                                  style: FlutterFlowTheme.of(context).headlineLarge.override(
                                        font: GoogleFonts.sourceSans3(
                                          fontWeight: FontWeight.normal,
                                          fontStyle: FlutterFlowTheme.of(context).headlineLarge.fontStyle,
                                        ),
                                        color: FlutterFlowTheme.of(context).themeText,
                                        fontSize: 30.0,
                                        letterSpacing: -0.3,
                                        fontWeight: FontWeight.normal,
                                        fontStyle: FlutterFlowTheme.of(context).headlineLarge.fontStyle,
                                        lineHeight: 1.3,
                                      ),
                                ),
                                Padding(
                                  padding: EdgeInsetsDirectional.fromSTEB(0.0, 8.0, 0.0, 0.0),
                                  child: Text(
                                    // 'Continue to ${functions.getMotivationPhrase()} with coding agents from your phone',
                                    l10n.authOptionsSubtitle,
                                    textAlign: TextAlign.center,
                                    style: FlutterFlowTheme.of(context).bodyMedium.override(
                                          font: GoogleFonts.sourceSans3(
                                            fontWeight: FontWeight.normal,
                                            fontStyle: FlutterFlowTheme.of(context).bodyMedium.fontStyle,
                                          ),
                                          color: FlutterFlowTheme.of(context).secondaryText,
                                          fontSize: 16.0,
                                          letterSpacing: 0.0,
                                          fontWeight: FontWeight.normal,
                                          fontStyle: FlutterFlowTheme.of(context).bodyMedium.fontStyle,
                                          lineHeight: 1.5,
                                        ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        Padding(
                          padding: EdgeInsetsDirectional.fromSTEB(0.0, 8.0, 0.0, 24.0),
                          child: FFButtonWidget(
                            onPressed: _isSocialSignInInProgress
                                ? null
                                : () async {
                                    logFirebaseEvent('AUTH_OPTIONS_CONTINUE_GOOGLE_BTN_ON_TAP');
                                    posthogCapture('onboarding_auth_method_selected', properties: {'method': 'google'});
                                    _authMethodPicked = true;
                                    HapticFeedback.lightImpact();
                                    await _handleSocialSignIn(() => authManager.signInWithGoogle(context), 'google');
                                  },
                            icon: FaIcon(FontAwesomeIcons.google, color: Colors.white, size: 18.0),
                            text: l10n.authOptionsContinueWithGoogle,
                            showLoadingIndicator: true,
                            options: FFButtonOptions(
                              width: double.infinity,
                              height: 56.0,
                              color: Color(0x75707070),
                              textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                                    font: GoogleFonts.sourceSans3(
                                      fontWeight: FontWeight.w500,
                                      fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                                    ),
                                    color: Colors.white,
                                    fontSize: 18.0,
                                    letterSpacing: 0.0,
                                    fontWeight: FontWeight.w500,
                                    fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                                  ),
                              elevation: 0.0,
                              borderSide: BorderSide(color: Color(0x1AFFFFFF), width: 1.0),
                              borderRadius: BorderRadius.circular(28.0),
                              hoverColor: Color(0x402B2B2B),
                            ),
                          ),
                        ),
                        if (!Platform.isAndroid)
                          Padding(
                            padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 24.0),
                            child: FFButtonWidget(
                              onPressed: _isSocialSignInInProgress
                                  ? null
                                  : () async {
                                      logFirebaseEvent('AUTH_OPTIONS_CONTINUE_APPLE_BTN_ON_TAP');
                                      posthogCapture('onboarding_auth_method_selected', properties: {'method': 'apple'});
                                      _authMethodPicked = true;
                                      HapticFeedback.lightImpact();
                                      await _handleSocialSignIn(() => authManager.signInWithApple(context), 'apple');
                                    },
                              icon: FaIcon(FontAwesomeIcons.apple, color: Colors.white, size: 18.0),
                              text: l10n.authOptionsContinueWithApple,
                              showLoadingIndicator: true,
                              options: FFButtonOptions(
                                width: double.infinity,
                                height: 56.0,
                                color: Color(0x75707070),
                                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                                      font: GoogleFonts.sourceSans3(
                                        fontWeight: FontWeight.w500,
                                        fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                                      ),
                                      color: Colors.white,
                                      fontSize: 18.0,
                                      letterSpacing: 0.0,
                                      fontWeight: FontWeight.w500,
                                      fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                                    ),
                                elevation: 0.0,
                                borderSide: BorderSide(color: Color(0x1AFFFFFF), width: 1.0),
                                borderRadius: BorderRadius.circular(28.0),
                                hoverColor: Color(0x402B2B2B),
                              ),
                            ),
                          ),
                        Padding(
                          padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 50.0),
                          child: FFButtonWidget(
                            onPressed: () async {
                              logFirebaseEvent('AUTH_OPTIONS_CONTINUE_EMAIL_BTN_ON_TAP');
                              posthogCapture('onboarding_auth_method_selected', properties: {'method': 'email'});
                              _authMethodPicked = true;
                              HapticFeedback.lightImpact();
                              context.pushNamed(SignUpWidget.routeName);
                            },
                            text: l10n.authOptionsContinueWithEmail,
                            options: FFButtonOptions(
                              width: double.infinity,
                              height: 56.0,
                              color: Color(0x75707070),
                              textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                                    font: GoogleFonts.sourceSans3(
                                      fontWeight: FontWeight.w500,
                                      fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                                    ),
                                    color: Colors.white,
                                    fontSize: 18.0,
                                    letterSpacing: 0.0,
                                    fontWeight: FontWeight.w500,
                                    fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                                  ),
                              elevation: 0.0,
                              borderSide: BorderSide(color: Color(0x1AFFFFFF), width: 1.0),
                              borderRadius: BorderRadius.circular(28.0),
                              hoverColor: Color(0x402B2B2B),
                            ),
                          ),
                        ),
                        Padding(
                          padding: EdgeInsetsDirectional.fromSTEB(0.0, 16.0, 0.0, 0.0),
                          child: Align(
                            alignment: AlignmentDirectional(0.0, 0.0),
                            child: RichText(
                            textAlign: TextAlign.center,
                            textScaler: MediaQuery.of(context).textScaler,
                            text: TextSpan(
                              children: [
                                TextSpan(
                                  text: l10n.authOptionsLegalPrefix,
                                  style: FlutterFlowTheme.of(context).bodySmall.override(
                                        font: GoogleFonts.sourceSans3(
                                          fontWeight: FontWeight.normal,
                                          fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                        ),
                                        color: FlutterFlowTheme.of(context).secondaryText,
                                        fontSize: 16.0,
                                        letterSpacing: 0.0,
                                        fontWeight: FontWeight.normal,
                                        fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                      ),
                                ),
                                TextSpan(
                                  text: l10n.authOptionsPrivacyPolicy,
                                  style: FlutterFlowTheme.of(context).bodySmall.override(
                                        font: GoogleFonts.sourceSans3(
                                          fontWeight: FontWeight.normal,
                                          fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                        ),
                                        color: FlutterFlowTheme.of(context).primaryText,
                                        fontSize: 16.0,
                                        letterSpacing: 0.0,
                                        fontWeight: FontWeight.normal,
                                        fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                      ),
                                  recognizer: TapGestureRecognizer()
                                    ..onTap = () async {
                                      HapticFeedback.lightImpact();
                                      await launchURL('https://vicoa.ai/privacy');
                                    },
                                ),
                                TextSpan(
                                  text: l10n.authOptionsAndConnector,
                                  style: FlutterFlowTheme.of(context).bodySmall.override(
                                        font: GoogleFonts.sourceSans3(
                                          fontWeight: FontWeight.normal,
                                          fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                        ),
                                        color: FlutterFlowTheme.of(context).secondaryText,
                                        fontSize: 16.0,
                                        letterSpacing: 0.0,
                                        fontWeight: FontWeight.normal,
                                        fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                      ),
                                ),
                                TextSpan(
                                  text: l10n.authOptionsTermsOfUse,
                                  style: FlutterFlowTheme.of(context).bodySmall.override(
                                        font: GoogleFonts.sourceSans3(
                                          fontWeight: FontWeight.normal,
                                          fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                        ),
                                        color: FlutterFlowTheme.of(context).primaryText,
                                        fontSize: 16.0,
                                        letterSpacing: 0.0,
                                        fontWeight: FontWeight.normal,
                                        fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                      ),
                                  recognizer: TapGestureRecognizer()
                                    ..onTap = () async {
                                      HapticFeedback.lightImpact();
                                      await launchURL('https://vicoa.ai/terms');
                                    },
                                ),
                                TextSpan(
                                  text: '.',
                                  style: FlutterFlowTheme.of(context).bodySmall.override(
                                        font: GoogleFonts.sourceSans3(
                                          fontWeight: FontWeight.normal,
                                          fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                        ),
                                        color: FlutterFlowTheme.of(context).secondaryText,
                                        fontSize: 16.0,
                                        letterSpacing: 0.0,
                                        fontWeight: FontWeight.normal,
                                        fontStyle: FlutterFlowTheme.of(context).bodySmall.fontStyle,
                                      ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
