import '/backend/agent_catalog.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_git.dart';
import '/custom_code/utils/file_mention_utils.dart';
import '/custom_code/utils/machine_utils.dart';
import '/custom_code/utils/slash_command_utils.dart';
import '/custom_code/utils/worktree_selection.dart';
import '/pages/agent_chat/components/pending_attachment.dart';
import '/pages/agent_chat/components/voice_dictation_bar.dart';
import '/pages/agent_chat/voice_transcription_provider.dart';
import 'new_session_widget.dart' show NewSessionWidget;
import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';
import 'dart:convert';

class NewSessionModel extends FlutterFlowModel<NewSessionWidget>
    with FileMentionMixin, SlashCommandMixin {
  List<dynamic> machines = [];
  bool isLoadingMachines = true;
  String? selectedMachineId;
  // Machines a live spawn/resume RPC just failed against (no_handler /
  // disconnected). The heartbeat-driven "online" badge (machine_utils, 90s
  // window) can lag a dead WebSocket link, so a spawn can fail against a
  // machine the picker still shows online. A failed RPC is ground truth the
  // link is down: mark it offline locally so the picker greys it and Submit
  // disables, breaking the tap-retry-tap loop. Auto-expires (a link that
  // recovers isn't hidden forever) and is cleared early when the user re-picks
  // the machine.
  final Map<String, DateTime> _rpcOfflineMarks = {};
  static const Duration _rpcOfflineWindow = Duration(seconds: 45);
  Timer? _refreshTimer;
  Timer? _directoryDebounceTimer;
  String? _selectedAgentType;
  String? get selectedAgentType => _selectedAgentType;
  set selectedAgentType(String? value) {
    _selectedAgentType = value;
    if (value != null) {
      FFAppState().updateUserPreferences((p) => p..newSessionAgentType = value);
    }
  }
  TextEditingController directoryController = TextEditingController();
  FocusNode directoryFocusNode = FocusNode();
  // Worktree selection (only meaningful when the selected machine advertises
  // worktree support and the directory is a git repo). `none` keeps today's
  // spawn-in-directory behavior.
  WorktreeMode worktreeMode = WorktreeMode.none;
  String? selectedWorktreePath;
  String? selectedWorktreeBranch;
  // Whether the selected directory is a git repo, probed per directory. `null`
  // means unknown (offline machine or a failed probe) and keeps the worktree
  // card visible; only a definitive `not_a_repo` hides it. The previous answer
  // is held while a probe is in flight so the card doesn't blink when moving
  // between two non-repo folders.
  bool? directoryIsGitRepo;
  int _gitRepoProbeToken = 0;
  TextEditingController promptController = TextEditingController();
  FocusNode promptFocusNode = FocusNode();
  bool isSubmitting = false;
  VoidCallback? onStateChanged;

  // Files picked for the first message. Upload is deferred to submit time —
  // /api/v1/attachments needs an agent_instance_id, and no instance exists
  // until the session spawns (see _submit in the widget).
  final List<PendingAttachment> pendingAttachments = [];
  late VoiceTranscriptionProvider voiceTranscriptionProvider;
  String? speechErrorMessage;
  bool shouldOpenSpeechSettings = false;
  VoiceDictationUiState? voiceDictationUiState;
  String voiceCommittedTranscript = '';
  String voicePartialTranscript = '';
  String _voiceOriginalDraft = '';
  Duration voiceElapsedDuration = Duration.zero;
  Timer? _voiceElapsedTimer;

  // SSE polling state for spawn request
  StreamSubscription<Map<String, dynamic>>? _instanceStreamSubscription;

  // Draft persistence key for the new-session prompt. Reuses the chat-draft
  // store keyed by instanceId; the leading underscores guarantee no collision
  // with real UUIDs.
  static const String _draftPromptKey = '__new_session__';

  void saveDraftPrompt() {
    FFAppState().setChatDraft(_draftPromptKey, promptController.text);
  }

  void restoreDraftPrompt() {
    final draftText = FFAppState().getChatDraft(_draftPromptKey);
    if (draftText.isNotEmpty) {
      promptController.text = draftText;
      promptController.selection = TextSelection.fromPosition(
        TextPosition(offset: draftText.length),
      );
      filterFileMentions(draftText);
    }
  }

  void clearDraftPrompt() {
    promptController.clear();
    FFAppState().clearChatDraft(_draftPromptKey);
  }

  /// Agents offered by the new-session UI — derived from the catalog so a
  /// new agent ships via a catalog bump instead of a hardcoded list here.
  List<Map<String, dynamic>> get agentTypes => [
        for (final a in (agentCatalog?.agents ?? const <CatalogAgent>[]))
          {'id': a.id, 'name': a.label, 'isComingSoon': false},
      ];

  // Per-agent catalog + selection state (plan §7.3). Loaded SWR-style on
  // sheet open; the baked-in fallback keeps the sheet renderable offline.
  static const String _persistenceKey = 'vicoa:last-remote-session-selection-v2';
  static const String _legacyPersistenceKey = 'vicoa:last-remote-session-selection';
  AgentCatalog? agentCatalog;
  bool isLoadingCatalog = false;
  /// Selected machine's cached real model lists, keyed by agent id. Filled
  /// lazily from GET /machines/{id}/agent-models so the picker can show a
  /// machine's actual models instead of catalog placeholders. Empty until an
  /// ACP agent has run on the machine once (then we fall back to the catalog).
  Map<String, List<Map<String, String>>> _machineAgentModels = {};

  /// Catalog the new-session picker should render: the base catalog with the
  /// selected machine's cached models merged in (falls back to base).
  AgentCatalog? get pickerCatalog {
    final base = agentCatalog;
    if (base == null) return null;
    return _machineAgentModels.isEmpty
        ? base
        : catalogWithCachedModels(base, _machineAgentModels);
  }

  final Map<String, SessionConfig> _perAgentConfigs = {};
  SessionConfig? get sessionConfig {
    final agent = _selectedAgentType;
    if (agent == null) return null;
    return _perAgentConfigs[agent];
  }

  // FileMentionMixin requirements
  @override
  TextEditingController get fileMentionTextController => promptController;
  @override
  VoidCallback? get fileMentionOnStateChanged => onStateChanged;

  // SlashCommandMixin requirements
  @override
  TextEditingController get slashCommandTextController => promptController;
  @override
  VoidCallback? get slashCommandOnStateChanged => onStateChanged;
  @override
  String? resolveSlashCommandRawAgentType() => _selectedAgentType;

  @override
  void initState(BuildContext context) {
    debugLogWidgetClass(this);

    // Bootstrap config state from the baked-in fallback FIRST — agentTypes
    // (and therefore isAgentTypeSelectable) derive from the catalog now, so
    // the saved-agent restore below needs it in place.
    agentCatalog = agentCatalogFallback();
    _hydratePerAgentDefaults();

    // Restore last-used agent type, falling back to first selectable
    final appState = FFAppState();
    final savedAgent = appState.userPreferences.newSessionAgentType;
    if (savedAgent != null && isAgentTypeSelectable(savedAgent)) {
      selectedAgentType = savedAgent;
    } else {
      final available = agentTypes;
      final defaultAgent = available.firstWhere(
        (a) => !(a['isComingSoon'] as bool? ?? false),
        orElse: () => available.isNotEmpty ? available.first : {'id': 'claude'},
      );
      selectedAgentType = defaultAgent['id'] as String?;
    }

    // Restore last-used machine (validated after machines load)
    selectedMachineId = appState.userPreferences.newSessionMachineId;
    voiceTranscriptionProvider = DeepgramVoiceTranscriptionProvider();

    _loadMachines();
    _refreshTimer = Timer.periodic(Duration(seconds: 30), (_) => _refreshMachines());

    _restorePersistedSelection().then((_) => loadAgentCatalog());
    unawaited(loadSlashCommands());
  }

  void _hydratePerAgentDefaults() {
    final catalog = agentCatalog;
    if (catalog == null) return;
    for (final agent in catalog.agents) {
      _perAgentConfigs.putIfAbsent(agent.id, () => SessionConfig.defaultsFor(catalog, agent.id));
    }
  }

  Future<void> _restorePersistedSelection() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      String? rawV2 = prefs.getString(_persistenceKey);
      if (rawV2 == null) {
        // Silent v1 → v2 migration (plan §3.5). v1 only stored {machineId, agent}.
        final rawV1 = prefs.getString(_legacyPersistenceKey);
        if (rawV1 != null) {
          try {
            final v1 = json.decode(rawV1) as Map<String, dynamic>;
            final migrated = <String, dynamic>{
              'lastMachineId': v1['machineId'],
              'lastAgent': v1['agent'],
              'perAgent': const <String, dynamic>{},
            };
            await prefs.setString(_persistenceKey, json.encode(migrated));
            await prefs.remove(_legacyPersistenceKey);
            rawV2 = json.encode(migrated);
          } catch (_) {
            // Garbage in v1 → ignore and let caller start fresh.
          }
        }
      }
      if (rawV2 == null) return;
      final decoded = json.decode(rawV2) as Map<String, dynamic>;
      final lastAgent = decoded['lastAgent'] as String?;
      if (lastAgent != null && isAgentTypeSelectable(lastAgent)) {
        selectedAgentType = lastAgent;
      }
      final perAgent = decoded['perAgent'] as Map<String, dynamic>?;
      if (perAgent != null) {
        perAgent.forEach((agentId, raw) {
          if (raw is Map) {
            _perAgentConfigs[agentId] = SessionConfig.fromJson(Map<String, dynamic>.from(raw));
          }
        });
      }
      onStateChanged?.call();
      unawaited(loadSlashCommands());
    } catch (e) {
      debugPrint('NewSession: failed to restore persisted selection: $e');
    }
  }

  Future<void> _persistSelection() async {
    final catalog = agentCatalog;
    final perAgentJson = <String, dynamic>{};
    _perAgentConfigs.forEach((agentId, cfg) {
      perAgentJson[agentId] = cfg.toJson();
    });
    final payload = <String, dynamic>{
      'lastMachineId': selectedMachineId,
      'lastAgent': _selectedAgentType,
      'perAgent': perAgentJson,
    };
    if (catalog != null) payload['catalogVersion'] = catalog.version;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_persistenceKey, json.encode(payload));
    } catch (e) {
      debugPrint('NewSession: persist failed: $e');
    }
  }

  /// SWR-style refresh: keep current state visible, fetch in background,
  /// reconcile against the live catalog when it arrives (plan §3.11).
  Future<void> loadAgentCatalog() async {
    if (isLoadingCatalog) return;
    isLoadingCatalog = true;
    try {
      final fresh = await actions.apiGetAgentCatalog();
      agentCatalog = fresh;
      // Reconcile each agent's config against the new catalog so stored stale
      // values fall back to catalog defaults silently (plan §3.5 step 3).
      final reconciled = <String, SessionConfig>{};
      for (final agent in fresh.agents) {
        final prior = _perAgentConfigs[agent.id];
        reconciled[agent.id] = prior != null ? prior.reconcileAgainst(fresh) : SessionConfig.defaultsFor(fresh, agent.id);
      }
      _perAgentConfigs
        ..clear()
        ..addAll(reconciled);
      onStateChanged?.call();
    } finally {
      isLoadingCatalog = false;
    }
  }

  /// Replace the active session config and persist. The active agent is
  /// derived from [config.agent] so changing agents inside the sheet flows
  /// naturally through this single setter.
  void setSessionConfig(SessionConfig config) {
    _selectedAgentType = config.agent;
    _perAgentConfigs[config.agent] = config;
    if (isAgentTypeSelectable(config.agent)) {
      FFAppState().updateUserPreferences((p) => p..newSessionAgentType = config.agent);
    }
    _persistSelection();
    onStateChanged?.call();
    unawaited(loadSlashCommands());
  }

  String get sessionConfigSummaryText {
    final cfg = sessionConfig;
    final catalog = agentCatalog;
    if (cfg == null || catalog == null) {
      final agent = agentTypes.firstWhere((a) => a['id'] == _selectedAgentType, orElse: () => {});
      return (agent['name'] as String?) ?? 'Agent';
    }
    return sessionConfigSummary(catalog, cfg);
  }

  bool get isVoiceDictationVisible => voiceDictationUiState != null;
  bool get isSpeechInitializing => voiceDictationUiState == VoiceDictationUiState.starting;
  bool get isListening => voiceDictationUiState == VoiceDictationUiState.listening;
  bool get isVoiceProcessing => voiceDictationUiState == VoiceDictationUiState.processing;
  bool get canConfirmVoiceInput => isListening;
  String get voiceDisplayTranscript {
    final partial = voicePartialTranscript.trim();
    if (partial.isNotEmpty) {
      final committed = voiceCommittedTranscript.trim();
      return committed.isEmpty ? partial : '$committed $partial';
    }
    return voiceCommittedTranscript.trim();
  }

  RecorderController? get voiceRecorderController => voiceTranscriptionProvider.recorderController;

  Future<void> startDictation() async {
    if (isVoiceDictationVisible) {
      return;
    }
    speechErrorMessage = null;
    shouldOpenSpeechSettings = false;
    _voiceOriginalDraft = promptController.text.trimRight();
    voiceCommittedTranscript = '';
    voicePartialTranscript = '';
    voiceElapsedDuration = Duration.zero;
    voiceDictationUiState = VoiceDictationUiState.starting;
    _startVoiceElapsedTimer();
    onStateChanged?.call();
    final started = await _startVoiceRecognitionSession();
    if (!started) {
      _voiceElapsedTimer?.cancel();
      voiceDictationUiState = null;
      if (speechErrorMessage == null) {
        speechErrorMessage = 'Speech recognition is unavailable right now.';
      }
      onStateChanged?.call();
    }
  }

  Future<void> stopDictation({bool cancel = false, bool commitToInput = false}) async {
    if (!isVoiceDictationVisible && !voiceTranscriptionProvider.isListening) {
      return;
    }
    if (cancel) {
      voiceDictationUiState = null;
      onStateChanged?.call();
      await voiceTranscriptionProvider.cancel();
      _resetVoiceDictationState();
    } else {
      voiceDictationUiState = VoiceDictationUiState.processing;
      onStateChanged?.call();
      await voiceTranscriptionProvider.stop();
      final hasSpeechError = speechErrorMessage?.isNotEmpty == true;
      if (commitToInput && !hasSpeechError && voiceDisplayTranscript.trim().isNotEmpty) {
        _commitVoiceTranscriptToInput();
      }
      _resetVoiceDictationState();
    }
  }

  Future<bool> _startVoiceRecognitionSession() async {
    final started = await voiceTranscriptionProvider.start(
      onResult: _handleSpeechResult,
      onStatus: _handleSpeechStatus,
      onError: _handleSpeechError,
    );
    if (started) {
      voiceDictationUiState = VoiceDictationUiState.listening;
      speechErrorMessage = null;
      shouldOpenSpeechSettings = false;
      onStateChanged?.call();
    }
    return started;
  }

  void _handleSpeechStatus(VoiceTranscriptionStatus status) {
    if (status == VoiceTranscriptionStatus.listening) {
      voiceDictationUiState = VoiceDictationUiState.listening;
      onStateChanged?.call();
    }
  }

  void _handleSpeechResult(VoiceTranscriptionResult result) {
    if (result.clearInterim) {
      voicePartialTranscript = '';
      onStateChanged?.call();
      return;
    }
    final recognized = result.text.trim();
    if (recognized.isEmpty) {
      return;
    }
    if (result.isFinal) {
      voiceCommittedTranscript = _appendTranscriptSegment(voiceCommittedTranscript, recognized);
      voicePartialTranscript = '';
    } else {
      voicePartialTranscript = recognized;
    }
    onStateChanged?.call();
  }

  void _handleSpeechError(VoiceTranscriptionError error) {
    speechErrorMessage = error.message;
    shouldOpenSpeechSettings = error.shouldOpenSettings;
    _voiceElapsedTimer?.cancel();
    voiceDictationUiState = null;
    onStateChanged?.call();
  }

  String _appendTranscriptSegment(String existing, String segment) {
    final current = existing.trim();
    final next = segment.trim();
    if (next.isEmpty) {
      return current;
    }
    if (current.isEmpty) {
      return next;
    }
    if (current.toLowerCase().endsWith(next.toLowerCase())) {
      return current;
    }
    return '$current $next'.replaceAll(RegExp(r'\s+'), ' ').trim();
  }

  void _commitVoiceTranscriptToInput() {
    final dictated = voiceDisplayTranscript.trim();
    final combined = _voiceOriginalDraft.isEmpty
        ? dictated
        : dictated.isEmpty
            ? _voiceOriginalDraft
            : '$_voiceOriginalDraft $dictated';
    promptController
      ..text = combined.trim()
      ..selection = TextSelection.fromPosition(TextPosition(offset: combined.trim().length));
    filterFileMentions(promptController.text);
  }

  void _resetVoiceDictationState() {
    _voiceElapsedTimer?.cancel();
    _voiceElapsedTimer = null;
    voiceDictationUiState = null;
    voiceCommittedTranscript = '';
    voicePartialTranscript = '';
    voiceElapsedDuration = Duration.zero;
    onStateChanged?.call();
  }

  void _startVoiceElapsedTimer() {
    _voiceElapsedTimer?.cancel();
    _voiceElapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      voiceElapsedDuration += const Duration(seconds: 1);
      onStateChanged?.call();
    });
  }

  Future<void> refreshSpeechAvailability() async {
    if (isVoiceDictationVisible) {
      return;
    }
    speechErrorMessage = null;
  }

  Future<void> _refreshMachines() async {
    try {
      final freshMachines = await actions.apiGetMachines();
      machines = _sortMachinesByStatus(freshMachines);
      onStateChanged?.call();
    } catch (e) {
      debugPrint('Error refreshing machines: $e');
    }
  }

  /// Online first, then most-recently-seen first (machine-management D16) —
  /// shared with the machines list page.
  List<dynamic> _sortMachinesByStatus(List<dynamic> source) =>
      sortMachinesByStatus(source);

  Future<void> _loadMachines() async {
    try {
      final freshMachines = await actions.apiGetMachines();
      machines = _sortMachinesByStatus(freshMachines);
      // Validate restored machine ID; fall back to default if not found
      if (selectedMachineId != null) {
        final exists = machines.any((m) => (m['machine_id'] ?? m['id']) == selectedMachineId);
        if (!exists) selectedMachineId = null;
      }
      if (selectedMachineId == null && machines.isNotEmpty) {
        _selectDefaultMachine();
      } else if (selectedMachineId != null) {
        // Restore directory + worktree for the saved machine
        final machine = machines.firstWhere(
          (m) => (m['machine_id'] ?? m['id']) == selectedMachineId,
          orElse: () => null,
        );
        if (machine != null) _restoreDirectoryAndWorktreeForMachine(machine);
      }
      _ensureAgentSupportedByMachine();
      isLoadingMachines = false;
      onStateChanged?.call();
      _reloadDirectoryDerivedState();
      unawaited(_loadMachineAgentModels(selectedMachineId));
    } catch (e) {
      debugPrint('Error loading machines: $e');
      machines = [];
      isLoadingMachines = false;
      onStateChanged?.call();
    }
  }

  void _selectDefaultMachine() {
    if (machines.isEmpty) return;
    // Prefer the first online machine; fall back to the first machine overall.
    final defaultMachine = machines.firstWhere(
      (m) => isMachineOnline(m),
      orElse: () => machines.first,
    );
    selectedMachineId = defaultMachine['machine_id'] ?? defaultMachine['id'];
    FFAppState().updateUserPreferences((p) => p..newSessionMachineId = selectedMachineId);
    _updateDirectoryForMachine(defaultMachine);
    // Sync the persisted directory/worktree to this machine's default so a stale
    // directory from a previous (now gone) machine isn't restored next time.
    _persistDirectory();
    persistWorktreeSelection();
  }

  void selectMachine(String machineId) {
    selectedMachineId = machineId;
    // Re-picking a machine is a fresh intent to use it — drop any stale local
    // offline mark so a recovered link isn't blocked by the leftover override.
    _rpcOfflineMarks.remove(machineId);
    FFAppState().updateUserPreferences((p) => p..newSessionMachineId = machineId);
    // A worktree path is repo- and machine-specific; clear it so it can't carry
    // over to a different machine.
    resetWorktreeSelection();
    final machine = machines.firstWhere(
      (m) => (m['machine_id'] ?? m['id']) == machineId,
      orElse: () => null,
    );
    if (machine != null) _updateDirectoryForMachine(machine);
    // The new machine gets its default directory and a cleared worktree; sync
    // both into persistence so they're what gets restored next visit.
    _persistDirectory();
    persistWorktreeSelection();
    _ensureAgentSupportedByMachine();
    _reloadDirectoryDerivedState();
    // Clear the previous machine's cached models immediately, then refetch so
    // the picker never shows another machine's models while in flight.
    _machineAgentModels = {};
    unawaited(_loadMachineAgentModels(machineId));
  }

  /// Fetch the selected machine's cached per-agent model lists for the picker.
  /// Best-effort: on error or no cache the picker just uses catalog defaults.
  Future<void> _loadMachineAgentModels(String? machineId) async {
    if (machineId == null) return;
    final models = await actions.apiGetMachineAgentModels(machineId);
    // Drop a stale response if the user switched machines mid-flight.
    if (selectedMachineId != machineId) return;
    _machineAgentModels = models;
    onStateChanged?.call();
  }

  /// Refresh everything derived from the selected machine + directory: the
  /// file-mention index and the git-repo probe behind the worktree card.
  void _reloadDirectoryDerivedState() {
    _directoryDebounceTimer?.cancel();
    _directoryDebounceTimer = Timer(const Duration(milliseconds: 500), () {
      loadFileMentions();
      unawaited(_probeDirectoryIsGitRepo());
    });
  }

  /// Ask the daemon whether the selected directory is a git repo. Uses
  /// `git-worktree-list` — the cheapest repo check the daemon exposes, and the
  /// same call the picker sheet makes when it opens. Only a definitive
  /// `not_a_repo` sets false; a transport failure resets to unknown so the card
  /// fails open rather than staying hidden on a real repo.
  Future<void> _probeDirectoryIsGitRepo() async {
    final machineId = selectedMachineId;
    final cwd = directoryController.text.trim();
    final token = ++_gitRepoProbeToken;
    if (machineId == null || cwd.isEmpty || !isMachineOnline(getSelectedMachine())) {
      directoryIsGitRepo = null;
      onStateChanged?.call();
      return;
    }
    bool? isRepo;
    try {
      await rpcGitWorktreeList(call: actions.VicoaWsClient.instance.callRpc, machineId: machineId, cwd: cwd);
      isRepo = true;
    } on GitOpsException catch (e) {
      if (e.code == 'not_a_repo') isRepo = false;
    } catch (e) {
      debugPrint('NewSession: git-repo probe failed: $e');
    }
    // Drop a stale response if the directory/machine changed mid-flight.
    if (token != _gitRepoProbeToken) return;
    directoryIsGitRepo = isRepo;
    onStateChanged?.call();
  }

  void onDirectoryChanged() {
    // The worktree list is per-directory; a new directory invalidates any
    // prior worktree selection.
    resetWorktreeSelection();
    _persistDirectory();
    persistWorktreeSelection();
    _reloadDirectoryDerivedState();
  }

  void _updateDirectoryForMachine(dynamic machine) {
    final recentDirs = _getRecentDirectories(machine);
    if (recentDirs.isNotEmpty) {
      directoryController.text = recentDirs.first;
    } else {
      final homeDir = getMachineHomeDir(machine);
      directoryController.text = homeDir ?? '~/';
    }
  }

  List<String> _getRecentDirectories(dynamic machine) {
    if (machine is Map) {
      final dirs = machine['recent_directories'];
      if (dirs is List) return dirs.map((d) => d.toString()).toList();
      final metadata = machine['metadata'];
      if (metadata is Map && metadata['recent_directories'] is List) {
        return (metadata['recent_directories'] as List).map((d) => d.toString()).toList();
      }
    }
    return [];
  }

  List<String> getRecentDirectories() {
    final appState = FFAppState();
    if (selectedMachineId == null) return appState.cachedDirectories;
    final machine = machines.firstWhere(
      (m) => (m['machine_id'] ?? m['id']) == selectedMachineId,
      orElse: () => null,
    );
    if (machine != null) {
      final machineRecent = _getRecentDirectories(machine);
      final combined = <String>{...machineRecent, ...appState.cachedDirectories}.toList();
      return combined.take(20).toList();
    }
    return appState.cachedDirectories;
  }

  // Delegate to the shared machine_utils helpers so this screen and the
  // machines list page agree on the online window (90s, machine-management D5)
  // and the display-name fallbacks — single source of truth, no duplication.
  bool isMachineOnline(dynamic machine) {
    final id = machine is Map
        ? (machine['machine_id'] ?? machine['id'])?.toString()
        : null;
    // A recent RPC failure overrides the heartbeat badge (see _rpcOfflineMarks).
    if (id != null && _isLocallyOffline(id)) return false;
    return isMachineOnlineFromMap(machine);
  }

  /// Record that a spawn/resume RPC just failed against [machineId] because its
  /// live link is down, so the picker treats it as offline until the mark ages
  /// out. Called from the New Session screen on a connectivity RPC error.
  void markMachineRpcOffline(String machineId) {
    _rpcOfflineMarks[machineId] = DateTime.now();
    onStateChanged?.call();
  }

  bool _isLocallyOffline(String machineId) {
    final at = _rpcOfflineMarks[machineId];
    if (at == null) return false;
    if (DateTime.now().difference(at) >= _rpcOfflineWindow) {
      _rpcOfflineMarks.remove(machineId);
      return false;
    }
    return true;
  }

  String getMachineDisplayName(dynamic machine) => machineDisplayName(machine);

  dynamic getSelectedMachine() {
    if (selectedMachineId == null) return null;
    return machines.firstWhere(
      (m) => (m['machine_id'] ?? m['id']) == selectedMachineId,
      orElse: () => null,
    );
  }

  bool isAgentTypeSelectable(String? agentId) {
    if (agentId == null) return false;
    final agent = agentTypes.firstWhere((a) => a['id'] == agentId, orElse: () => {});
    if (agent.isEmpty || (agent['isComingSoon'] as bool? ?? false)) return false;
    return isAgentSupportedByMachine(agentId);
  }

  /// available_agents map from the selected machine's daemon metadata.
  /// Null when the machine (or an old daemon) doesn't report availability.
  Map<String, bool>? get selectedMachineAvailableAgents =>
      parseAvailableAgents(getSelectedMachine());

  /// Whether the selected machine's daemon supports git worktrees. Drives
  /// whether the new-session worktree card is shown at all (§5.3). False for
  /// old daemons that don't advertise the capability.
  bool get selectedMachineSupportsWorktree =>
      machineSupportsWorktree(getSelectedMachine());

  /// Reset the worktree selection — used when the machine or directory changes
  /// so a stale worktree path never leaks into a spawn on a different repo.
  void resetWorktreeSelection() {
    worktreeMode = WorktreeMode.none;
    selectedWorktreePath = null;
    selectedWorktreeBranch = null;
  }

  /// Persist the working directory for the selected machine so returning to this
  /// screen restores it (see [_restoreDirectoryAndWorktreeForMachine]).
  void _persistDirectory() {
    FFAppState().updateUserPreferences((p) => p..newSessionDirectory = directoryController.text.trim());
  }

  /// Persist the current worktree selection for the selected machine+directory.
  /// A `none` selection stores null so it reads back as "no restore".
  void persistWorktreeSelection() {
    final wt = worktreeMode == WorktreeMode.none
        ? null
        : <String, dynamic>{'mode': worktreeMode.name, 'path': selectedWorktreePath, 'branch': selectedWorktreeBranch};
    FFAppState().updateUserPreferences((p) => p..newSessionWorktree = wt);
  }

  /// Restore the directory + worktree persisted for the saved machine. Both are
  /// always written together, so the stored worktree matches the stored
  /// directory; a missing directory falls back to the machine default with no
  /// worktree restored.
  void _restoreDirectoryAndWorktreeForMachine(dynamic machine) {
    final savedDir = FFAppState().userPreferences.newSessionDirectory;
    if (savedDir == null || savedDir.isEmpty) {
      _updateDirectoryForMachine(machine);
      resetWorktreeSelection();
      return;
    }
    directoryController.text = savedDir;
    final wt = FFAppState().userPreferences.newSessionWorktree;
    final modeName = wt == null ? null : wt['mode'] as String?;
    final mode = WorktreeMode.values.firstWhere((m) => m.name == modeName, orElse: () => WorktreeMode.none);
    if (mode == WorktreeMode.none) {
      resetWorktreeSelection();
      return;
    }
    worktreeMode = mode;
    selectedWorktreePath = wt!['path'] as String?;
    selectedWorktreeBranch = wt['branch'] as String?;
  }

  /// Whether the selected machine's daemon can spawn [agentId]. A machine
  /// with no availability metadata is treated as supporting everything
  /// (old daemons predate the field); a machine WITH metadata that lacks
  /// the key cannot spawn that agent (its daemon predates the agent).
  bool isAgentSupportedByMachine(String agentId) {
    final available = selectedMachineAvailableAgents;
    if (available == null) return true;
    return available[agentId] == true;
  }

  /// When the selected machine doesn't support the current agent, fall back
  /// to the first supported one so the picker never points at an agent the
  /// daemon would reject.
  void _ensureAgentSupportedByMachine() {
    final current = _selectedAgentType;
    if (current != null && isAgentSupportedByMachine(current)) return;
    final fallback = agentTypes.firstWhere(
      (a) => isAgentSupportedByMachine(a['id'] as String),
      orElse: () => {},
    );
    if (fallback.isNotEmpty) selectedAgentType = fallback['id'] as String;
  }

  Future<void> loadFileMentions() async {
    if (selectedMachineId == null || isLoadingFileMentions) return;

    final directory = directoryController.text.trim();
    if (directory.isEmpty) {
      fileMentions = [];
      return;
    }

    isLoadingFileMentions = true;

    try {
      final machine = getSelectedMachine();
      final homeDir = getMachineHomeDir(machine);
      final absolutePath = functions.toAbsolutePath(directory, homeDir);

      if (absolutePath == null || absolutePath.isEmpty) {
        fileMentions = [];
        return;
      }

      debugPrint('Loading file mentions for new session: $absolutePath');
      final files = await actions.apiGetFileMentions(absolutePath);
      fileMentions = files;
      debugPrint('Loaded ${fileMentions.length} file mentions');
    } catch (e) {
      debugPrint('Error loading file mentions: $e');
      fileMentions = [];
    } finally {
      isLoadingFileMentions = false;
      onStateChanged?.call();
    }
  }

  bool get canSubmit {
    return selectedMachineId != null &&
        directoryController.text.trim().isNotEmpty &&
        isAgentTypeSelectable(selectedAgentType) &&
        isMachineOnline(getSelectedMachine()) &&
        !isSubmitting;
  }

  Future<void> pickImageFromLibrary() => _pickImage(ImageSource.gallery);
  Future<void> takePhotoAndAttach() => _pickImage(ImageSource.camera);

  Future<void> _pickImage(ImageSource source) async {
    try {
      final picked = await ImagePicker().pickImage(
        source: source,
        maxWidth: 2048,
        maxHeight: 2048,
        imageQuality: 85,
      );
      if (picked == null) return;
      pendingAttachments.add(PendingAttachment(localPath: picked.path));
      onStateChanged?.call();
    } catch (e) {
      debugPrint('Error picking image: $e');
    }
  }

  Future<void> pickFilesAndAttach() async {
    try {
      final result = await FilePicker.platform
          .pickFiles(allowMultiple: true, withData: false);
      if (result == null) return;
      for (final f in result.files) {
        final path = f.path;
        if (path == null) continue;
        pendingAttachments.add(PendingAttachment(
          localPath: path,
          filename: f.name,
          isImage: isImageFilename(f.name),
        ));
      }
      onStateChanged?.call();
    } catch (e) {
      debugPrint('Error picking files: $e');
    }
  }

  void removePendingAttachment(PendingAttachment attachment) {
    pendingAttachments.remove(attachment);
    onStateChanged?.call();
  }

  /// Uploads the picked attachments against the just-created [instanceId] and
  /// returns the successful attachment ids. Deferred from pick time because
  /// /api/v1/attachments requires an instance to scope against; failures are
  /// dropped so a flaky upload doesn't sink the already-created session.
  Future<List<String>> uploadPendingAttachments(String instanceId) async {
    final ids = <String>[];
    for (final a in pendingAttachments) {
      final result = await actions.apiUploadAttachment(
          instanceId, a.localPath, a.filename);
      if (result is Map && result['id'] != null) {
        ids.add(result['id'] as String);
      }
    }
    return ids;
  }

  /// Polls for instance ID via SSE stream after spawning. When
  /// [includePromptInSpawn] is false the session spawns idle (no --prompt) so
  /// the caller can send the prompt together with attachments as the first
  /// message once the instance exists (attachments can't ride the spawn).
  Future<Map<String, dynamic>> startSession(
      {bool includePromptInSpawn = true}) async {
    if (!canSubmit) {
      return {'success': false, 'error': 'Please fill in all required fields'};
    }

    isSubmitting = true;
    onStateChanged?.call();

    try {
      final directory = directoryController.text.trim();
      final prompt =
          includePromptInSpawn ? promptController.text.trim() : '';

      FFAppState().addToCachedDirectories(directory);

      final cfg = sessionConfig;
      final extraMetadata = cfg?.toSpawnMetadata();
      // Map the worktree selection onto the spawn directory + optional param.
      final spawn = resolveWorktreeSpawn(
        mode: worktreeMode,
        baseDirectory: directory,
        selectedWorktreePath: selectedWorktreePath,
      );
      final result = await actions.apiSpawnSession(
        selectedMachineId!,
        spawn.directory,
        agent: selectedAgentType ?? 'claude',
        prompt: prompt,
        extraMetadata: extraMetadata,
        worktree: spawn.worktree,
      );

      return result;
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    } finally {
      isSubmitting = false;
      onStateChanged?.call();
    }
  }

  void cancelInstanceStream() {
    _instanceStreamSubscription?.cancel();
    _instanceStreamSubscription = null;
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _instanceStreamSubscription?.cancel();
    _directoryDebounceTimer?.cancel();
    disposeFileMentionMixin();
    _voiceElapsedTimer?.cancel();
    directoryController.dispose();
    directoryFocusNode.dispose();
    promptController.dispose();
    promptFocusNode.dispose();
    voiceTranscriptionProvider.dispose();
  }
}
