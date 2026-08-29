import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/l10n/app_localizations.dart';
import '/custom_code/actions/index.dart' as actions;
import '/components/connect_computer/connect_computer_widget.dart';
import '/pages/snack_bar/snack_bar_widget.dart';
import '/pages/info_dialog/info_dialog_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'start_session_model.dart';
export 'start_session_model.dart';

class StartSessionWidget extends StatefulWidget {
  const StartSessionWidget({super.key});

  static String routeName = 'StartSession';
  static String routePath = '/start-session';

  @override
  State<StartSessionWidget> createState() => _StartSessionWidgetState();
}

class _StartSessionWidgetState extends State<StartSessionWidget>
    with TickerProviderStateMixin {
  late StartSessionModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();
  int _directoriesShownCount = 5; // Track how many directories to show

  final animationsMap = <String, AnimationInfo>{};

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => StartSessionModel());
    // Register callback to rebuild widget when model state changes
    _model.onStateChanged = () {
      if (mounted) {
        setState(() {});
      }
    };
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'StartSession'});

    animationsMap.addAll({
      'textOnPageLoadAnimation': AnimationInfo(
        trigger: AnimationTrigger.onPageLoad,
        effectsBuilder: () => [
          FadeEffect(
            curve: Curves.easeInOut,
            delay: 0.0.ms,
            duration: 500.0.ms,
            begin: 0.0,
            end: 1.0,
          ),
          MoveEffect(
            curve: Curves.easeInOut,
            delay: 0.0.ms,
            duration: 500.0.ms,
            begin: Offset(-50.0, 0.0),
            end: Offset(0.0, 0.0),
          ),
        ],
      ),
      'iconButtonOnPageLoadAnimation': AnimationInfo(
        trigger: AnimationTrigger.onPageLoad,
        effectsBuilder: () => [
          FadeEffect(
            curve: Curves.easeInOut,
            delay: 0.0.ms,
            duration: 500.0.ms,
            begin: 0.0,
            end: 1.0,
          ),
          MoveEffect(
            curve: Curves.easeInOut,
            delay: 0.0.ms,
            duration: 500.0.ms,
            begin: Offset(50.0, 0.0),
            end: Offset(0.0, 0.0),
          ),
        ],
      ),
    });
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
        FocusManager.instance.primaryFocus?.unfocus();
      },
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
        body: Column(
          mainAxisSize: MainAxisSize.max,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsetsDirectional.fromSTEB(24.0, 60.0, 16.0, 16.0),
              child: Row(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    AppLocalizations.of(context).startSessionNewSession,
                    textAlign: TextAlign.center,
                    style: FlutterFlowTheme.of(context).headlineMedium.override(
                          font: GoogleFonts.sourceSans3(
                            fontWeight: FontWeight.w500,
                          ),
                          fontSize: 25.0,
                          letterSpacing: 0.0,
                          fontWeight: FontWeight.w500,
                        ),
                  ).animateOnPageLoad(animationsMap['textOnPageLoadAnimation']!),
                  FlutterFlowIconButton(
                    borderColor: FlutterFlowTheme.of(context).alternate,
                    borderRadius: 10.0,
                    borderWidth: 1.0,
                    buttonSize: 40.0,
                    icon: Icon(
                      Icons.close_rounded,
                      color: FlutterFlowTheme.of(context).secondaryText,
                      size: 20.0,
                    ),
                    onPressed: () async {
                      HapticFeedback.lightImpact();
                      context.pop();
                    },
                  ).animateOnPageLoad(animationsMap['iconButtonOnPageLoadAnimation']!),
                ],
              ),
            ),
            Expanded(
              child: _model.machines.isEmpty && !_model.isLoadingMachines
                  ? _buildEmptyState()
                  : Column(
                      children: [
                        Expanded(
                          child: _buildForm(),
                        ),
                        Container(
                          padding: EdgeInsets.fromLTRB(20.0, 12.0, 20.0, 48.0),
                          decoration: BoxDecoration(
                            color: FlutterFlowTheme.of(context).secondaryBackground,
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.05),
                                offset: Offset(0, -2),
                                blurRadius: 8.0,
                              ),
                            ],
                          ),
                          child: _buildStartButton(),
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Align(
      alignment: Alignment.topCenter,
      child: ConnectComputerWidget(
        hasSessions: false,
        docsUrl: 'https://vicoa.ai/docs/start-remote-session',
      ),
    );
  }

  Widget _buildForm() {
    return SingleChildScrollView(
      child: Padding(
        padding: EdgeInsets.fromLTRB(20.0, 8.0, 20.0, 24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Machine Selection
            Text(
              AppLocalizations.of(context).startSessionMachine,
              style: FlutterFlowTheme.of(context).labelMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    fontWeight: FontWeight.w500,
                    color: FlutterFlowTheme.of(context).secondaryText,
                  ),
            ),
            SizedBox(height: 12.0),
            _buildMachineDropdown(),
            if (_model.machines.isNotEmpty &&
                _model.machines.every((m) => !_model.isMachineOnline(m))) ...[
              SizedBox(height: 10.0),
              Row(
                children: [
                  Icon(
                    Icons.info_outline_rounded,
                    size: 14.0,
                    color: FlutterFlowTheme.of(context).secondaryText,
                  ),
                  SizedBox(width: 6.0),
                  Expanded(
                    child: RichText(
                      text: TextSpan(
                        style: FlutterFlowTheme.of(context).bodySmall.override(
                              font: GoogleFonts.sourceSans3(),
                              color: FlutterFlowTheme.of(context).secondaryText,
                              fontSize: 13.0,
                            ),
                        children: [
                          TextSpan(text: AppLocalizations.of(context).startSessionRunPrefix),
                          TextSpan(
                            text: 'vicoa',
                            style: GoogleFonts.jetBrainsMono(
                              fontWeight: FontWeight.w400,
                              fontSize: 13.0,
                              color: FlutterFlowTheme.of(context).primaryText,
                            ),
                          ),
                          TextSpan(text: AppLocalizations.of(context).startSessionOrSeparator),
                          TextSpan(
                            text: 'vicoa daemon',
                            style: GoogleFonts.jetBrainsMono(
                              fontWeight: FontWeight.w400,
                              fontSize: 13.0,
                              color: FlutterFlowTheme.of(context).primaryText,
                            ),
                          ),
                          TextSpan(text: AppLocalizations.of(context).startSessionToBringOnline),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ],
            SizedBox(height: 28.0),

            // Agent Type Selection
            Text(
              AppLocalizations.of(context).startSessionAgent,
              style: FlutterFlowTheme.of(context).labelMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    fontWeight: FontWeight.w500,
                    color: FlutterFlowTheme.of(context).secondaryText,
                  ),
            ),
            SizedBox(height: 12.0),
            _buildAgentTypeDropdown(),
            SizedBox(height: 28.0),

            // Directory Input
            Text(
              AppLocalizations.of(context).startSessionWorkingDirectory,
              style: FlutterFlowTheme.of(context).labelMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    fontWeight: FontWeight.w500,
                    color: FlutterFlowTheme.of(context).secondaryText,
                  ),
            ),
            SizedBox(height: 12.0),
            _buildDirectoryInput(),
            SizedBox(height: 12.0),
            _buildRecentDirectories(),
          ],
        ),
      ),
    );
  }

  Widget _buildMachineDropdown() {
    // Show loading state in dropdown if still loading
    if (_model.isLoadingMachines && _model.machines.isEmpty) {
      return Container(
        decoration: BoxDecoration(
          color: FlutterFlowTheme.of(context).primaryBackground,
          borderRadius: BorderRadius.circular(16.0),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 16.0),
          child: Row(
            children: [
              SizedBox(
                width: 20.0,
                height: 20.0,
                child: CircularProgressIndicator(
                  strokeWidth: 2.0,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    FlutterFlowTheme.of(context).primary,
                  ),
                ),
              ),
              SizedBox(width: 16.0),
              Text(
                AppLocalizations.of(context).startSessionLoadingMachines,
                style: FlutterFlowTheme.of(context).bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      fontSize: 16.0,
                      color: FlutterFlowTheme.of(context).secondaryText,
                    ),
              ),
            ],
          ),
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 4.0),
        child: DropdownButtonFormField<String>(
          value: _model.selectedMachineId,
          decoration: InputDecoration(
            border: InputBorder.none,
          ),
          hint: Text(
            AppLocalizations.of(context).startSessionSelectMachine,
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5),
                  fontSize: 16.0,
                ),
          ),
          isExpanded: true,
          borderRadius: BorderRadius.circular(16.0),
          dropdownColor: FlutterFlowTheme.of(context).primaryBackground,
          items: _model.machines.map<DropdownMenuItem<String>>((machine) {
            final machineId = machine['machine_id'] ?? machine['id'];
            final isOnline = _model.isMachineOnline(machine);
            final displayName = _model.getMachineDisplayName(machine);

            return DropdownMenuItem<String>(
              value: machineId,
              enabled: isOnline,
              child: Row(
                children: [
                  Container(
                    width: 8.0,
                    height: 8.0,
                    decoration: BoxDecoration(
                      color: isOnline
                          ? Colors.green
                          : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(4.0),
                    ),
                  ),
                  SizedBox(width: 12.0),
                  Expanded(
                    child: Text(
                      displayName,
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
                            font: GoogleFonts.sourceSans3(),
                            fontSize: 16.0,
                            color: isOnline
                                ? FlutterFlowTheme.of(context).primaryText
                                : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5),
                          ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (!isOnline)
                    Text(
                      AppLocalizations.of(context).startSessionOffline,
                      style: FlutterFlowTheme.of(context).bodySmall.override(
                            fontSize: 13.0,
                            color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5),
                          ),
                    ),
                ],
              ),
            );
          }).toList(),
          onChanged: (value) {
            if (value != null) {
              HapticFeedback.lightImpact();
              setState(() {
                _model.selectMachine(value);
              });
            }
          },
          style: FlutterFlowTheme.of(context).bodyMedium.override(
                font: GoogleFonts.sourceSans3(),
                fontSize: 16.0,
              ),
          icon: Icon(
            Icons.keyboard_arrow_down_rounded,
            color: FlutterFlowTheme.of(context).secondaryText,
            size: 24.0,
          ),
        ),
      ),
    );
  }

  Widget _buildAgentTypeDropdown() {
    return Container(
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 4.0),
        child: DropdownButtonFormField<String>(
          value: _model.selectedAgentType,
          decoration: InputDecoration(
            border: InputBorder.none,
          ),
          isExpanded: true,
          borderRadius: BorderRadius.circular(16.0),
          dropdownColor: FlutterFlowTheme.of(context).primaryBackground,
          items: _model.agentTypes.map<DropdownMenuItem<String>>((agentType) {
            final id = agentType['id'] as String;
            final name = agentType['name'] as String? ?? '';
            final isComingSoon = agentType['isComingSoon'] as bool? ?? false;
            final itemText = isComingSoon
                ? AppLocalizations.of(context).startSessionAgentComingSoon(name)
                : name;

            return DropdownMenuItem<String>(
              value: id,
              enabled: !isComingSoon,
              child: Text(
                itemText,
                style: FlutterFlowTheme.of(context).bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      fontSize: 16.0,
                      color: isComingSoon
                          ? FlutterFlowTheme.of(context)
                              .secondaryText
                              .withValues(alpha: 0.5)
                          : FlutterFlowTheme.of(context).primaryText,
                    ),
              ),
            );
          }).toList(),
          onChanged: (value) {
            if (value != null && _model.isAgentTypeSelectable(value)) {
              HapticFeedback.lightImpact();
              setState(() {
                _model.selectedAgentType = value;
              });
            }
          },
          style: FlutterFlowTheme.of(context).bodyMedium.override(
                font: GoogleFonts.sourceSans3(),
                fontSize: 16.0,
              ),
          icon: Icon(
            Icons.keyboard_arrow_down_rounded,
            color: FlutterFlowTheme.of(context).secondaryText,
            size: 24.0,
          ),
        ),
      ),
    );
  }

  Widget _buildDirectoryInput() {
    return Container(
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 4.0),
        child: TextFormField(
          controller: _model.directoryController,
          focusNode: _model.directoryFocusNode,
          decoration: InputDecoration(
            hintText: '~/projects/my-app',
            hintStyle: FlutterFlowTheme.of(context).bodyMedium.override(
                  color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5),
                  fontSize: 15.0,
                ),
            border: InputBorder.none,
          ),
          style: FlutterFlowTheme.of(context).bodyMedium.override(
                font: GoogleFonts.firaCode(),
                fontSize: 15.0,
              ),
        ),
      ),
    );
  }

  Widget _buildRecentDirectories() {
    final recentDirs = _model.getRecentDirectories();
    if (recentDirs.isEmpty) {
      return SizedBox.shrink();
    }

    final directories = recentDirs.take(_directoriesShownCount).toList();
    final hasMore = recentDirs.length > _directoriesShownCount;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          AppLocalizations.of(context).startSessionRecent,
          style: FlutterFlowTheme.of(context).bodySmall.override(
                color: FlutterFlowTheme.of(context).secondaryText,
                fontSize: 13.0,
                fontWeight: FontWeight.w500,
              ),
        ),
        SizedBox(height: 12.0),
        ListView.separated(
          padding: EdgeInsets.zero,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: directories.length,
          separatorBuilder: (_, __) => SizedBox(height: 8.0),
          itemBuilder: (context, index) {
            final dir = directories[index];
            return InkWell(
              onTap: () {
                HapticFeedback.lightImpact();
                setState(() {
                  _model.directoryController.value = TextEditingValue(
                    text: dir,
                    selection: TextSelection.collapsed(offset: dir.length),
                  );
                });
                FocusScope.of(context).requestFocus(_model.directoryFocusNode);
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (!mounted) {
                    return;
                  }
                  _model.directoryController.selection = TextSelection.collapsed(
                    offset: _model.directoryController.text.length,
                  );
                });
              },
              borderRadius: BorderRadius.circular(8.0),
              child: Container(
                width: double.infinity,
                padding: EdgeInsets.symmetric(horizontal: 12.0, vertical: 10.0),
                decoration: BoxDecoration(
                  color: FlutterFlowTheme.of(context).primaryBackground,
                  borderRadius: BorderRadius.circular(8.0),
                ),
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    const iconWidth = 14.0;
                    const spacing = 8.0;
                    final textStyle = FlutterFlowTheme.of(context).bodySmall.override(
                          font: GoogleFonts.firaCode(),
                          fontSize: 12.0,
                          color: FlutterFlowTheme.of(context).secondaryText,
                        );
                    final rawMaxTextWidth = constraints.maxWidth - iconWidth - spacing;
                    final maxTextWidth = rawMaxTextWidth > 0 ? rawMaxTextWidth : 0.0;
                    final truncatedDir = _shrinkFromFront(
                      dir,
                      maxTextWidth,
                      textStyle,
                      context,
                    );

                    return Row(
                      mainAxisSize: MainAxisSize.max,
                      children: [
                        Icon(
                          Icons.folder_open_outlined,
                          color: FlutterFlowTheme.of(context).secondaryText,
                          size: iconWidth,
                        ),
                        SizedBox(width: spacing),
                        Expanded(
                          child: Text(
                            truncatedDir,
                            style: textStyle,
                          ),
                        ),
                      ],
                    );
                  },
                ),
              ),
            );
          },
        ),
        if (hasMore) ...[
          // SizedBox(height: 6.0),
          InkWell(
            onTap: () {
              HapticFeedback.lightImpact();
              setState(() {
                _directoriesShownCount += 5;
              });
            },
            borderRadius: BorderRadius.circular(8.0),
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.symmetric(vertical: 10.0),
              child: Center(
                child: Text(
                  AppLocalizations.of(context).startSessionShowMore,
                  style: FlutterFlowTheme.of(context).bodySmall.override(
                        color: FlutterFlowTheme.of(context).secondaryText,
                        fontSize: 13.0,
                        fontWeight: FontWeight.w500,
                      ),
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildStartButton() {
    final hasRequiredInputs = _model.selectedMachineId != null &&
        _model.directoryController.text.trim().isNotEmpty &&
        _model.selectedAgentType != null &&
        _model.isAgentTypeSelectable(_model.selectedAgentType);

    return FFButtonWidget(
        showLoadingIndicator: true,
        onPressed: hasRequiredInputs
            ? () async {
              if (_model.isSubmitting) {
                return;
              }
              HapticFeedback.mediumImpact();
              logFirebaseEvent('START_SESSION_PAGE_START_SESSION_BTN_TAP');

              final result = await _model.startSession();

              if (!mounted) return;

              if (result['success'] == true) {
                final agentInstanceId =
                    result['agentInstanceId']?.toString();

                if (agentInstanceId == null || agentInstanceId.isEmpty) {
                  await showModalBottomSheet(
                    isScrollControlled: true,
                    backgroundColor: Colors.transparent,
                    enableDrag: false,
                    context: context,
                    builder: (context) {
                      return SnackBarWidget(
                        content: AppLocalizations.of(context).startSessionStartedNoStatus,
                      );
                    },
                  );
                  return;
                }

                // Wait for the daemon-spawned agent to self-register. WS first
                // (the user-scoped socket pushes instance-created via the
                // dispatcher, which fetches the joined row before emitting).
                //
                // The REST polling block below is the ONLY per-flow polling
                // we allow — it covers the mobile lifecycle edge where the
                // app was paused while the broadcast fired (WS missed it, no
                // replay on resume). Do NOT copy this pattern to other RPC
                // waits; the correct fix is to unify catch-up rows with the
                // live dispatch path so reconnect catch-up resolves the WS
                // wait automatically. This block goes when that lands.
                Map<String, dynamic>? instanceData =
                    await actions.VicoaWsClient.instance.waitForEntity(
                  'agent_instances',
                  agentInstanceId,
                  timeout: const Duration(seconds: 4),
                );
                if (instanceData == null) {
                  for (var i = 0; i < 6; i++) {
                    try {
                      final fetched =
                          await actions.apiGetInstanceById(agentInstanceId);
                      if (fetched is Map && fetched['id'] != null) {
                        instanceData = Map<String, dynamic>.from(fetched);
                        break;
                      }
                    } catch (_) {
                      // Not registered yet — keep polling.
                    }
                    await Future.delayed(const Duration(seconds: 2));
                  }
                }

                if (!mounted) return;

                // Pop StartSession and return to Home, which navigates to
                // AgentChat. Hand off the id even if the row has not surfaced
                // yet — the chat page picks it up over the WebSocket.
                context.pop({
                  'status': 'success',
                  'instanceId': agentInstanceId,
                  if (instanceData != null) 'instanceData': instanceData,
                });
              } else {
                await _showUnableToStartSessionDialog(
                  result['error']?.toString(),
                );
              }
              }
            : null,
        text: AppLocalizations.of(context).startSessionStartSession,
        options: FFButtonOptions(
          width: double.infinity,
          height: 54.0,
          padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
          color: Colors.transparent,
          textStyle: FlutterFlowTheme.of(context).titleMedium.override(
                color: hasRequiredInputs
                    ? FlutterFlowTheme.of(context).primaryText
                    : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                fontSize: 18.0,
                fontWeight: FontWeight.w600,
              ),
          elevation: 0.0,
          borderSide: BorderSide(
            color: hasRequiredInputs
                ? FlutterFlowTheme.of(context).primaryText
                : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
            width: 1.0,
          ),
          borderRadius: BorderRadius.circular(24.0),
      ),
    );
  }

  Future<void> _showUnableToStartSessionDialog(String? errorMessage) async {
    if (!mounted) return;
    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return InfoDialogWidget(
          title: AppLocalizations.of(context).startSessionUnableToStart,
          content: _buildUnableToStartSessionMessage(errorMessage),
        );
      },
    );
  }

  String _buildUnableToStartSessionMessage(String? errorMessage) {
    final trimmedError = errorMessage?.trim();
    if (trimmedError != null && trimmedError.isNotEmpty) {
      return trimmedError;
    }
    return AppLocalizations.of(context).startSessionUnableToStartBody;
  }

  String _shrinkFromFront(
    String text,
    double maxWidth,
    TextStyle style,
    BuildContext context,
  ) {
    if (text.isEmpty) {
      return text;
    }

    final width = _measureTextWidth(text, style, context);
    if (maxWidth <= 0.0) {
      return '...';
    }

    if (width <= maxWidth) {
      return text;
    }

    final ellipsis = '...';
    for (var i = 1; i < text.length; i++) {
      final candidate = '$ellipsis${text.substring(i)}';
      if (_measureTextWidth(candidate, style, context) <= maxWidth) {
        return candidate;
      }
    }

    return ellipsis + text.substring(text.length - 1);
  }

  double _measureTextWidth(
    String text,
    TextStyle style,
    BuildContext context,
  ) {
    final textPainter = TextPainter(
      text: TextSpan(text: text, style: style),
      maxLines: 1,
      textDirection: Directionality.of(context),
    )..layout(minWidth: 0, maxWidth: double.infinity);

    return textPainter.width;
  }
}
