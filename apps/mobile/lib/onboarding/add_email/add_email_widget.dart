import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/backend/posthog/posthog_analytics.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/index.dart';
import '/l10n/app_localizations.dart';
import 'add_email_model.dart';
export 'add_email_model.dart';

/// Asks a signed-in account with no email for one. Some Apple IDs (registered
/// with a phone number) share none, and the backend cannot create an account
/// without it, so the app is unusable until this is done. There is no skip:
/// the only ways out are saving an address or signing out.
///
/// Reached two ways: pushed by AuthOptions right after such a sign-in
/// ([fromSignIn], which pops with the result and lets AuthOptions finish
/// onboarding), or as the root page for an account already signed in from
/// before this page existed.
class AddEmailWidget extends StatefulWidget {
  const AddEmailWidget({super.key, this.fromSignIn = false});

  final bool fromSignIn;

  static String routeName = 'AddEmail';
  static String routePath = '/addEmail';

  @override
  State<AddEmailWidget> createState() => _AddEmailWidgetState();
}

class _AddEmailWidgetState extends State<AddEmailWidget> {
  late AddEmailModel _model;

  String get _source => widget.fromSignIn ? 'sign_in' : 'app_start';

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => AddEmailModel());
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'AddEmail'});
    posthogCapture('onboarding_email_prompt_shown', properties: {'source': _source});
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_model.isSaving) return;
    FocusScope.of(context).unfocus();
    final added = await _model.submit();
    posthogCapture('onboarding_email_submitted', properties: {'source': _source, 'outcome': _model.outcome?.name ?? ''});
    if (!added || !mounted) return;
    if (widget.fromSignIn) {
      context.pop(true);
      return;
    }
    // Signed in before this page existed: the sign-in steps that need the
    // backend all failed then. The first call creates the account; the
    // reconcile restores a subscription bought in the meantime.
    await actions.apiSyncUser();
    unawaited(actions.apiReconcileSuperwallSubscription());
    if (!mounted) return;
    context.goNamedAuth(HomeWidget.routeName, context.mounted);
  }

  Future<void> _signOut() async {
    HapticFeedback.lightImpact();
    if (widget.fromSignIn) {
      context.pop(false);
      return;
    }
    GoRouter.of(context).prepareAuthEvent();
    await actions.signOutAndClearLocalData();
    if (!mounted) return;
    GoRouter.of(context).clearRedirectLocation();
    context.goNamed(AuthOptionsWidget.routeName, queryParameters: {'mode': 'login'});
  }

  String? _message(AppLocalizations l10n) {
    switch (_model.outcome) {
      case actions.AddEmailOutcome.invalid:
        return l10n.authAddEmailInvalid;
      case actions.AddEmailOutcome.taken:
        return l10n.authAddEmailTaken;
      case actions.AddEmailOutcome.failed:
        return l10n.authAddEmailFailed;
      case actions.AddEmailOutcome.added:
      case null:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final theme = FlutterFlowTheme.of(context);
    final message = _message(l10n);

    return PopScope(
      canPop: false,
      child: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Scaffold(
          backgroundColor: theme.secondaryBackground,
          body: SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsetsDirectional.fromSTEB(24.0, 18.0, 24.0, 32.0),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 430.0),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Icon(Icons.mail_outline_rounded, size: 44.0, color: theme.primary),
                      Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(0.0, 20.0, 0.0, 0.0),
                        child: Text(
                          l10n.authAddEmailTitle,
                          textAlign: TextAlign.center,
                          style: theme.headlineLarge.override(font: GoogleFonts.sourceSans3(), color: theme.themeText, fontSize: 30.0, letterSpacing: -0.3, lineHeight: 1.3),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(0.0, 8.0, 0.0, 28.0),
                        child: Text(
                          l10n.authAddEmailSubtitle,
                          textAlign: TextAlign.center,
                          style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 16.0, letterSpacing: 0.0, lineHeight: 1.5),
                        ),
                      ),
                      TextFormField(
                        controller: _model.emailController,
                        focusNode: _model.emailFocusNode,
                        autofocus: true,
                        enabled: !_model.isSaving,
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.email],
                        autocorrect: false,
                        enableSuggestions: false,
                        textInputAction: TextInputAction.done,
                        onFieldSubmitted: (_) => _submit(),
                        onChanged: (_) {
                          if (_model.outcome != null) safeSetState(() => _model.outcome = null);
                        },
                        style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.themeText, fontSize: 16.0, letterSpacing: 0.0),
                        decoration: InputDecoration(
                          hintText: l10n.authAddEmailHint,
                          hintStyle: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 16.0, letterSpacing: 0.0),
                          filled: true,
                          fillColor: theme.primaryBackground,
                          contentPadding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 16.0),
                          enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: theme.alternate, width: 1.0), borderRadius: BorderRadius.circular(12.0)),
                          focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: theme.primary, width: 2.0), borderRadius: BorderRadius.circular(12.0)),
                          disabledBorder: OutlineInputBorder(borderSide: BorderSide(color: theme.alternate, width: 1.0), borderRadius: BorderRadius.circular(12.0)),
                        ),
                      ),
                      if (message != null)
                        Padding(
                          padding: const EdgeInsetsDirectional.fromSTEB(4.0, 10.0, 4.0, 0.0),
                          child: Text(
                            message,
                            style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.error, fontSize: 14.0, letterSpacing: 0.0, lineHeight: 1.4),
                          ),
                        ),
                      Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(0.0, 24.0, 0.0, 12.0),
                        child: FFButtonWidget(
                          onPressed: _model.isSaving ? null : _submit,
                          text: l10n.commonContinue,
                          showLoadingIndicator: true,
                          options: FFButtonOptions(
                            width: double.infinity,
                            height: 56.0,
                            color: theme.primary,
                            textStyle: theme.titleSmall.override(font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500), color: Colors.white, fontSize: 18.0, letterSpacing: 0.0, fontWeight: FontWeight.w500),
                            elevation: 0.0,
                            borderRadius: BorderRadius.circular(28.0),
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: _model.isSaving ? null : _signOut,
                        child: Text(
                          l10n.commonSignOut,
                          style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 16.0, letterSpacing: 0.0),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
