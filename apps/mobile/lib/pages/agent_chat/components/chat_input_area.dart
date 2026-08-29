import 'package:app_settings/app_settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '/backend/agent_catalog.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/agent_chat/agent_chat_model.dart';
import '/pages/agent_chat/components/add_to_chat_actions.dart';
import '/pages/agent_chat/components/pending_attachment.dart';
import '/pages/agent_chat/components/agent_config_panel.dart';
import '/pages/agent_chat/components/chat_usage_indicator.dart';
import '/pages/agent_chat/components/voice_dictation_bar.dart';
import '/pages/agent_chat/components/voice_dictation_button.dart';
import '/pages/new_session/components/agent_config_sheet.dart';
import '/pages/snack_bar/snack_bar_widget.dart';

/// Isolated chat input area widget to prevent rebuilds of the parent widget
/// when user is typing or voice state changes.
class ChatInputArea extends StatelessWidget {
  const ChatInputArea({
    Key? key,
    required this.model,
    required this.supportsControlSettings,
    required this.onSendMessage,
    required this.onRequestAutoScroll,
    required this.onOpenWebPreview,
    this.onOpenFiles,
    this.showYoloMode = false,
  }) : super(key: key);

  final AgentChatModel model;
  final bool supportsControlSettings;
  final Future<void> Function(String message) onSendMessage;
  final VoidCallback onRequestAutoScroll;
  final VoidCallback onOpenWebPreview;
  // Opens the Files screen for the current session. Null hides the folder
  // button (e.g. legacy sessions that pre-date the machine_id column).
  final VoidCallback? onOpenFiles;
  final bool showYoloMode;

