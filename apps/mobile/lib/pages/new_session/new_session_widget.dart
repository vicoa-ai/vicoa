import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/rpc_error_messages.dart';
import '/backend/posthog/posthog_analytics.dart';
import '/custom_code/widgets/file_mention_suggestions.dart';
import '/pages/agent_chat/components/slash_commands.dart';
import '/pages/agent_chat/components/add_to_chat_actions.dart';
import '/pages/agent_chat/components/pending_attachment.dart';
import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/components/connect_computer/connect_computer_widget.dart';
import '/backend/agent_catalog.dart';
import '/pages/new_session/components/agent_config_sheet.dart';
import '/pages/new_session/components/directory_picker_sheet.dart';
import '/pages/new_session/components/worktree_picker_sheet.dart';
import '/custom_code/utils/worktree_selection.dart';
import '/pages/snack_bar/snack_bar_widget.dart';
import '/pages/info_dialog/info_dialog_widget.dart';
import '/pages/agent_chat/components/voice_dictation_bar.dart';
import '/pages/agent_chat/components/voice_dictation_button.dart';
import 'package:app_settings/app_settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'dart:async';
import 'new_session_model.dart';
export 'new_session_model.dart';

class NewSessionWidget extends StatefulWidget {
  const NewSessionWidget(
      {super.key, this.taskId, this.initialPrompt, this.subtaskIds});

  /// When launched from a task, the spawned session is linked back to this task
  /// (its `task_id` is set) and the task is advanced to in_progress on success.
  final String? taskId;

  /// Optional text (composed from the task) used to seed the first prompt.
  final String? initialPrompt;

  /// Backlog/todo sub-tasks bundled into this session — advanced to in_progress
  /// on success alongside the parent task.
  final List<String>? subtaskIds;

  static String routeName = 'NewSession';
  static String routePath = '/new-session';

  @override
  State<NewSessionWidget> createState() => _NewSessionWidgetState();
}

