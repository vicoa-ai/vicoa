import 'dart:io';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/l10n/app_localizations.dart';
import '/custom_code/actions/index.dart' as actions;
import '/pages/snack_bar/snack_bar_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'review_dialog_model.dart';
export 'review_dialog_model.dart';

class ReviewDialogWidget extends StatefulWidget {
  const ReviewDialogWidget({super.key});

  @override
  State<ReviewDialogWidget> createState() => _ReviewDialogWidgetState();
}

class _ReviewDialogWidgetState extends State<ReviewDialogWidget> {
  late ReviewDialogModel _model;

  final TextEditingController _feedbackController = TextEditingController();
  final FocusNode _feedbackFocusNode = FocusNode();
  bool _isSubmittingFeedback = false;

  static const int _feedbackMaxLength = 500;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ReviewDialogModel());
  }

  @override
  void dispose() {
    _feedbackController.dispose();
    _feedbackFocusNode.dispose();
    _model.dispose();

    super.dispose();
  }

  Future<void> _submitFeedback() async {
    final message = _feedbackController.text.trim();
    if (message.isEmpty || _isSubmittingFeedback) return;

    setState(() => _isSubmittingFeedback = true);

    final appVersion = FFAppState().appVersion;
    final platform = Platform.operatingSystem;
    final osVersion = Platform.operatingSystemVersion;
    final userEmail = FFAppState().user.email;
    final fullMessage =
        '$message\n\n---\nSource: review_dialog\nUser: $userEmail\nApp Version: $appVersion\nPlatform: $platform\nOS: $osVersion';

    final success = await actions.apiReportIssue(fullMessage);
    if (!mounted) return;

    setState(() => _isSubmittingFeedback = false);
    Navigator.pop(context);
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.transparent,
      isScrollControlled: true,
      enableDrag: false,
      builder: (context) => SnackBarWidget(
        content: success
            ? AppLocalizations.of(context).reviewDialogThankYou
            : AppLocalizations.of(context).reviewDialogSendFailed,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();

    return Container(
      width: double.infinity,
      constraints: BoxConstraints(maxWidth: 400.0),
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).secondaryBackground,
        borderRadius: BorderRadius.circular(24.0),
      ),
      child: Padding(
        padding: EdgeInsetsDirectional.fromSTEB(24.0, 24.0, 24.0, 40.0),
        child: _buildPage(),
      ),
    );
  }

  Widget _buildPage() {
    switch (_model.currentPage) {
      case 0:
        return _buildInitialPage();
      case 1:
        return _buildLoveItPage();
      case 2:
        return _buildNeedsWorkPage();
      default:
        return _buildInitialPage();
    }
  }

  // Initial page: "Enjoying Vicoa?"
  Widget _buildInitialPage() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // Logo
        Image.asset(
          'assets/images/vicoa-light.webp',
          width: 60.0,
          height: 60.0,
          fit: BoxFit.contain,
        ),
        SizedBox(height: 24.0),
        // Title
        Text(
          AppLocalizations.of(context).reviewDialogEnjoyingVicoa,
          style: FlutterFlowTheme.of(context).headlineMedium.override(
                font: GoogleFonts.sourceSans3(
                  fontWeight: FontWeight.w600,
                  fontStyle: FlutterFlowTheme.of(context).headlineMedium.fontStyle,
                ),
                fontSize: 28.0,
                letterSpacing: 0.0,
                fontWeight: FontWeight.w600,
                fontStyle: FlutterFlowTheme.of(context).headlineMedium.fontStyle,
              ),
        ),
        SizedBox(height: 16.0),
        // Description
        Text(
          AppLocalizations.of(context).reviewDialogEnjoyingDescription,
          textAlign: TextAlign.center,
          style: FlutterFlowTheme.of(context).bodyMedium.override(
                font: GoogleFonts.sourceSans3(
                  fontWeight: FontWeight.normal,
                  fontStyle: FlutterFlowTheme.of(context).bodyMedium.fontStyle,
                ),
                color: FlutterFlowTheme.of(context).secondaryText,
                fontSize: 17.0,
                letterSpacing: 0.0,
                fontWeight: FontWeight.normal,
                fontStyle: FlutterFlowTheme.of(context).bodyMedium.fontStyle,
              ),
        ),
        SizedBox(height: 24.0),
        // "Love it!" button
        FFButtonWidget(
          onPressed: () async {
            logFirebaseEvent('REVIEW_DIALOG_LOVE_IT_BTN_ON_TAP');
            HapticFeedback.lightImpact();
            setState(() {
              _model.currentPage = 1;
            });
          },
          text: AppLocalizations.of(context).reviewDialogLoveIt,
          options: FFButtonOptions(
            width: double.infinity,
            height: 56.0,
            padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
            iconPadding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
            color: FlutterFlowTheme.of(context).alternate,
            textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                  font: GoogleFonts.sourceSans3(
                    fontWeight: FontWeight.w600,
                    fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                  ),
                  color: FlutterFlowTheme.of(context).primaryText,
                  fontSize: 19.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w600,
                  fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                ),
            elevation: 0.0,
            borderSide: BorderSide(
              color: Colors.transparent,
              width: 0.0,
            ),
            borderRadius: BorderRadius.circular(16.0),
          ),
        ),
        SizedBox(height: 12.0),
        // "Could be better" button
        FFButtonWidget(
          onPressed: () async {
            logFirebaseEvent('REVIEW_DIALOG_NEEDS_WORK_BTN_ON_TAP');
            HapticFeedback.lightImpact();
            setState(() {
              _model.currentPage = 2;
            });
          },
          text: AppLocalizations.of(context).reviewDialogCouldBeBetter,
          options: FFButtonOptions(
            width: double.infinity,
            height: 56.0,
            padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
            iconPadding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
            color: FlutterFlowTheme.of(context).alternate,
            textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                  font: GoogleFonts.sourceSans3(
                    fontWeight: FontWeight.w600,
                    fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                  ),
                  color: FlutterFlowTheme.of(context).primaryText,
                  fontSize: 19.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w600,
                  fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                ),
            elevation: 0.0,
            borderSide: BorderSide(
              color: Colors.transparent,
              width: 0.0,
            ),
            borderRadius: BorderRadius.circular(16.0),
          ),
        ),
      ],
    );
  }

  // "Love it!" page - encourage app store review
  Widget _buildLoveItPage() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // Icon
        Text(
          '😍',
          style: TextStyle(fontSize: 60.0),
        ),
        SizedBox(height: 12.0),
        // Title
        Text(
          AppLocalizations.of(context).reviewDialogReviewVicoa,
          style: FlutterFlowTheme.of(context).headlineMedium.override(
                font: GoogleFonts.sourceSans3(
                  fontWeight: FontWeight.w600,
                  fontStyle: FlutterFlowTheme.of(context).headlineMedium.fontStyle,
                ),
                fontSize: 28.0,
                letterSpacing: 0.0,
                fontWeight: FontWeight.w600,
                fontStyle: FlutterFlowTheme.of(context).headlineMedium.fontStyle,
              ),
        ),
        SizedBox(height: 16.0),
        // Description
        Text(
          AppLocalizations.of(context).reviewDialogReviewDescription,
          textAlign: TextAlign.center,
          style: FlutterFlowTheme.of(context).bodyMedium.override(
                font: GoogleFonts.sourceSans3(
                  fontWeight: FontWeight.normal,
                  fontStyle: FlutterFlowTheme.of(context).bodyMedium.fontStyle,
                ),
                color: FlutterFlowTheme.of(context).secondaryText,
                fontSize: 17.0,
                letterSpacing: 0.0,
                fontWeight: FontWeight.normal,
                fontStyle: FlutterFlowTheme.of(context).bodyMedium.fontStyle,
              ),
        ),
        SizedBox(height: 16.0),
        // 5 Stars
        Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(
            5,
            (index) => Padding(
              padding: EdgeInsetsDirectional.fromSTEB(4.0, 0.0, 4.0, 0.0),
              child: Icon(
                Icons.star_rounded,
                color: Colors.amber,
                size: 40.0,
              ),
            ),
          ),
        ),
        SizedBox(height: 24.0),
        // "Rate on App Store" button
        FFButtonWidget(
          onPressed: () async {
            logFirebaseEvent('REVIEW_DIALOG_RATE_APP_BTN_ON_TAP');
            HapticFeedback.lightImpact();
            await actions.openStoreListing();
            Navigator.pop(context);
          },
          text: AppLocalizations.of(context).reviewDialogRateOnAppStore,
          options: FFButtonOptions(
            width: double.infinity,
            height: 56.0,
            padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
            iconPadding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
            color: FlutterFlowTheme.of(context).primary,
            textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                  font: GoogleFonts.sourceSans3(
                    fontWeight: FontWeight.w600,
                    fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                  ),
                  color: Colors.white,
                  fontSize: 18.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w600,
                  fontStyle: FlutterFlowTheme.of(context).titleSmall.fontStyle,
                ),
            elevation: 0.0,
            borderSide: BorderSide(
              color: Colors.transparent,
              width: 0.0,
            ),
            borderRadius: BorderRadius.circular(16.0),
          ),
        ),
      ],
    );
  }

  // "Needs work" page - inline feedback form posted to /support/report-issue
  Widget _buildNeedsWorkPage() {
    final hasText = _feedbackController.text.trim().isNotEmpty;
    final canSubmit = hasText && !_isSubmittingFeedback;

    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Icon
          Text(
            '🤔',
            style: TextStyle(fontSize: 60.0),
          ),
          SizedBox(height: 12.0),
          // Title
          Text(
            AppLocalizations.of(context).reviewDialogWhatCouldBeBetter,
            style: FlutterFlowTheme.of(context).headlineMedium.override(
                  font: GoogleFonts.sourceSans3(
                    fontWeight: FontWeight.w600,
                    fontStyle:
                        FlutterFlowTheme.of(context).headlineMedium.fontStyle,
                  ),
                  fontSize: 24.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w600,
                  fontStyle:
                      FlutterFlowTheme.of(context).headlineMedium.fontStyle,
                ),
          ),
          SizedBox(height: 12.0),
          // Description
          Text(
            AppLocalizations.of(context).reviewDialogNeedsWorkDescription,
            textAlign: TextAlign.center,
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  font: GoogleFonts.sourceSans3(
                    fontWeight: FontWeight.normal,
                    fontStyle:
                        FlutterFlowTheme.of(context).bodyMedium.fontStyle,
                  ),
                  color: FlutterFlowTheme.of(context).secondaryText,
                  fontSize: 17.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.normal,
                  fontStyle: FlutterFlowTheme.of(context).bodyMedium.fontStyle,
                ),
          ),
          SizedBox(height: 20.0),
          // Feedback text field
          TextFormField(
            controller: _feedbackController,
            focusNode: _feedbackFocusNode,
            autofocus: true,
            textInputAction: TextInputAction.newline,
            keyboardType: TextInputType.multiline,
            minLines: 5,
            maxLines: 6,
            maxLength: _feedbackMaxLength,
            maxLengthEnforcement: MaxLengthEnforcement.enforced,
            enabled: !_isSubmittingFeedback,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              hintText: AppLocalizations.of(context).reviewDialogIssueHint,
              hintStyle: FlutterFlowTheme.of(context).bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: FlutterFlowTheme.of(context).secondaryText,
                    fontSize: 16.0,
                    letterSpacing: 0.0,
                  ),
              enabledBorder: OutlineInputBorder(
                borderSide: BorderSide(
                  color: FlutterFlowTheme.of(context).alternate,
                  width: 1.0,
                ),
                borderRadius: BorderRadius.circular(12.0),
              ),
              focusedBorder: OutlineInputBorder(
                borderSide: BorderSide(
                  color: FlutterFlowTheme.of(context).primary,
                  width: 2.0,
                ),
                borderRadius: BorderRadius.circular(12.0),
              ),
              filled: true,
              fillColor: FlutterFlowTheme.of(context).secondaryBackground,
              contentPadding:
                  EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 16.0),
            ),
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  color: FlutterFlowTheme.of(context).themeText,
                  fontSize: 17.0,
                  letterSpacing: 0.0,
                ),
            buildCounter: (context,
                    {required currentLength, required isFocused, maxLength}) =>
                Align(
              alignment: Alignment.centerRight,
              child: Text(
                AppLocalizations.of(context)
                    .reviewDialogCharCount(currentLength, maxLength ?? 0),
                style: FlutterFlowTheme.of(context).bodySmall.override(
                      font: GoogleFonts.sourceSans3(),
                      color: FlutterFlowTheme.of(context).secondaryText,
                      fontSize: 12.0,
                      letterSpacing: 0.0,
                    ),
              ),
            ),
          ),
          SizedBox(height: 12.0),
          // Cancel + Send row
          Row(
            mainAxisSize: MainAxisSize.max,
            children: [
              Expanded(
                child: FFButtonWidget(
                  onPressed: _isSubmittingFeedback
                      ? null
                      : () {
                          HapticFeedback.lightImpact();
                          Navigator.pop(context);
                        },
                  text: AppLocalizations.of(context).commonCancel,
                  options: FFButtonOptions(
                    height: 50.0,
                    padding:
                        EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    iconPadding:
                        EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    color: FlutterFlowTheme.of(context).primaryBackground,
                    textStyle:
                        FlutterFlowTheme.of(context).titleSmall.override(
                              font: GoogleFonts.sourceSans3(
                                fontWeight: FontWeight.normal,
                                fontStyle: FlutterFlowTheme.of(context)
                                    .titleSmall
                                    .fontStyle,
                              ),
                              color:
                                  FlutterFlowTheme.of(context).secondaryText,
                              fontSize: 18.0,
                              letterSpacing: 0.0,
                              fontWeight: FontWeight.normal,
                              fontStyle: FlutterFlowTheme.of(context)
                                  .titleSmall
                                  .fontStyle,
                            ),
                    elevation: 0.0,
                    borderSide: BorderSide(
                      color: Colors.transparent,
                      width: 1.0,
                    ),
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                ),
              ),
              SizedBox(width: 12.0),
              Expanded(
                child: FFButtonWidget(
                  onPressed: canSubmit
                      ? () {
                          logFirebaseEvent(
                              'REVIEW_DIALOG_SEND_FEEDBACK_BTN_ON_TAP');
                          HapticFeedback.lightImpact();
                          _submitFeedback();
                        }
                      : null,
                  text: _isSubmittingFeedback
                      ? AppLocalizations.of(context).reviewDialogSending
                      : AppLocalizations.of(context).reviewDialogSendFeedback,
                  options: FFButtonOptions(
                    height: 50.0,
                    padding:
                        EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    iconPadding:
                        EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    color: FlutterFlowTheme.of(context).primary,
                    disabledColor: FlutterFlowTheme.of(context).alternate,
                    textStyle:
                        FlutterFlowTheme.of(context).titleSmall.override(
                              font: GoogleFonts.sourceSans3(
                                fontWeight: FontWeight.w600,
                                fontStyle: FlutterFlowTheme.of(context)
                                    .titleSmall
                                    .fontStyle,
                              ),
                              color: Colors.white,
                              fontSize: 18.0,
                              letterSpacing: 0.0,
                              fontWeight: FontWeight.w600,
                              fontStyle: FlutterFlowTheme.of(context)
                                  .titleSmall
                                  .fontStyle,
                            ),
                    elevation: 0.0,
                    borderSide: BorderSide(
                      color: Colors.transparent,
                      width: 0.0,
                    ),
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