  @override
  Widget build(BuildContext context) {
    const controlButtonGap = 2.0;
    return RepaintBoundary(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4.0),
        child: model.canSendMessages() && model.isVoiceDictationVisible
            ? VoiceDictationBar(
                state: model.voiceDictationUiState!,
                elapsed: model.voiceElapsedDuration,
                recorderController: model.voiceRecorderController,
                confirmEnabled: model.canConfirmVoiceInput,
                onCancel: () async {
                  HapticFeedback.lightImpact();
                  await model.stopDictation(cancel: true);
                },
                onConfirm: () async {
                  HapticFeedback.mediumImpact();
                  await model.stopDictation(commitToInput: true);
                  if (!model.isVoiceDictationVisible &&
                      model.speechErrorMessage?.isNotEmpty == true &&
                      context.mounted) {
                    await _showVoiceError(
                        context,
                        model.speechErrorMessage!,
                        model.shouldOpenSpeechSettings);
                  }
                },
              )
            : _buildTextInputContainer(context, controlButtonGap),
      ),
    );
  }

  /// Builds the on-demand Claude rate-limit fetch for the usage indicator, or
  /// null (keep in-band windows) for non-Claude agents or a session with no
  /// recorded machine. Mirrors the web's `usageFetchLimits` guard.
  Future<List<UsageWindow>?> Function()? _claudeUsageFetch() {
    if (!model.supportsControlSettings()) return null; // Claude only.
    final machineId = model.machineId;
    if (machineId == null || machineId.isEmpty) return null;
    return () => fetchClaudeUsageWindows(
        call: actions.VicoaWsClient.instance.callRpc, machineId: machineId);
  }

  /// Text alone, or at least one picked image (uploads happen at send time);
  /// blocked while a send-time upload is already in flight.
  bool _canSubmit(String message) =>
      (message.trim().isNotEmpty || model.pendingAttachments.isNotEmpty) &&
      !model.hasUploadingAttachments;

  Widget _buildTextInputContainer(
      BuildContext context, double controlButtonGap) {
    final canSend = model.canSendMessages();
    return Container(
      margin: const EdgeInsetsDirectional.fromSTEB(8.0, 0, 8.0, 12.0),
      padding: const EdgeInsetsDirectional.fromSTEB(10.0, 8.0, 10.0, 12.0),
      decoration: BoxDecoration(
        color:
            FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(24.0),
        border: Border.all(
          color:
              FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (model.pendingAttachments.isNotEmpty) ...[
            PendingAttachmentStrip(
              attachments: model.pendingAttachments,
              onRemove: model.removePendingAttachment,
              onRetry: model.retryAttachmentUpload,
            ),
            const SizedBox(height: 6.0),
          ],
          Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(20.0),
            ),
            child: Focus(
              onKeyEvent: (node, event) {
                if (!canSend) return KeyEventResult.ignored;
                if (event is KeyDownEvent &&
                    event.logicalKey == LogicalKeyboardKey.enter &&
                    !HardwareKeyboard.instance.isShiftPressed) {
                  final message = model.messageController.text;
                  if (_canSubmit(message) && !model.isSendingMessage) {
                    FocusScope.of(context).unfocus();
                    onRequestAutoScroll();
                    model.isSendingMessage = true;
                    onSendMessage(message);
                  }
                  return KeyEventResult.handled;
                }
                return KeyEventResult.ignored;
              },
              child: TextFormField(
                controller: model.messageController,
                focusNode: model.messageFocusNode,
                enabled: canSend,
                minLines: 1,
                maxLines: 7,
                keyboardType: TextInputType.multiline,
                scrollPhysics: const BouncingScrollPhysics(),
                textCapitalization: TextCapitalization.sentences,
                textInputAction: TextInputAction.newline,
                onChanged: (text) {
                  model.filterSlashCommands(text);
                  model.filterFileMentions(text);
                },
                decoration: InputDecoration(
                  // A stopped agent gets its own copy — "session ended" would
                  // be wrong for a session that can simply be resumed.
                  hintText: canSend
                      ? AppLocalizations.of(context).chatInputPlaceholder
                      : (model.liveStateHint ??
                          AppLocalizations.of(context).chatInputSessionEnded),
                  hintStyle: FlutterFlowTheme.of(context).bodyMedium.override(
                        color: FlutterFlowTheme.of(context).secondaryText,
                        fontSize: 17.0,
                      ),
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  disabledBorder: InputBorder.none,
                  contentPadding: const EdgeInsetsDirectional.all(8.0),
                ),
                style: FlutterFlowTheme.of(context).bodyMedium.override(
                      fontSize: 17.0,
                    ),
              ),
            ),
          ),
          const SizedBox(height: 4.0),
          Row(children: [
            // "+" button sits at the leftmost slot — opens the Add-to-chat
            // sheet whose options insert "@" / "/" into the message box so
            // the chat input's onChanged runs filterFileMentions /
            // filterSlashCommands. Wrapped in its own IgnorePointer+Opacity
            // because the gear pill (next in the row) is intentionally
            // tappable when !canSend, so we can't share the inner-row
            // IgnorePointer that disables the rest of the controls.
            IgnorePointer(
              ignoring: !canSend,
              child: Opacity(
                opacity: canSend ? 1.0 : 0.4,
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(20.0),
                    onTap: () {
                      HapticFeedback.lightImpact();
                      FocusManager.instance.primaryFocus?.unfocus();
                      // Claude and OpenCode surface both skills and commands
                      // through the same slash trigger; Codex only has
                      // commands. Match the AgentConfigPill's agent-id
                      // resolution so the label stays in sync with how the
                      // rest of the chat input identifies the agent.
                      final hasSkills = model.isOpencodeAgent() ||
                          model.supportsControlSettings();
                      showAddToChatMenu(
                        context: context,
                        controller: model.messageController,
                        focusNode: model.messageFocusNode,
                        fileMention: model,
                        slashCommand: model,
                        hasSkills: hasSkills,
                        onPhotoLibrary: () => model.pickImageFromLibrary(),
                        onTakePhoto: () => model.takePhotoAndAttach(),
                        onChooseFiles: () => model.pickFilesAndAttach(),
                      );
                    },
                    child: Tooltip(
                      message: AppLocalizations.of(context).chatInputAddToChat,
                      child: Container(
                        width: 40.0,
                        height: 40.0,
                        alignment: Alignment.center,
                        child: Icon(
                          Icons.add_rounded,
                          color: FlutterFlowTheme.of(context).secondaryText,
                          size: 22.0,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(width: controlButtonGap),
            // Gear pill stays tappable even for closed sessions — the sheet
            // opens fully frozen so users can still inspect the session's
            // model / reasoning / permission state. Everything else in this
            // row is disabled via the inner IgnorePointer when !canSend.
            // Codex now shows the pill too: model + reasoning_effort +
            // permission_mode are mid-session editable via the Rust bridge
            // (plans/inprogress/mid-session-mode-switching.md).
            if (model.canShowAgentConfigSheet()) ...[
              _AgentConfigPill(model: model, showYoloMode: showYoloMode),
              SizedBox(width: controlButtonGap),
            ],
            // Folder icon ALWAYS renders — it's the primary FilesScreen
            // entry and we don't want it disappearing on users. It sits
            // outside the !canSend gate below (FilesScreen has its own
            // offline surface) and also outside the onOpenFiles-null gate
            // (legacy sessions with no machine_id get a snackbar on tap
            // explaining why files aren't available, instead of a
            // mysteriously missing button).
            Material(
              color: Colors.transparent,
              child: InkWell(
                borderRadius: BorderRadius.circular(20.0),
                onTap: () {
                  HapticFeedback.lightImpact();
                  FocusManager.instance.primaryFocus?.unfocus();
                  if (onOpenFiles != null) {
                    onOpenFiles!();
                  } else {
                    showModalBottomSheet(
                      context: context,
                      isScrollControlled: true,
                      backgroundColor: Colors.transparent,
                      barrierColor: Colors.transparent,
                      builder: (ctx) => Padding(
                        padding: MediaQuery.viewInsetsOf(ctx),
                        child: SnackBarWidget(
                          content:
                              AppLocalizations.of(context).chatInputCliOutdated,
                          waitTime: 3000,
                        ),
                      ),
                    );
                  }
                },
                child: Tooltip(
                  message: AppLocalizations.of(context).chatInputBrowseFiles,
                  child: Container(
                    width: 40.0,
                    height: 40.0,
                    alignment: Alignment.center,
                    child: Icon(
                      Icons.folder_outlined,
                      color: FlutterFlowTheme.of(context).secondaryText,
                      size: 20.0,
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(width: controlButtonGap),
            Expanded(child: IgnorePointer(
              ignoring: !canSend,
              child: Opacity(
                opacity: canSend ? 1.0 : 0.4,
                child: Row(
                  children: [
              Material(
                color: Colors.transparent,
                child: InkWell(
                  borderRadius: BorderRadius.circular(20.0),
                  onTap: () async {
                    HapticFeedback.mediumImpact();
                    await model.sendInterrupt();
                  },
                  child: Tooltip(
                    message: AppLocalizations.of(context).chatInputStopTask,
                    child: Container(
                      width: 40.0,
                      height: 40.0,
                      alignment: Alignment.center,
                      child: Icon(
                        Icons.stop_circle_outlined,
                        color: FlutterFlowTheme.of(context).secondaryText,
                        size: 20.0,
                      ),
                    ),
                  ),
                ),
              ),
              SizedBox(width: controlButtonGap),
              // Context-window + rate-limit usage (Claude + Codex) sits to the
              // right of the interrupt button. Ring only here; details open in
              // a bottom sheet. Self-hides when the session reports no usage.
              // On Claude sessions, opening the sheet also refreshes the
              // Session/Weekly rate-limit windows from the machine's daemon
              // (the in-band ones only update at end of turn).
              ChatUsageIndicator(
                  usage: SessionUsage.fromInstanceData(model.instanceData),
                  fetchLimits: _claudeUsageFetch()),
              Expanded(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (model.latestWebPreviewUrl?.isNotEmpty == true) ...[
                        Material(
                          color: Colors.transparent,
                          child: InkWell(
                            borderRadius: BorderRadius.circular(20.0),
                            onTap: () {
                              HapticFeedback.lightImpact();
                              FocusManager.instance.primaryFocus?.unfocus();
                              onOpenWebPreview();
                            },
                            child: Tooltip(
                              message: AppLocalizations.of(context)
                                  .chatInputOpenWebPreview,
                              child: Container(
                                width: 40.0,
                                height: 40.0,
                                alignment: Alignment.center,
                                child: Icon(
                                  Icons.language_rounded,
                                  color: FlutterFlowTheme.of(context)
                                      .secondaryText,
                                  size: 20.0,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8.0),
              _buildVoiceButton(context),
              const SizedBox(width: 8.0),
              _buildSendButton(context),
                  ],
                ),
              ),
            )),
          ]),
        ],
      ),
    );
  }

  Widget _buildVoiceButton(BuildContext context) {
    return VoiceDictationButton(
      isSpeechInitializing: model.isSpeechInitializing,
      shouldOpenSpeechSettings: model.shouldOpenSpeechSettings,
      onPressed: () async {
        HapticFeedback.lightImpact();
        FocusScope.of(context).unfocus();
        await model.startDictation();
        if (!model.isVoiceDictationVisible &&
            model.speechErrorMessage?.isNotEmpty == true &&
            context.mounted) {
          await _showVoiceError(context, model.speechErrorMessage!,
              model.shouldOpenSpeechSettings);
        }
      },
    );
  }

  Widget _buildSendButton(BuildContext context) {
    return Container(
      width: 40.0,
      height: 40.0,
      decoration: BoxDecoration(
        color:
            FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(20.0),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20.0),
          onTap: model.isSendingMessage
              ? null
              : () async {
                  HapticFeedback.mediumImpact();
                  final message = model.messageController.text;
                  if (_canSubmit(message)) {
                    FocusScope.of(context).unfocus();
                    onRequestAutoScroll();
                    model.isSendingMessage = true;
                    await onSendMessage(message);
                  }
                },
          child: Container(
            width: 40.0,
            height: 40.0,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(20.0),
            ),
            child: model.isSendingMessage
                ? Center(
                    child: SizedBox(
                      width: 20.0,
                      height: 20.0,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.0,
                        valueColor: AlwaysStoppedAnimation<Color>(
                          FlutterFlowTheme.of(context).secondaryText,
                        ),
                      ),
                    ),
                  )
                : Icon(
                    Icons.arrow_upward_rounded,
                    color: FlutterFlowTheme.of(context).primaryText,
                    size: 22.0,
                  ),
          ),
        ),
      ),
    );
  }

  Future<void> _showVoiceError(
      BuildContext context, String message, bool shouldOpenSettings) async {
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
      model.shouldOpenSpeechSettings = false;
    }
  }
}

/// **NOT IN USE — kept for a future switch.**
///
/// The gear icon currently routes to `showAgentConfigSheet` (the dropdown
/// bottom sheet) via `_openSheet`. This floating-overlay implementation —
/// `_toggle` / `_show` / `_remove` / `_entry` plus the `ChatAgentConfigBody`
/// it renders — stays on disk so we can flip back by changing
/// `onTap: _openSheet` to `onTap: _toggle` in `build()` below.
///
/// Original notes: replaces ControlSettingsSelector with a plain settings
/// icon (same 40×40 footprint). Tap opens a floating overlay dialog above
/// the chat input area (mirrors the legacy ControlSettingsSelector behavior).
/// Horizontal extent is inset 16px from each screen edge (chat input box
/// sits at 12px outer + inner margin, so the panel reads as its own
/// surface).
class _AgentConfigPill extends StatefulWidget {
  const _AgentConfigPill({required this.model, required this.showYoloMode});
  final AgentChatModel model;
  final bool showYoloMode;

  @override
  State<_AgentConfigPill> createState() => _AgentConfigPillState();
}

class _AgentConfigPillState extends State<_AgentConfigPill> {
  final GlobalKey _buttonKey = GlobalKey();
  OverlayEntry? _entry;

  @override
  void dispose() {
    _remove();
    super.dispose();
  }

  // Preserved alongside _show/_remove for a future switch back to the overlay
  // panel. Currently the gear icon routes to _openSheet instead.
  // ignore: unused_element
  void _toggle() {
    HapticFeedback.lightImpact();
    if (_entry == null) {
      _show();
    } else {
      _remove();
    }
  }

  /// Open the dropdown-style agent_config_sheet from the new-session screen.
  /// Apply only the dimensions that are live-editable mid-chat (permission
  /// mode for Claude/Codex; opencode mode for OpenCode). Other dimensions
  /// (agent, model, thinking/reasoning) round-trip through the sheet but are
  /// ignored on return because the backend can't change them mid-session.
  Future<void> _openSheet() async {
    HapticFeedback.lightImpact();
    // ACP agents (cursor/gemini/copilot/kimi/hermes) source their modes/models
    // from the live session, not the catalog — render those instead.
    if (widget.model.isAcpAgent()) {
      await _openAcpSheet();
      return;
    }
    var catalog = agentCatalogFallback();
    final agentId = widget.model.isOpencodeAgent()
        ? 'opencode'
        : widget.model.supportsControlSettings()
            ? 'claude'
            : 'codex';
    // Claude / Codex / OpenCode all report their machine-real model list onto
    // session_config.available_models (Claude: catalog + ~/.claude custom
    // models; Codex: account/version-filtered `model/list`; OpenCode:
    // provider-aware). Prefer it over the static catalog so the gear shows what
    // the running agent actually supports; no-ops back to the static list when
    // nothing was reported (older daemon / no discovery).
    catalog = _withLiveModels(catalog, agentId);
    final canSend = widget.model.canSendMessages();
    // Prefer the canonical spawn-time snapshot persisted on the row so the
    // sheet shows model + effort (which the live pill state doesn't track).
    // Falls back to live state for legacy sessions where the column is null.
    // See plans/session-config-storage.md §7.1.
    var initial = initialPillConfigFor(
      instanceData: widget.model.instanceData as Map<dynamic, dynamic>?,
      catalog: catalog,
      fallbackAgentId: agentId,
      livePermissionMode: widget.model.permissionMode.controlValue,
      liveOpencodeMode: widget.model.opencodeAgentMode.apiValue,
    );
    // Open the gear on the model the session is actually running (live
    // current_model), not the spawn-time snapshot. Applies to every non-ACP
    // agent — current_model falls back to the spawn model when discovery hasn't
    // reported, so this is a no-op for un-discovered sessions.
    if (widget.model.acpCurrentModel != null) {
      initial = SessionConfig(
        agent: initial.agent,
        model: widget.model.acpCurrentModel,
        thinkingEffort: initial.thinkingEffort,
        reasoningEffort: initial.reasoningEffort,
        permissionMode: initial.permissionMode,
        opencodeMode: initial.opencodeMode,
      );
    }
    final result = await showAgentConfigSheet(
      context: context,
      catalog: catalog,
      initial: initial,
      hideAgentSelector: true,
      title: AppLocalizations.of(context).chatInputModelConfig,
      heightFraction: 0.55,
      // Closed sessions render as pure state inspection (everything frozen).
      // Active sessions allow model + effort + permission_mode edits for both
      // Claude and Codex per plans/inprogress/mid-session-mode-switching.md.
      freezeModelAndEffort: !canSend,
      freezePermission: !canSend,
      freezeOpencodeMode: !canSend,
      footerNote: !canSend
          ? AppLocalizations.of(context).chatInputSessionReadOnly
          : null,
    );
    if (result == null || !mounted || !canSend) return;
    final initialModel = initial.model;
    final initialEffort = initial.thinkingEffort ?? initial.reasoningEffort;
    if (result.model != null && result.model != initialModel) {
      widget.model.requestModelChange(result.model!);
    }
    final effort = result.thinkingEffort ?? result.reasoningEffort;
    if (effort != null && effort != initialEffort) {
      widget.model.requestEffortChange(effort);
    }
    if (result.permissionMode != null && result.permissionMode != widget.model.permissionMode.controlValue) {
      final mode = AgentPermissionMode.values.firstWhere(
        (e) => e.controlValue == result.permissionMode,
        orElse: () => widget.model.permissionMode,
      );
      widget.model.requestPermissionModeChange(mode);
    }
    if (result.opencodeMode != null && result.opencodeMode != widget.model.opencodeAgentMode.apiValue) {
      final mode = OpencodeAgentMode.values.firstWhere(
        (e) => e.apiValue == result.opencodeMode,
        orElse: () => widget.model.opencodeAgentMode,
      );
      widget.model.requestOpencodeAgentModeChange(mode);
    }
  }

  /// Mid-session config sheet for ACP agents. Reuses the new-session sheet UI
  /// by building a one-agent synthetic catalog from the modes/models the
  /// wrapper reported onto session_config (the agent's real session/new
  /// state). Mode change → set_mode; model change → the wrapper's model
  /// control (live for cursor/copilot, next-session for gemini/kimi).
  Future<void> _openAcpSheet() async {
    final m = widget.model;
    final agentId = m.acpAgentId();
    if (agentId == null) return;
    final canSend = m.canSendMessages();
    final modeEntries = m.acpAvailableModes;
    final modelEntries = m.acpAvailableModels;

    final agent = CatalogAgent(
      id: agentId,
      label: agentId,
      models: modelEntries.isEmpty
          ? null
          : modelEntries.map((e) => CatalogModel(id: e['id']!, label: e['label']!)).toList(),
      thinkingEfforts: const [],
      reasoningEfforts: const [],
      permissionModes: modeEntries.map((e) => CatalogEnumEntry(id: e['id']!, label: e['label']!)).toList(),
      modes: const [],
    );
    final catalog = AgentCatalog(version: 'live', minCliVersion: '0', minClientVersion: '0', agents: [agent]);
    final initial = SessionConfig(agent: agentId, model: m.acpCurrentModel, permissionMode: m.acpCurrentMode);

    final result = await showAgentConfigSheet(
      context: context,
      catalog: catalog,
      initial: initial,
      hideAgentSelector: true,
      title: AppLocalizations.of(context).chatInputSessionConfig,
      heightFraction: 0.5,
      freezeModelAndEffort: !canSend,
      freezePermission: !canSend,
      footerNote: !canSend
          ? AppLocalizations.of(context).chatInputSessionReadOnly
          : null,
    );
    if (result == null || !mounted || !canSend) return;
    if (result.permissionMode != null && result.permissionMode != initial.permissionMode) {
      await m.requestPermissionModeChangeRaw(result.permissionMode!);
    }
    if (result.model != null && result.model != initial.model) {
      await m.requestModelChange(result.model!);
    }
  }

  /// Return [base] with [agentId]'s model list replaced by the live list the
  /// wrapper reported onto session_config — Claude's catalog + ~/.claude custom
  /// models, Codex's account/version-filtered `model/list`, or OpenCode's
  /// provider-aware models. Per-model gating (thinking efforts, permission
  /// opt-ins, default effort) is carried over for models the static catalog
  /// recognizes; unknown (user-custom) models get a plain entry. Falls back to
  /// [base] unchanged when nothing was reported (older daemon / no discovery).
  AgentCatalog _withLiveModels(AgentCatalog base, String agentId) {
    final live = widget.model.acpAvailableModels;
    if (live.isEmpty) return base;
    final known = {for (final m in base.agentById(agentId)?.models ?? const <CatalogModel>[]) m.id: m};
    final models = live.map((e) {
      final id = e['id']!;
      final g = known[id];
      return g == null
          ? CatalogModel(id: id, label: e['label']!)
          : CatalogModel(id: id, label: e['label']!, description: g.description, isDefault: g.isDefault, thinkingEfforts: g.thinkingEfforts, permissionModes: g.permissionModes, defaultThinkingEffort: g.defaultThinkingEffort);
    }).toList();
    final agents = base.agents
        .map((a) => a.id == agentId
            ? CatalogAgent(
                id: a.id,
                label: a.label,
                models: models,
                thinkingEfforts: a.thinkingEfforts,
                reasoningEfforts: a.reasoningEfforts,
                permissionModes: a.permissionModes,
                modes: a.modes,
              )
            : a)
        .toList();
    return AgentCatalog(version: base.version, minCliVersion: base.minCliVersion, minClientVersion: base.minClientVersion, agents: agents);
  }

  void _show() {
    final overlayState = Overlay.of(context, rootOverlay: true);
    final renderBox = _buttonKey.currentContext?.findRenderObject() as RenderBox?;
    if (renderBox == null) return;
    final overlayBox = overlayState.context.findRenderObject() as RenderBox;
    final buttonOffset = renderBox.localToGlobal(Offset.zero, ancestor: overlayBox);

    // Slightly inset from the chat input area's edges (which sit at 12px:
    // 4px outer padding + 8px inner margin). The extra breathing room makes
    // the floating panel feel like its own surface rather than an extension
    // of the input box.
    const horizontalPadding = 16.0;
    // Lift the panel well above the trigger so the input row isn't crowded.
    const verticalGap = 80.0;
    final overlaySize = overlayBox.size;
    final panelWidth = overlaySize.width - 2 * horizontalPadding;
    // `bottom` = distance from the overlay's bottom to the panel's bottom edge.
    final bottomDistance = overlaySize.height - buttonOffset.dy + verticalGap;
    final maxHeight = (buttonOffset.dy - MediaQuery.of(context).padding.top - 16.0 - verticalGap).clamp(120.0, double.infinity);

    final theme = FlutterFlowTheme.of(context);
    _entry = OverlayEntry(
      builder: (ctx) => Stack(children: [
        Positioned.fill(
          child: GestureDetector(behavior: HitTestBehavior.translucent, onTap: _remove),
        ),
        Positioned(
          left: horizontalPadding,
          width: panelWidth,
          bottom: bottomDistance,
          child: Material(
            color: Colors.transparent,
            child: Container(
              constraints: BoxConstraints(maxHeight: maxHeight),
              padding: const EdgeInsets.all(16.0),
              decoration: BoxDecoration(
                color: theme.secondaryBackground,
                // Match the chat input area's border (chat_input_area.dart's
                // _buildTextInputContainer): 24-radius, alpha 0.2 stroke, 1px.
                borderRadius: BorderRadius.circular(24.0),
                border: Border.all(color: theme.secondaryText.withValues(alpha: 0.2), width: 1.0),
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.35), blurRadius: 20.0, offset: const Offset(0, 8)),
                ],
              ),
              child: SingleChildScrollView(
                child: ChatAgentConfigBody(model: widget.model, showYoloMode: widget.showYoloMode),
              ),
            ),
          ),
        ),
      ]),
    );
    overlayState.insert(_entry!);
  }

  void _remove() {
    _entry?.remove();
    _entry = null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    // Mirror the folder / stop / web-preview buttons: Container with
    // `alignment: center` keeps the 20px icon centred inside the 40×40 slot,
    // otherwise the icon lays out top-left and the visual gap to the next
    // button looks ~10px wider than every other control gap.
    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: _buttonKey,
        borderRadius: BorderRadius.circular(20.0),
        // onTap: _toggle,
        // Tap routes to the dropdown sheet for now; the overlay panel infra
        // (_toggle / _show / _remove / _entry) is preserved so we can switch
        // back without restoring the wiring.
        onTap: _openSheet,
        child: Container(
          width: 40.0,
          height: 40.0,
          alignment: Alignment.center,
          child: Icon(Icons.settings_outlined, size: 20.0, color: theme.secondaryText),
        ),
      ),
    );
  }
}