class _NewSessionWidgetState extends State<NewSessionWidget>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  late NewSessionModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();
  bool _isProcessing = false;

  final animationsMap = <String, AnimationInfo>{};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _model = createModel(context, () => NewSessionModel());
    _model.onStateChanged = () {
      if (mounted) setState(() {});
    };
    _model.restoreDraftPrompt();
    // Seeding from a task overrides any saved draft — the user chose to start
    // this specific task.
    if (widget.initialPrompt != null &&
        widget.initialPrompt!.trim().isNotEmpty) {
      _model.promptController.text = widget.initialPrompt!;
    }

    animationsMap.addAll({
      'textOnPageLoadAnimation': AnimationInfo(
        trigger: AnimationTrigger.onPageLoad,
        effectsBuilder: () => [
          FadeEffect(curve: Curves.easeInOut, delay: 0.0.ms, duration: 500.0.ms, begin: 0.0, end: 1.0),
          MoveEffect(curve: Curves.easeInOut, delay: 0.0.ms, duration: 500.0.ms, begin: Offset(-50.0, 0.0), end: Offset(0.0, 0.0)),
        ],
      ),
      'iconButtonOnPageLoadAnimation': AnimationInfo(
        trigger: AnimationTrigger.onPageLoad,
        effectsBuilder: () => [
          FadeEffect(curve: Curves.easeInOut, delay: 0.0.ms, duration: 500.0.ms, begin: 0.0, end: 1.0),
          MoveEffect(curve: Curves.easeInOut, delay: 0.0.ms, duration: 500.0.ms, begin: Offset(50.0, 0.0), end: Offset(0.0, 0.0)),
        ],
      ),
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _model.saveDraftPrompt();
    _model.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _model.refreshSpeechAvailability();
    } else if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _model.saveDraftPrompt();
    }
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
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsetsDirectional.fromSTEB(24.0, 60.0, 16.0, 16.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    AppLocalizations.of(context).newSessionNewSession,
                    style: FlutterFlowTheme.of(context).headlineMedium.override(
                          font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500),
                          fontSize: 25.0,
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
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      context.pop();
                    },
                  ).animateOnPageLoad(animationsMap['iconButtonOnPageLoadAnimation']!),
                ],
              ),
            ),
            Expanded(
              child: _model.machines.isEmpty && !_model.isLoadingMachines
                  ? Align(
                      alignment: Alignment.topCenter,
                      child: ConnectComputerWidget(
                        hasSessions: false,
                        docsUrl: 'https://vicoa.ai/docs/start-remote-session',
                      ),
                    )
                  : Column(
                      children: [
                        Expanded(child: _buildForm()),
                        _buildPromptInput(),
                      ],
                    ),
            ),
          ],
        ),
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
            _sectionLabel(AppLocalizations.of(context).newSessionMachine),
            SizedBox(height: 12.0),
            _buildMachineDropdown(),
            if (_model.machines.isNotEmpty &&
                _model.machines.every((m) => !_model.isMachineOnline(m))) ...[
              SizedBox(height: 10.0),
              _buildOfflineHint(),
            ],
            SizedBox(height: 28.0),
            _sectionLabel(AppLocalizations.of(context).newSessionWorkingDirectory),
            SizedBox(height: 12.0),
            _buildDirectoryCard(),
            SizedBox(height: 28.0),
            _sectionLabel(AppLocalizations.of(context).newSessionAgent),
            SizedBox(height: 12.0),
            _buildAgentCard(),
            // Worktree — its own section after Agent, shown only when the
            // selected machine's daemon advertises worktree support (old
            // daemons would silently ignore the param) AND the directory isn't
            // known to be a plain, non-git folder.
            if (_model.selectedMachineSupportsWorktree && _model.directoryIsGitRepo != false) ...[
              SizedBox(height: 28.0),
              _sectionLabel(AppLocalizations.of(context).newSessionWorktree),
              SizedBox(height: 12.0),
              _buildWorktreeCard(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _sectionLabel(String label) {
    return Text(
      label,
      style: FlutterFlowTheme.of(context).labelMedium.override(
            font: GoogleFonts.sourceSans3(),
            fontSize: 15.0,
            fontWeight: FontWeight.w500,
            color: FlutterFlowTheme.of(context).secondaryText,
          ),
    );
  }

  Widget _buildOfflineHint() {
    return Row(
      children: [
        Icon(Icons.info_outline_rounded, size: 14.0, color: FlutterFlowTheme.of(context).secondaryText),
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
                TextSpan(text: AppLocalizations.of(context).newSessionRunPrefix),
                TextSpan(
                  text: 'vicoa daemon',
                  style: GoogleFonts.jetBrainsMono(fontSize: 12.0, color: FlutterFlowTheme.of(context).primaryText),
                ),
                TextSpan(text: AppLocalizations.of(context).newSessionToBringOnline),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMachineDropdown() {
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
                width: 20.0, height: 20.0,
                child: CircularProgressIndicator(
                  strokeWidth: 2.0,
                  valueColor: AlwaysStoppedAnimation<Color>(FlutterFlowTheme.of(context).primary),
                ),
              ),
              SizedBox(width: 16.0),
              Text(AppLocalizations.of(context).newSessionLoadingMachines, style: FlutterFlowTheme.of(context).bodyMedium.override(
                    font: GoogleFonts.sourceSans3(), fontSize: 16.0, color: FlutterFlowTheme.of(context).secondaryText)),
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
          decoration: InputDecoration(border: InputBorder.none),
          hint: Text(AppLocalizations.of(context).newSessionSelectMachine, style: FlutterFlowTheme.of(context).bodyMedium.override(
                color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5), fontSize: 16.0)),
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
                    width: 8.0, height: 8.0,
                    decoration: BoxDecoration(
                      color: isOnline ? Colors.green : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(4.0),
                    ),
                  ),
                  SizedBox(width: 12.0),
                  Expanded(
                    child: Text(displayName, style: FlutterFlowTheme.of(context).bodyMedium.override(
                          font: GoogleFonts.sourceSans3(), fontSize: 16.0,
                          color: isOnline ? FlutterFlowTheme.of(context).primaryText : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5)),
                      overflow: TextOverflow.ellipsis),
                  ),
                  if (!isOnline)
                    Text(AppLocalizations.of(context).newSessionOffline, style: FlutterFlowTheme.of(context).bodySmall.override(
                          fontSize: 13.0, color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5))),
                ],
              ),
            );
          }).toList(),
          onChanged: (value) {
            if (value != null) {
              HapticFeedback.lightImpact();
              setState(() { _model.selectMachine(value); });
            }
          },
          style: FlutterFlowTheme.of(context).bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 16.0),
          icon: Icon(Icons.keyboard_arrow_down_rounded, color: FlutterFlowTheme.of(context).secondaryText, size: 24.0),
        ),
      ),
    );
  }

  /// Click-target card mirroring the Machine card style. Tapping opens the
  /// directory picker bottom sheet, which owns the input + recent list.
  Widget _buildDirectoryCard() {
    final theme = FlutterFlowTheme.of(context);
    final value = _model.directoryController.text.trim();
    final hasValue = value.isNotEmpty;
    return Container(
      decoration: BoxDecoration(color: theme.primaryBackground, borderRadius: BorderRadius.circular(16.0)),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          onTap: _openDirectoryPicker,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 16.0),
            child: Row(children: [
              Expanded(
                child: Text(
                  hasValue ? value : '~/projects/my-app',
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.firaCode(),
                    fontSize: 15.0,
                    color: hasValue ? theme.primaryText : theme.secondaryText.withValues(alpha: 0.5),
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8.0),
              Icon(Icons.unfold_more_rounded, color: theme.secondaryText, size: 20.0),
            ]),
          ),
        ),
      ),
    );
  }

  Future<void> _openDirectoryPicker() async {
    HapticFeedback.lightImpact();
    FocusScope.of(context).unfocus();
    final picked = await showDirectoryPickerSheet(
      context: context,
      initial: _model.directoryController.text,
      recentDirectories: _model.getRecentDirectories(),
    );
    if (!mounted || picked == null) return;
    _model.directoryController.value = TextEditingValue(
      text: picked, selection: TextSelection.collapsed(offset: picked.length));
    _model.onDirectoryChanged();
    setState(() {});
  }

  /// Worktree selection card. Shows the current choice — `Current branch`,
  /// `New worktree`, or the chosen branch name — and opens the picker sheet.
  Widget _buildWorktreeCard() {
    final theme = FlutterFlowTheme.of(context);
    final (label, mono) = switch (_model.worktreeMode) {
      WorktreeMode.none => (AppLocalizations.of(context).newSessionCurrentBranch, false),
      WorktreeMode.newWorktree => (AppLocalizations.of(context).newSessionNewWorktree, false),
      WorktreeMode.existing => (
          // Prefer the actual branch name; fall back to the worktree's folder
          // name only for a detached worktree (empty branch).
          (_model.selectedWorktreeBranch?.isNotEmpty ?? false)
              ? _model.selectedWorktreeBranch!
              : _worktreeBranchLabel(context, _model.selectedWorktreePath),
          true,
        ),
    };
    return Container(
      decoration: BoxDecoration(color: theme.primaryBackground, borderRadius: BorderRadius.circular(16.0)),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          onTap: _openWorktreePicker,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 16.0),
            child: Row(children: [
              FaIcon(FontAwesomeIcons.codeBranch, color: theme.secondaryText, size: 16.0),
              const SizedBox(width: 12.0),
              Expanded(
                child: Text(
                  label,
                  style: theme.bodyMedium.override(
                    font: mono ? GoogleFonts.firaCode() : GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    color: theme.primaryText,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8.0),
              Icon(Icons.unfold_more_rounded, color: theme.secondaryText, size: 20.0),
            ]),
          ),
        ),
      ),
    );
  }

  /// The trailing path segment (the branch/worktree name) for a worktree path.
  String _worktreeBranchLabel(BuildContext context, String? path) {
    final fallback = AppLocalizations.of(context).newSessionWorktree;
    if (path == null || path.isEmpty) return fallback;
    final parts = path.split('/')..removeWhere((p) => p.isEmpty);
    return parts.isEmpty ? fallback : parts.last;
  }

  Future<void> _openWorktreePicker() async {
    HapticFeedback.lightImpact();
    FocusScope.of(context).unfocus();
    final machineId = _model.selectedMachineId;
    final cwd = _model.directoryController.text.trim();
    if (machineId == null || cwd.isEmpty) return;
    final pick = await showWorktreePickerSheet(
      context: context,
      machineId: machineId,
      cwd: cwd,
      currentMode: _model.worktreeMode,
      currentPath: _model.selectedWorktreePath,
    );
    if (!mounted || pick == null) return;
    setState(() {
      _model.worktreeMode = pick.mode;
      _model.selectedWorktreePath = pick.path;
      _model.selectedWorktreeBranch = pick.branch;
    });
    _model.persistWorktreeSelection();
  }

  /// Agent card showing a two-row dot-separated summary of the session
  /// config (row 1: agent + model; row 2: permission + effort). Tap opens
  /// the agent-config bottom sheet.
  Widget _buildAgentCard() {
    final theme = FlutterFlowTheme.of(context);
    final config = _model.sessionConfig;
    final catalog = _model.pickerCatalog;
    final agentName = config?.agent ?? _model.selectedAgentType ?? 'claude';
    final rows = (catalog != null && config != null) ? sessionConfigSummaryRows(catalog, config) : <List<String>>[[_model.sessionConfigSummaryText]];

    return Container(
      decoration: BoxDecoration(color: theme.primaryBackground, borderRadius: BorderRadius.circular(16.0)),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          onTap: _openAgentConfigSheet,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 14.0),
            child: Row(children: [
              AgentTypeIconWidget(agentTypeName: agentName, size: 20.0),
              const SizedBox(width: 12.0),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                  for (var i = 0; i < rows.length; i++) ...[
                    if (i > 0) const SizedBox(height: 4.0),
                    Text(
                      rows[i].join(' · '),
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        fontSize: i == 0 ? 16.0 : 13.0,
                        color: i == 0 ? theme.primaryText : theme.secondaryText,
                        fontWeight: i == 0 ? FontWeight.w500 : FontWeight.w400,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ]),
              ),
              const SizedBox(width: 8.0),
              Icon(Icons.unfold_more_rounded, color: theme.secondaryText, size: 20.0),
            ]),
          ),
        ),
      ),
    );
  }

  Future<void> _openAgentConfigSheet() async {
    HapticFeedback.lightImpact();
    FocusScope.of(context).unfocus();
    final catalog = _model.pickerCatalog;
    if (catalog == null) return;
    final initial = _model.sessionConfig ?? SessionConfig.defaultsFor(catalog, _model.selectedAgentType ?? 'claude');
    final result = await showAgentConfigSheet(
      context: context,
      catalog: catalog,
      initial: initial,
      availableAgents: _model.selectedMachineAvailableAgents,
    );
    if (!mounted || result == null) return;
    setState(() => _model.setSessionConfig(result));
  }

  Widget _buildPromptInput() {
    final canSubmit = _model.canSubmit;
    final theme = FlutterFlowTheme.of(context);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SlashCommandSuggestions(
          visible: _model.showSlashCommandSuggestions,
          commands: _model.filteredSlashCommands,
          onCommandSelected: (command) async {
            HapticFeedback.lightImpact();
            _model.insertSlashCommand(command.command, insertText: command.insert);
            setState(() {});
          },
        ),
        FileMentionSuggestions(
          mixin: _model,
          margin: const EdgeInsets.fromLTRB(16.0, 0.0, 16.0, 8.0),
          onFileSelected: (_) => setState(() {}),
        ),
        _model.isVoiceDictationVisible
            ? VoiceDictationBar(
                state: _model.voiceDictationUiState!,
                elapsed: _model.voiceElapsedDuration,
                recorderController: _model.voiceRecorderController,
                confirmEnabled: _model.canConfirmVoiceInput,
                onCancel: () async {
                  HapticFeedback.lightImpact();
                  await _model.stopDictation(cancel: true);
                },
                onConfirm: () async {
                  HapticFeedback.mediumImpact();
                  await _model.stopDictation(commitToInput: true);
                  if (!_model.isVoiceDictationVisible &&
                      _model.speechErrorMessage?.isNotEmpty == true &&
                      mounted) {
                    await _showVoiceError(_model.speechErrorMessage!, _model.shouldOpenSpeechSettings);
                  }
                },
              )
            : Container(
      margin: EdgeInsets.fromLTRB(16.0, 0.0, 16.0, 40.0),
      padding: EdgeInsetsDirectional.fromSTEB(10.0, 8.0, 10.0, 12.0),
      decoration: BoxDecoration(
        color: theme.secondaryText.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(24.0),
        border: Border.all(
          color: theme.secondaryText.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_model.pendingAttachments.isNotEmpty) ...[
            PendingAttachmentStrip(
              attachments: _model.pendingAttachments,
              onRemove: _model.removePendingAttachment,
            ),
            const SizedBox(height: 6.0),
          ],
          // Text input
          Container(
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(20.0)),
            child: TextField(
              controller: _model.promptController,
              focusNode: _model.promptFocusNode,
              minLines: 1,
              maxLines: 7,
              keyboardType: TextInputType.multiline,
              textCapitalization: TextCapitalization.sentences,
              textInputAction: TextInputAction.newline,
              onChanged: (text) {
                _model.filterSlashCommands(text);
                _model.filterFileMentions(text);
                setState(() {});
              },
              decoration: InputDecoration(
                hintText: AppLocalizations.of(context).chatInputPlaceholder,
                hintStyle: theme.bodyMedium.override(
                  color: theme.secondaryText,
                  fontSize: 17.0,
                ),
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                contentPadding: EdgeInsetsDirectional.all(8.0),
              ),
              style: theme.bodyMedium.override(fontSize: 17.0),
            ),
          ),
          SizedBox(height: 4.0),
          // Bottom row: add-to-chat (+) on the left, voice + send on the
          // right (agent picker moved up to its own card).
          Row(
            children: [
              _buildAddToChatButton(),
              Spacer(),
              VoiceDictationButton(
                isSpeechInitializing: _model.isSpeechInitializing,
                shouldOpenSpeechSettings: _model.shouldOpenSpeechSettings,
                onPressed: () async {
                  HapticFeedback.lightImpact();
                  FocusScope.of(context).unfocus();
                  await _model.startDictation();
                  if (!_model.isVoiceDictationVisible &&
                      _model.speechErrorMessage?.isNotEmpty == true &&
                      mounted) {
                    await _showVoiceError(_model.speechErrorMessage!,
                        _model.shouldOpenSpeechSettings);
                  }
                },
              ),
              SizedBox(width: 12.0),
              Container(
                width: 40.0,
                height: 40.0,
                decoration: BoxDecoration(
                  color: theme.secondaryText.withValues(alpha: 0.05),
                  borderRadius: BorderRadius.circular(20.0),
                ),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(20.0),
                    onTap: canSubmit && !_isProcessing
                        ? () {
                            HapticFeedback.mediumImpact();
                            _submit();
                          }
                        : null,
                    child: Container(
                      width: 40.0,
                      height: 40.0,
                      decoration: BoxDecoration(borderRadius: BorderRadius.circular(20.0)),
                      child: _isProcessing
                          ? Center(
                              child: SizedBox(
                                width: 20.0,
                                height: 20.0,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2.0,
                                  valueColor: AlwaysStoppedAnimation<Color>(theme.secondaryText),
                                ),
                              ),
                            )
                          : Icon(
                              Icons.arrow_upward_rounded,
                              color: theme.primaryText,
                              size: 22.0,
                            ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    ),
      ],
    );
  }

  /// "+" button mirroring the chat input's Add-to-chat affordance: opens the
  /// bottom sheet whose options insert "@" / "/" into the prompt box so the
  /// file-mention / slash-command panels surface (same flow as typing them).
  Widget _buildAddToChatButton() {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(20.0),
        onTap: () {
          HapticFeedback.lightImpact();
          FocusManager.instance.primaryFocus?.unfocus();
          // Claude / OpenCode surface both skills and commands via the same
          // slash trigger; Codex (and ACP agents) only have commands. Mirror
          // the chat input's substring-based agent resolution.
          final agentId = (_model.selectedAgentType ?? '').toLowerCase();
          final hasSkills =
              agentId.contains('claude') || agentId.contains('opencode');
          showAddToChatMenu(
            context: context,
            controller: _model.promptController,
            focusNode: _model.promptFocusNode,
            fileMention: _model,
            slashCommand: _model,
            hasSkills: hasSkills,
            onPhotoLibrary: () => _model.pickImageFromLibrary(),
            onTakePhoto: () => _model.takePhotoAndAttach(),
            onChooseFiles: () => _model.pickFilesAndAttach(),
          );
        },
        child: Tooltip(
          message: AppLocalizations.of(context).newSessionAddToChat,
          child: Container(
            width: 40.0,
            height: 40.0,
            alignment: Alignment.center,
            child: Icon(
              Icons.add_rounded,
              color: theme.secondaryText,
              size: 22.0,
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    setState(() => _isProcessing = true);
    // Capture before startSession()/clearDraftPrompt() touches the controller —
    // tells the chat whether to show its animated "first message loading" state.
    final hasInitialPrompt = _model.promptController.text.trim().isNotEmpty;
    // Attachments can't ride the spawn command (they upload against an instance
    // that doesn't exist yet), so when present we spawn idle and send the prompt
    // together with the files as the first message once the instance registers.
    final hasAttachments = _model.pendingAttachments.isNotEmpty;
    final promptText = _model.promptController.text.trim();
    try {
      final result =
          await _model.startSession(includePromptInSpawn: !hasAttachments);
      if (!mounted) return;

      if (result['success'] != true) {
        final code = result['errorCode']?.toString();
        // Resolve the friendly copy while context is fresh, before the async
        // posthog call — otherwise it reads context across an await gap.
        final friendly = friendlyRpcErrorMessage(context, code);
        // A connectivity failure is ground truth the machine's link is down —
        // grey it in the picker so the user stops retrying against it.
        if (rpcCodeMeansOffline(code) && _model.selectedMachineId != null) {
          _model.markMachineRpcOffline(_model.selectedMachineId!);
        }
        await posthogCapture('session_create_failed', properties: {
          'agent_type': _model.selectedAgentType ?? 'claude',
          'reason': 'spawn_error',
          'error': result['error']?.toString() ?? 'unknown',
          if (code != null) 'error_code': code,
        });
        await _showErrorDialog(friendly ?? result['error']?.toString());
        return;
      }

      final agentInstanceId = result['agentInstanceId']?.toString();

      if (agentInstanceId == null || agentInstanceId.isEmpty) {
        await posthogCapture('session_create_failed', properties: {
          'agent_type': _model.selectedAgentType ?? 'claude',
          'reason': 'missing_ids',
        });
        await _showErrorDialog(
            AppLocalizations.of(context).newSessionStartedNoStatus);
        return;
      }

      // Wait for the daemon-spawned agent to self-register. WS first (the
      // user-scoped socket pushes instance-created via the dispatcher, which
      // fetches the joined row before emitting).
      //
      // The REST polling block below is the ONLY per-flow polling we allow —
      // it covers the mobile lifecycle edge where the app was paused while
      // the broadcast fired (WS missed it, no replay on resume). Do NOT copy
      // this pattern to other RPC waits; the correct fix is to unify
      // catch-up rows with the live dispatch path so reconnect catch-up
      // resolves the WS wait automatically. This block goes when that lands.
      Map<String, dynamic>? instanceData =
          await actions.VicoaWsClient.instance.waitForEntity(
        'agent_instances',
        agentInstanceId,
        timeout: const Duration(seconds: 4),
      );
      if (instanceData == null) {
        for (var i = 0; i < 6; i++) {
          try {
            final fetched = await actions.apiGetInstanceById(agentInstanceId);
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

      // The daemon never registered the instance within the wait window — the
      // session didn't actually start on the machine (the agent isn't
      // installed there, the daemon is out of date, or the headless runner
      // crashed before registering). Surface the failure and stay here instead
      // of navigating to a blank session page that then 404s on fetch
      // (the registration happens up front in the runner, before any slow
      // agent startup, so a null result means "never started", not "slow").
      if (instanceData == null) {
        await posthogCapture('session_create_failed', properties: {
          'agent_type': _model.selectedAgentType ?? 'claude',
          'reason': 'instance_never_registered',
        });
        await _showErrorDialog(_sessionDidNotStartMessage(context));
        return;
      }

      // The user typed a first message (bundled into the spawn command). Mark
      // the getting-started checklist's "Send a message" step done instantly —
      // otherwise its server-derived total_user_messages check races the
      // daemon's cold-start prompt POST, reads 0, latches, and the checkmark
      // lags ~10–20s (until the card is next recreated). Mirrors the in-chat
      // send path (agent_chat_model).
      if (hasInitialPrompt) {
        FFAppState().gettingStartedActivated = true;
      }

      await posthogCapture('session_created', properties: {
        'agent_type': _model.selectedAgentType ?? 'claude',
        'source': 'mobile',
      });
      // One-shot: fire `first_remote_session_created` the first time the user
      // creates a session via this UI (distinct from `first_session_observed`,
      // which can fire from a TUI-spawned session that never traverses here).
      if (!FFAppState().analyticsFlags.hasCreatedFirstRemoteSession) {
        await posthogCapture('first_remote_session_created', properties: {
          'agent_type': _model.selectedAgentType ?? 'claude',
          'source': 'mobile',
        });
        FFAppState().updateAnalyticsFlags(
            (f) => f.hasCreatedFirstRemoteSession = true);
      }
      // The session spawned idle when attachments were present — upload them
      // now (the instance exists) and deliver the prompt + files as the first
      // message. Uploads that fail are dropped; the prompt still goes through.
      if (hasAttachments) {
        final ids = await _model.uploadPendingAttachments(agentInstanceId);
        if (ids.isNotEmpty || promptText.isNotEmpty) {
          await actions.apiChatWithAgent(agentInstanceId, promptText,
              attachmentIds: ids);
        }
      }
      // Launched from a task: link the spawned session to it and advance the
      // task to in_progress (mirrors the web new-session flow). Best-effort —
      // the session already exists, so a failed link must not block navigation.
      if (widget.taskId != null && widget.taskId!.isNotEmpty) {
        try {
          await actions.apiUpdateAgentInstance(
              agentInstanceId, {'task_id': widget.taskId});
          await actions.apiUpdateTask(
              widget.taskId!, {'status': 'in_progress'});
          for (final subId in widget.subtaskIds ?? const <String>[]) {
            await actions.apiUpdateTask(subId, {'status': 'in_progress'});
          }
        } catch (_) {}
      }
      _model.clearDraftPrompt();
      context.pop({
        'status': 'success',
        'instanceId': agentInstanceId,
        'instanceData': instanceData,
        'hasInitialPrompt': hasInitialPrompt,
      });
    } catch (e) {
      await posthogCapture('session_create_failed', properties: {
        'agent_type': _model.selectedAgentType ?? 'claude',
        'reason': 'exception',
        'error': e.toString(),
      });
      rethrow;
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  Future<void> _showErrorDialog(String? errorMessage) async {
    if (!mounted) return;
    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => InfoDialogWidget(
        title: AppLocalizations.of(context).newSessionUnableToStart,
        content: _buildErrorMessage(errorMessage),
      ),
    );
  }

  Future<void> _showVoiceError(String message, bool shouldOpenSettings) async {
    if (!mounted) return;
    await showModalBottomSheet(
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      enableDrag: false,
      context: context,
      builder: (context) {
        return SnackBarWidget(
          content: message,
          waitTime: 2000,
        );
      },
    );
    if (shouldOpenSettings) {
      await Future.delayed(const Duration(milliseconds: 500));
      await AppSettings.openAppSettings();
      _model.shouldOpenSpeechSettings = false;
    }
  }

  /// Message shown when the spawned session never registered an instance —
  /// names the agent and points at the likely causes (not installed on the
  /// machine, or an out-of-date daemon).
  String _sessionDidNotStartMessage(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final agentId = _model.selectedAgentType;
    final label =
        (agentId != null ? _model.agentCatalog?.agentById(agentId)?.label : null) ??
            l10n.newSessionTheAgent;
    return l10n.newSessionAgentDidNotStart(label);
  }

  String _buildErrorMessage(String? error) {
    final trimmed = error?.trim();
    if (trimmed != null && trimmed.isNotEmpty) {
      // Safety net: never surface a raw `RpcException(<code>)`. A connectivity
      // code is already mapped to friendly copy upstream; anything still
      // reaching here (an unmapped code) falls back to the generic body rather
      // than reading as an internal error string.
      if (trimmed.startsWith('RpcException(')) {
        return AppLocalizations.of(context).newSessionUnableToStartBody;
      }
      return trimmed;
    }
    return AppLocalizations.of(context).newSessionUnableToStartBody;
  }
}
