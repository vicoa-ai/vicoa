import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/l10n/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

class ErrorStateDisplayWidget extends StatelessWidget {
  const ErrorStateDisplayWidget({
    super.key,
    required this.errorType,
    this.errorMessage,
    required this.onRetry,
    required this.onSignInAgain,
  });

  final functions.ErrorType errorType;
  final String? errorMessage;
  final VoidCallback onRetry;
  final VoidCallback onSignInAgain;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: EdgeInsetsDirectional.fromSTEB(20.0, 12.0, 20.0, 0.0),
      padding: EdgeInsets.all(32.0),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            FlutterFlowTheme.of(context).primaryBackground,
            FlutterFlowTheme.of(context).accent1.withValues(alpha: 0.05),
          ],
        ),
        borderRadius: BorderRadius.circular(20.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).alternate.withValues(alpha: 0.2),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.02),
            offset: Offset(0, 4),
            blurRadius: 12.0,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 80.0,
            height: 80.0,
            decoration: BoxDecoration(
              color: functions.getErrorColor(errorType).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(40.0),
            ),
            child: Icon(
              functions.getErrorIcon(errorType),
              color: functions.getErrorColor(errorType),
              size: 40.0,
            ),
          ),
          SizedBox(height: 20.0),
          Text(
            functions.getErrorTitle(errorType),
            style: FlutterFlowTheme.of(context).headlineSmall.override(
                  font: GoogleFonts.sourceSans3(),
                  color: FlutterFlowTheme.of(context).primaryText,
                  fontSize: 21.0,
                  fontWeight: FontWeight.w600,
                ),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: 8.0),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 16.0),
            child: Text(
              errorMessage ?? AppLocalizations.of(context).errorStateDisplayUnexpectedError,
              style: FlutterFlowTheme.of(context).bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: FlutterFlowTheme.of(context).secondaryText,
                    fontSize: 15.0,
                  ),
              textAlign: TextAlign.center,
            ),
          ),
          SizedBox(height: 24.0),
          if (errorType == functions.ErrorType.authentication)
            FFButtonWidget(
              onPressed: () {
                HapticFeedback.lightImpact();
                onSignInAgain();
              },
              text: AppLocalizations.of(context).errorStateDisplaySignInAgain,
              icon: Icon(Icons.login_rounded, size: 20.0),
              options: FFButtonOptions(
                height: 48.0,
                padding: EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                color: FlutterFlowTheme.of(context).primary,
                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                      font: GoogleFonts.sourceSans3(),
                      color: Colors.white,
                      fontSize: 17.0,
                      fontWeight: FontWeight.w600,
                    ),
                elevation: 0,
                borderRadius: BorderRadius.circular(12.0),
              ),
            )
          else
            FFButtonWidget(
              onPressed: () {
                HapticFeedback.lightImpact();
                onRetry();
              },
              text: AppLocalizations.of(context).errorStateDisplayTryAgain,
              icon: Icon(Icons.refresh_rounded, size: 20.0),
              options: FFButtonOptions(
                height: 48.0,
                padding: EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
                color: FlutterFlowTheme.of(context).primary,
                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                      font: GoogleFonts.sourceSans3(),
                      color: Colors.white,
                      fontSize: 17.0,
                      fontWeight: FontWeight.w600,
                    ),
                elevation: 0,
                borderRadius: BorderRadius.circular(12.0),
              ),
            ),
        ],
      ),
    );
  }
}
