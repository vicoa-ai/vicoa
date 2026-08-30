import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'app_language_model.dart';
export 'app_language_model.dart';

class AppLanguageWidget extends StatefulWidget {
  const AppLanguageWidget({super.key});

  static String routeName = 'AppLanguage';
  static String routePath = '/appLanguage';

  @override
  State<AppLanguageWidget> createState() => _AppLanguageWidgetState();
}

class _AppLanguageWidgetState extends State<AppLanguageWidget> {
  late AppLanguageModel _model;

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => AppLanguageModel());
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();
    final l10n = AppLocalizations.of(context);
    final selectedPref = FFAppState().appLanguage;
    final options = <({String pref, String label})>[
      (pref: 'system', label: l10n.languageAutomatic),
      (pref: 'en', label: l10n.languageEnglish),
      (pref: 'zh', label: l10n.languageChinese),
    ];

    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
        FocusManager.instance.primaryFocus?.unfocus();
      },
      child: Scaffold(
        backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
        appBar: AppBar(
          backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
          automaticallyImplyLeading: false,
          leading: Align(
            alignment: const AlignmentDirectional(1.0, 0.0),
            child: FlutterFlowIconButton(
              borderColor: Colors.transparent,
              borderRadius: 10.0,
              borderWidth: 1.0,
              buttonSize: 40.0,
              fillColor: FlutterFlowTheme.of(context).primaryBackground,
              icon: Icon(
                Icons.chevron_left_rounded,
                color: FlutterFlowTheme.of(context).secondaryText,
                size: 24.0,
              ),
              onPressed: () async {
                HapticFeedback.lightImpact();
                context.safePop();
              },
            ),
          ),
          title: Text(
            l10n.appLanguageTitle,
            style: FlutterFlowTheme.of(context).titleLarge.override(
                  font: GoogleFonts.sourceSans3(
                    fontWeight:
                        FlutterFlowTheme.of(context).titleLarge.fontWeight,
                    fontStyle:
                        FlutterFlowTheme.of(context).titleLarge.fontStyle,
                  ),
                  letterSpacing: 0.0,
                  fontWeight:
                      FlutterFlowTheme.of(context).titleLarge.fontWeight,
                  fontStyle: FlutterFlowTheme.of(context).titleLarge.fontStyle,
                ),
          ),
          centerTitle: true,
          elevation: 0.0,
        ),
        body: SafeArea(
          top: true,
          bottom: false,
          child: ListView.separated(
            padding:
                const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 24.0),
            itemCount: options.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8.0),
            itemBuilder: (context, index) {
              final option = options[index];
              final isSelected = option.pref == selectedPref;
              return Material(
                color: FlutterFlowTheme.of(context).primaryBackground,
                borderRadius: BorderRadius.circular(14.0),
                child: InkWell(
                  borderRadius: BorderRadius.circular(14.0),
                  onTap: () async {
                    HapticFeedback.selectionClick();
                    setLanguageSetting(context, option.pref);
                    context.safePop();
                  },
                  child: Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(
                        16.0, 15.0, 16.0, 15.0),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            option.label,
                            style: FlutterFlowTheme.of(context)
                                .displaySmall
                                .override(
                                  font: GoogleFonts.sourceSans3(
                                    fontWeight: FontWeight.normal,
                                    fontStyle: FlutterFlowTheme.of(context)
                                        .displaySmall
                                        .fontStyle,
                                  ),
                                  fontSize: 16.0,
                                  letterSpacing: 0.0,
                                  fontWeight: FontWeight.normal,
                                ),
                          ),
                        ),
                        if (isSelected)
                          Icon(
                            Icons.check_rounded,
                            color: FlutterFlowTheme.of(context).primary,
                            size: 22.0,
                          ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
