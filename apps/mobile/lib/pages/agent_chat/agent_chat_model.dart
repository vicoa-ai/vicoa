import '/flutter_flow/app_locale.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/ws_protocol.dart' as ws_protocol;
import '/backend/posthog/posthog_analytics.dart';
import '/custom_code/utils/text_sanitizer.dart';
import '/custom_code/utils/file_mention_utils.dart';
import '/custom_code/utils/slash_command_utils.dart';
import '/index.dart';
import '/constants/welcome_demo_session.dart';
import '/pages/agent_chat/components/voice_dictation_bar.dart';
import '/pages/agent_chat/voice_transcription_provider.dart';
import 'agent_chat_widget.dart' show AgentChatWidget;
import 'components/pending_attachment.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/actions/actions.dart' as local_actions;
import '/profile/no_credit_sheet/no_credit_sheet_widget.dart';
import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';
import 'package:file_picker/file_picker.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';
import 'dart:async';
import 'dart:convert';

enum AgentPermissionMode {
  defaultMode('default', 'Default', controlValue: 'default'),
  planMode('plan', 'Plan mode', controlValue: 'plan'),
  auto('auto', 'Auto mode', controlValue: 'auto'),
  acceptEdits('accept_edits', 'Accept edits', controlValue: 'acceptEdits'),
  bypassPermissions('bypass_permissions', 'YOLO', controlValue: 'bypassPermissions');

  const AgentPermissionMode(this.apiValue, this.displayName, {required this.controlValue});

  final String apiValue;
  final String displayName;
  final String controlValue;
}

enum OpencodeAgentMode {
  build('build', 'Build'),
  plan('plan', 'Plan');

  const OpencodeAgentMode(this.apiValue, this.displayName);

  final String apiValue;
  final String displayName;
}

final RegExp _controlCommandJsonRegex = RegExp(r'\{\s*"type"\s*:\s*"control"[^}]*\}', caseSensitive: false);
const String _waitingForInputMessage = 'Waiting for your input...';
const List<String> _webPreviewLinkKeywords = ['trycloudflare.com', 'ngrok'];
final RegExp _webUrlRegex = RegExp(r'''https?://[^\s<>"'`]+''', caseSensitive: false);

class AgentChatModel extends FlutterFlowModel<AgentChatWidget>
    with FileMentionMixin, SlashCommandMixin {
  final Map<String, DebugDataField> debugGeneratorVariables = {};
  final Map<String, DebugDataField> debugBackendQueries = {};
  final Map<String, FlutterFlowModel> widgetBuilderComponents = {};

  // Chat state
  List<dynamic> messages = [];
  bool isLoadingMessages = false;
  bool isSendingMessage = false;
  // True from successful send until the WebSocket confirms the agent is active.
  // Drives the vibing indicator independently of the send-button spinner.
  bool isWaitingForAgentResponse = false;
  String? instanceId;
  dynamic instanceData;
  String? errorMessage;
  bool hasError = false;
  String? projectRoot; // Project root resolved from the instance record (project + home_dir)
  String? sessionChangeType; // Track session changes: 'renamed', 'deleted', null for no changes
  AgentPermissionMode permissionMode = AgentPermissionMode.defaultMode;
  AgentPermissionMode? pendingPermissionMode;

  // Images picked for the next message (uploaded at send time).
  final List<PendingAttachment> pendingAttachments = [];
  bool get hasUploadingAttachments => pendingAttachments.any((a) => a.uploading);
  // Bumped on every pendingAttachments mutation (add/remove/upload state).
  // The page's _handleModelChanged rebuild gate only repaints for signals it
  // tracks — without this revision a pick/remove wouldn't show until
  // something else (e.g. the keyboard) forced a rebuild.
  int pendingAttachmentsRevision = 0;

  void _notifyAttachmentsChanged() {
    pendingAttachmentsRevision++;
    onStateChanged?.call();
  }

  // Bumped whenever a `message-update` WS frame patches an existing
  // message's `message_metadata` in place. The page's _handleModelChanged
  // rebuild gate diffs message *count*, sending state, etc. — none of which
  // change on an in-place mutation — so without this revision the patched
  // queued/consumed/cancelled + sub-agent state wouldn't repaint until an
  // unrelated event forced a rebuild. Mirrors pendingAttachmentsRevision.
  int messageMetadataRevision = 0;

  // Message ids the user produced by tapping an inline option / permission
  // choice (e.g. "Always allow"). These go out to unblock the current turn —
  // not to queue for later — but the backend stamps them `queued` like any
  // mid-turn send and never `consumed`s them, so they'd otherwise sit in the
  // queue bar forever. Recorded on send so the bar can skip them.
  final Set<String> optionResponseMessageIds = {};

  OpencodeAgentMode opencodeAgentMode = OpencodeAgentMode.build;
  OpencodeAgentMode? pendingOpencodeAgentMode;
  bool? thinkingSettingEnabled;
String? latestWebPreviewUrl;

  // Last seen message tracking
  String? lastSeenMessageId;

  // Streaming state. Messages arrive over the shared user-scoped WebSocket
  // (VicoaWsClient); this model just subscribes to its instance's events.
  bool isStreamingActive = false;
  Function()? onStateChanged;
  // Fires when a status_update event arrives. The widget uses this to mirror
  // the new status into widget.instanceData and FFAppState's
  // cachedAgentInstances — locations the model itself can't reach.
  void Function(String status)? onStatusUpdate;
  StreamSubscription<dynamic>? _streamSubscription;

  // Realtime degradation indicator — `true` when the per-instance message
  // SSE has been disconnected long enough that we're likely missing updates.
  // Debounced so brief blips don't flash a banner.
  bool realtimeDegraded = false;
  Timer? _realtimeDegradedDebounceTimer;
  static const Duration _realtimeDegradedDebounce = Duration(seconds: 5);

  // FileMentionMixin requirements
  @override
  TextEditingController get fileMentionTextController => messageController;
  @override
  VoidCallback? get fileMentionOnStateChanged => onStateChanged;

  // SlashCommandMixin requirements
  @override
  TextEditingController get slashCommandTextController => messageController;
  @override
  VoidCallback? get slashCommandOnStateChanged => onStateChanged;
  @override
  String? resolveSlashCommandRawAgentType() =>
      instanceData?['agent_type_name']?.toString() ??
      instanceData?['agent_type']?.toString();
  @override
  String? resolveSlashCommandMachineId() => _resolveMachineId();
  @override
  String? resolveSlashCommandProjectPath() => _resolveProjectAbsolutePath();
  @override
  void onSlashCommandFilterTriggered() {
    // First `/` keystroke this session — kick off a silent background refresh
    // so newly added custom commands appear on the next keystroke.
    if (_didRefreshSlashCommands) return;
    _didRefreshSlashCommands = true;
    unawaited(refreshSlashCommandsSilently());
  }

  void Function({bool animate})? onScrollToBottomRequested;

  // Thinking timeout management

  // Controllers
  late TextEditingController messageController;
  // Bound to the chat input's TextFormField so widgets can request focus
  // programmatically — e.g. after the Add-to-chat sheet inserts "@" or "/"
  // at the cursor, we re-focus so the user can keep typing without a tap.
  late FocusNode messageFocusNode;
  late ItemScrollController itemScrollController;
  late ItemPositionsListener itemPositionsListener;

  // Speech dictation
  late VoiceTranscriptionProvider voiceTranscriptionProvider;
  String? speechErrorMessage;
  bool shouldOpenSpeechSettings = false;
  VoiceDictationUiState? voiceDictationUiState;
  String voiceCommittedTranscript = '';
  String voicePartialTranscript = '';
  String _voiceOriginalDraft = '';
  Duration voiceElapsedDuration = Duration.zero;
  Timer? _voiceElapsedTimer;

  // Safety net: if the WebSocket never fires after a successful send, drop the
  // vibing indicator after this duration so it doesn't spin forever.
  Timer? _sendingTimeoutTimer;
  static const Duration _sendingTimeout = Duration(seconds: 30);

  @override
  void initState(BuildContext context) {
    debugLogWidgetClass(this);
    messageController = TextEditingController();
    messageFocusNode = FocusNode();
    itemScrollController = ItemScrollController();
    itemPositionsListener = ItemPositionsListener.create();
    voiceTranscriptionProvider = DeepgramVoiceTranscriptionProvider();
  }

  // Save the current draft message to FFAppState
  void saveDraftMessage() {
    if (instanceId != null) {
      final draftText = messageController.text;
      FFAppState().setChatDraft(instanceId!, draftText);
    }
  }

  // Restore the draft message from FFAppState
  void restoreDraftMessage() {
    if (instanceId != null) {
      final draftText = FFAppState().getChatDraft(instanceId!);
      if (draftText.isNotEmpty) {
        messageController.text = draftText;
        messageController.selection = TextSelection.fromPosition(
          TextPosition(offset: draftText.length),
        );
      }
    }
  }

  // Clear the draft message from FFAppState
  void clearDraftMessage() {
    if (instanceId != null) {
      FFAppState().clearChatDraft(instanceId!);
    }
  }

  // Save the last seen message info
  void saveLastSeenMessage() {
    if (instanceId != null && messages.isNotEmpty) {
      final lastMessage = messages.last;
      lastSeenMessageId = lastMessage['id']?.toString();

      // Save to FFAppState
      FFAppState().setLastSeenMessageId(instanceId!, lastSeenMessageId ?? '');
    }
  }

  // Restore the last seen message info from FFAppState
  void restoreLastSeenMessage() {
    if (instanceId != null) {
      lastSeenMessageId = FFAppState().getLastSeenMessageId(instanceId!);
    }
  }

  // Get index of the last seen message
  int? getLastSeenMessageIndex() {
    if (lastSeenMessageId == null || messages.isEmpty) return null;

    final index = messages.indexWhere((msg) => msg['id']?.toString() == lastSeenMessageId);
    return index >= 0 ? index : null;
  }

  // Check if there are new messages since last seen
  bool hasNewMessages() {
    if (lastSeenMessageId == null || messages.isEmpty) return false;

    final lastSeenIndex = getLastSeenMessageIndex();
    if (lastSeenIndex == null) return false;

    // Check if there are messages after the last seen one
    return lastSeenIndex < messages.length - 1;
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

  void setVoiceTranscriptionProvider(VoiceTranscriptionProvider provider) {
    voiceTranscriptionProvider.dispose();
    voiceTranscriptionProvider = provider;
  }

  Future<void> startDictation() async {
    if (isVoiceDictationVisible) {
      return;
    }
    speechErrorMessage = null;
    shouldOpenSpeechSettings = false;
    _voiceOriginalDraft = messageController.text.trimRight();
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
      if (commitToInput &&
          !hasSpeechError &&
          voiceDisplayTranscript.trim().isNotEmpty) {
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
      return;
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
    messageController
      ..text = combined.trim()
      ..selection = TextSelection.fromPosition(TextPosition(offset: combined.trim().length));
    filterSlashCommands(messageController.text);
    filterFileMentions(messageController.text);
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

  // Call this method when app becomes active to refresh speech state
  Future<void> refreshSpeechAvailability() async {
    if (isVoiceDictationVisible) {
      return;
    }
    speechErrorMessage = null;
  }

  // Per-chat-page-session refresh guards. The flag is set when *any* fetch
  // path (chat-open stale check, first-`@`, first-`/`) kicks off, so the
  // resource is refreshed at most once per chat session.
  bool _didRefreshFileMentions = false;
  bool _didRefreshSlashCommands = false;
  // Disk caches older than this on chat open trigger a background refresh.
  static const Duration _cacheStaleThreshold = Duration(days: 1);

  // Load instance details and resolve the project root from the record.
  Future<void> _loadInstanceDetails() async {
    if (instanceId == null) return;

    try {
      final details = await actions.apiGetInstanceById(instanceId!);
      debugPrint(
          'Instance details: ${details['agent_type_name']}, ${details['status']}');
      if (details != null) {
        instanceData = details;

        // The instance record already carries the working directory
        // (`project` + `home_dir`), so resolve the project root directly
        // instead of guessing it from a git diff. The Files / Changes tabs
        // are the source of truth for "what changed" (via daemon RPC).
        projectRoot = _resolveProjectAbsolutePath();
      }
    } catch (e) {
      debugPrint('Error loading instance details: $e');
    }
  }

  bool isOpencodeAgent() {
    final typeName = (instanceData?['agent_type_name']?.toString() ??
            instanceData?['agent_type']?.toString() ??
            '')
        .toLowerCase();
    return typeName.contains('opencode');
  }

  bool supportsControlSettings() {
    final typeName = (instanceData?['agent_type_name']?.toString() ??
            instanceData?['agent_type']?.toString() ??
            '')
        .toLowerCase();
    return typeName.contains('claude');
  }

  bool isCodexAgent() {
    final typeName = (instanceData?['agent_type_name']?.toString() ??
            instanceData?['agent_type']?.toString() ??
            '')
        .toLowerCase();
    return typeName.contains('codex');
  }

  /// Agents whose gear is driven by the live `session_config` the wrapper
  /// reports rather than by the static catalog. 'pi' is LAST on purpose: the
  /// lookup below is a substring match and 'copilot' contains 'pi'.
  static const List<String> _acpAgentIds = [
    'cursor',
    'gemini',
    'copilot',
    'kimi',
    'hermes',
    'omp',
    'pi',
  ];

  /// Catalog id for a live-config agent ('cursor'/'gemini'/'omp'/…), else null.
  String? acpAgentId() {
    // `session_config.agent` is the catalog id the daemon was spawned with, so
    // it is authoritative. `agent_type_name` is the user-editable UserAgent row
    // name and only a fallback for rows that predate session_config — matching
    // on it alone missed every agent whose display name isn't its id
    // ("Oh My Pi" -> omp), leaving those sessions with no config sheet at all.
    final configured = _sessionConfigMap?['agent']?.toString().toLowerCase().trim();
    if (configured != null && _acpAgentIds.contains(configured)) return configured;
    final typeName = (instanceData?['agent_type_name']?.toString() ??
            instanceData?['agent_type']?.toString() ??
            '')
        .toLowerCase();
    for (final id in _acpAgentIds) {
      if (typeName.contains(id)) return id;
    }
    return null;
  }

  bool isAcpAgent() => acpAgentId() != null;

  Map<String, dynamic>? get _sessionConfigMap {
    final sc = instanceData?['session_config'];
    return sc is Map ? Map<String, dynamic>.from(sc) : null;
  }

  /// Parse a `[{id,label}]` list the wrapper reported onto session_config
  /// (available_modes / available_models from the agent's session/new).
  List<Map<String, String>> _acpEntries(String key) {
    final raw = _sessionConfigMap?[key];
    if (raw is! List) return const [];
    final out = <Map<String, String>>[];
    for (final e in raw) {
      if (e is Map && e['id'] != null) {
        out.add({'id': e['id'].toString(), 'label': (e['label'] ?? e['id']).toString()});
      }
    }
    return out;
  }

  List<Map<String, String>> get acpAvailableModes => _acpEntries('available_modes');
  List<Map<String, String>> get acpAvailableModels => _acpEntries('available_models');
  String? get acpCurrentMode =>
      _sessionConfigMap?['current_mode']?.toString() ??
      _sessionConfigMap?['permission_mode']?.toString();
  String? get acpCurrentModel =>
      _sessionConfigMap?['current_model']?.toString() ??
      _sessionConfigMap?['model']?.toString();

  /// Whether the ACP session advertised any switchable modes/models — gates
  /// the gear so we never show an empty sheet.
  bool hasAcpControls() =>
      acpAvailableModes.isNotEmpty || acpAvailableModels.isNotEmpty;

  /// True when the gear pill should be shown — Claude (TUI + headless),
  /// Codex (TUI + native headless), OpenCode, and ACP agents that advertised
  /// live modes/models all surface mid-session editable dimensions.
  bool canShowAgentConfigSheet() {
    return supportsControlSettings() ||
        isCodexAgent() ||
        isOpencodeAgent() ||
        (isAcpAgent() && hasAcpControls());
  }

  /// Send a raw permission/mode change for an ACP agent — an arbitrary mode
  /// id (not the AgentPermissionMode enum, which only covers claude/codex).
  /// The wrapper validates against the agent's live availableModes and
  /// applies it via session/set_mode.
  Future<void> requestPermissionModeChangeRaw(String modeId) async {
    if (instanceId == null || modeId.isEmpty) return;
    final message =
        'Change the permission mode to $modeId. ${_buildControlMessage('permission_mode', modeId)}';
    try {
      await actions.apiChatWithAgent(instanceId!, message);
    } catch (e) {
      debugPrint('Error updating ACP mode: $e');
    }
  }

  // Resolve the project's absolute path on disk from instanceData, or null
  // if it's unavailable. Centralized so cache lookups and network fetches
  // share the same key.
  String? _resolveProjectAbsolutePath() {
    final projectPath = instanceData?['project']?.toString();
    final homeDir = instanceData?['home_dir']?.toString();
    if (projectPath == null || projectPath.isEmpty) return null;
    final absolutePath = functions.toAbsolutePath(projectPath, homeDir);
    if (absolutePath == null || absolutePath.isEmpty) return null;
    return absolutePath;
  }

  // Machine this session runs on, or null for a legacy instance that never
  // recorded one. Null means file mentions read the CLI-synced DB copy rather
  // than the live daemon index.
  String? _resolveMachineId() {
    final machineId = instanceData?['machine_id']?.toString();
    return (machineId == null || machineId.isEmpty) ? null : machineId;
  }

  /// Public accessor for [_resolveMachineId] — the machine this session runs
  /// on, or null for a legacy instance that never recorded one. Used by the
  /// chat input to fetch fresh Claude rate limits from that machine's daemon.
  String? get machineId => _resolveMachineId();

  // Chat-open refresh policy. For each resource:
  //   * No disk cache → kick off the initial load now (file mentions only —
  //     slash commands have always-loaded defaults, so they don't need this).
  //   * Disk cache older than [_cacheStaleThreshold] → silent background
  //     refresh. The popup isn't open yet, so a `setState` here is fine, but
  //     we still call the silent path for code reuse — the data update lands
  //     before any keystroke could fire `filter*`.
  //   * Fresh cache → do nothing on open; let the first `@` / `/` keystroke
  //     trigger the per-session refresh.
  Future<void> _maybeFreshenFileMentionsOnOpen() async {
    if (_didRefreshFileMentions) return;
    final absolutePath = _resolveProjectAbsolutePath();
    if (absolutePath == null) return;
    final age =
        await actions.FileMentionsCache.instance.ageOnDisk(absolutePath);
    if (age == null) {
      // No cache — load eagerly so the first `@` has data without paying
      // the network + isolate-decode cost mid-interaction.
      _didRefreshFileMentions = true;
      await loadFileMentions();
      return;
    }
    if (age > _cacheStaleThreshold) {
      _didRefreshFileMentions = true;
      await _refreshFileMentionsSilently();
    }
  }

  Future<void> _maybeFreshenSlashCommandsOnOpen() async {
    if (_didRefreshSlashCommands) return;
    final age =
        await actions.SlashCommandsCache.instance.ageOnDisk(slashCommandAgentKey);
    if (age == null) {
      // No cache — loadSlashCommands (called separately on chat open) will
      // fetch. Mark refreshed so first `/` doesn't fire a duplicate.
      _didRefreshSlashCommands = true;
      return;
    }
    if (age > _cacheStaleThreshold) {
      _didRefreshSlashCommands = true;
      await refreshSlashCommandsSilently();
    }
  }

  // Background fetch that updates [fileMentions] and the disk cache *without*
  // firing `onStateChanged`. The next user keystroke runs `filterFileMentions`
  // against the freshened list, so the popup picks up new entries as part of
  // a natural interaction rather than shifting under the user's eyes.
  Future<void> _refreshFileMentionsSilently() async {
    final absolutePath = _resolveProjectAbsolutePath();
    if (absolutePath == null) return;
    try {
      final knownHash =
          await actions.FileMentionsCache.instance.readHash(absolutePath);
      final result = await actions.fetchFileMentions(
        projectPath: absolutePath,
        machineId: _resolveMachineId(),
        knownHash: knownHash,
      );
      if (result.unchanged) {
        // Nothing moved on disk. Reset the staleness clock so the next chat
        // open doesn't re-ask, and skip rewriting an identical list.
        unawaited(actions.FileMentionsCache.instance
            .touch(absolutePath, hash: result.hash));
        return;
      }
      final files = result.files ?? const <String>[];
      if (files.isNotEmpty) {
        fileMentions = files;
        // FileMentionsCache.write also bumps the file's mtime, which is what
        // ageOnDisk reads on the next chat open.
        unawaited(actions.FileMentionsCache.instance
            .write(absolutePath, files, hash: result.hash));
      }
    } catch (e) {
      debugPrint('Error refreshing file mentions: $e');
    }
  }

  // Lazy hook from FileMentionMixin: invoked the first time the user types
  // `@`. If the cache existed at chat-open time we skipped the eager fetch
  // here; this is where we populate from disk-or-network. Subsequent `@`
  // keystrokes within the same chat session trigger a silent background
  // refresh exactly once.
  @override
  Future<void> ensureFileMentionsLoaded() async {
    if (isLoadingFileMentions) return;
    if (fileMentions.isEmpty) {
      await loadFileMentions();
      _didRefreshFileMentions = true;
      return;
    }
    if (!_didRefreshFileMentions) {
      _didRefreshFileMentions = true;
      unawaited(_refreshFileMentionsSilently());
    }
  }

  // Load available file mentions for this instance.
  //
  // Resolution order: in-memory → disk cache → network fetch. The disk read
  // and JSON parse both run off-isolate (via FileMentionsCache.read and
  // apiGetFileMentions respectively), so this can be invoked on the UI path
  // without blocking the chat scroll. Calls while a load is already in
  // flight are deduped via [isLoadingFileMentions].
  Future<void> loadFileMentions() async {
    if (instanceId == null || isLoadingFileMentions) return;
    if (fileMentions.isNotEmpty) return; // memory cache hit

    isLoadingFileMentions = true;

    try {
      final absolutePath = _resolveProjectAbsolutePath();
      if (absolutePath == null) {
        debugPrint('No project path available for file mentions');
        fileMentions = [];
        return;
      }

      // Disk cache: previously-fetched lists persist across sessions and
      // avoid the ~1–2 MB network fetch + JSON decode on every chat open.
      final cached =
          await actions.FileMentionsCache.instance.read(absolutePath);
      if (cached != null && cached.isNotEmpty) {
        fileMentions = cached;
        debugPrint('Loaded ${fileMentions.length} file mentions from disk cache for: $absolutePath');
        return;
      }

      debugPrint('Loading file mentions for: $absolutePath');
      // No `knownHash` here: the disk cache missed, so there is nothing to
      // compare against and `unchanged` would leave us with an empty list.
      final result = await actions.fetchFileMentions(
        projectPath: absolutePath,
        machineId: _resolveMachineId(),
      );
      final files = result.files ?? const <String>[];
      fileMentions = files;
      debugPrint('Loaded ${fileMentions.length} file mentions '
          'from ${result.source.name}');
      if (files.isNotEmpty) {
        unawaited(actions.FileMentionsCache.instance
            .write(absolutePath, files, hash: result.hash));
      }
    } catch (e) {
      debugPrint('Error loading file mentions: $e');
      fileMentions = [];
    } finally {
      isLoadingFileMentions = false;
      // Re-run filtering against the current draft. Without this, the first
      // `@` of a session (typed or inserted by the Add-to-chat sheet) calls
      // filterFileMentions while fileMentions is still empty and bails with
      // show:false — the panel then can't surface until the user types
      // another character. Mirrors loadSlashCommands which already re-filters
      // after every load path.
      filterFileMentions(fileMentionTextController.text);
      onStateChanged?.call();
    }
  }

  // Filter out projectRoot from absolute paths in content
  String filterProjectRootFromContent(String content) {
    if (projectRoot == null || projectRoot!.isEmpty) return content;

    // Replace occurrences of projectRoot with empty string or relative path indicator
    final filteredContent = content.replaceAllMapped(
      RegExp('${RegExp.escape(projectRoot!)}/([^\\s`]+)'),
      (match) {
        final relativePath = match.group(1);
        return relativePath ?? match.group(0)!;
      },
    );

    return filteredContent;
  }

  String sanitizeMessageContent(String content) {
    if (content.isEmpty) {
      return '';
    }

    if (_containsControlSetting(content, 'ask_user_question')) {
      return '';
    }

    var sanitized = content;

    // Strip local command tags while keeping stdout content
    sanitized = sanitized.replaceAllMapped(
      RegExp(r'<local-command-stdout>([\s\S]*?)</local-command-stdout>',
          caseSensitive: false),
      (match) => match.group(1) ?? '',
    );
    sanitized = sanitized.replaceAll(
      RegExp(r'<local-command-stderr>[\s\S]*?</local-command-stderr>',
          caseSensitive: false),
      '',
    );

    // Remove control messages only if they're NOT in code blocks
    sanitized = removePatternOutsideCodeBlocks(sanitized, _controlCommandJsonRegex);

    sanitized = sanitized.replaceAll(_waitingForInputMessage, '');
    // Replace multiple spaces/tabs ONLY outside code blocks to preserve code formatting
    sanitized = replacePatternOutsideCodeBlocks(sanitized, RegExp(r'[ \t]{2,}'), ' ');
    sanitized = sanitized.replaceAll(RegExp(r'\n{3,}'), '\n\n');
    return sanitized.trim();
  }

  bool _containsControlSetting(String content, String setting) {
    final matches = _controlCommandJsonRegex.allMatches(content);
    for (final match in matches) {
      final snippet = match.group(0);
      final parsed = _parseControlCommand(snippet);
      if (parsed?['setting']?.toString() == setting) {
        return true;
      }
    }
    return false;
  }

  // Load messages for the agent instance
  // If hasCachedData is true, loads cached messages first then refreshes in background
  Future<void> loadMessages({bool hasCachedData = false}) async {
    if (instanceId == null) return;

    hasError = false;
    errorMessage = null;

    // Local welcome demo: never touches the API or WebSocket. Prefer any cached
    // messages so the user's in-demo progress (e.g. a chosen waitlist answer)
    // persists across reopens; otherwise seed the scripted conversation.
    if (isWelcomeDemoInstance(instanceId)) {
      final cached = FFAppState().getCachedMessages(instanceId!);
      messages = cached.isNotEmpty ? cached : buildWelcomeDemoMessages();
      FFAppState().setCachedMessages(instanceId!, messages);
      isLoadingMessages = false;
      onStateChanged?.call();
      // No scroll-to-bottom: the demo opens at the top so the user reads the
      // intro from the beginning (the widget calls scrollToTop on open).
      return;
    }

    // If we have cached data, load it first and show it immediately
    if (hasCachedData) {
      final cachedMessages = FFAppState().getCachedMessages(instanceId!);
      if (cachedMessages.isNotEmpty) {
        messages = cachedMessages;
        _refreshLatestWebPreviewUrl();
        isLoadingMessages = false;
        onStateChanged?.call();

        _hydrateControlSettingsFromMessages();
      }
    }

    try {
      // Load instance details first to resolve the project root
      await _loadInstanceDetails();

      final result = await actions.apiGetInstanceMessages(instanceId!);
      final hadCachedMessages = messages.isNotEmpty;
      _mergeMessages(result);
      _backfillRequiresUserInput();
      _refreshLatestWebPreviewUrl();
      hasError = false;

      // Cache the messages for next time
      FFAppState().setCachedMessages(instanceId!, messages);

      _hydrateControlSettingsFromMessages();

      onStateChanged?.call();

      // Load slash commands in the background. loadSlashCommands sets the
      // default commands synchronously first, so the `/` menu has fallback
      // suggestions until the network fetch returns. If a disk cache exists
      // it's used; if not, network. Either way we follow up with a
      // staleness check so day-old caches are refreshed transparently.
      unawaited(loadSlashCommands());
      unawaited(_maybeFreshenSlashCommandsOnOpen());

      // File mentions: if no disk cache → load eagerly so first `@` is
      // instant. If cache > 1 day → silent background refresh. Otherwise
      // defer to ensureFileMentionsLoaded (fires on first `@`).
      unawaited(_maybeFreshenFileMentionsOnOpen());

      if (!hadCachedMessages) {
        scrollToBottom();
      }

      // Start streaming after initial load
      if (!isStreamingActive) {
        _startMessageStreaming();
      }
    } catch (e) {
      hasError = true;
      errorMessage = tr().chatErrorLoadMessagesFailed;
    } finally {
      isLoadingMessages = false;
    }
  }

  void _mergeMessages(List<dynamic> freshMessages) {
    if (messages.isEmpty) {
      messages = freshMessages;
      return;
    }

    final existingById = <dynamic, int>{};
    for (int i = 0; i < messages.length; i++) {
      final id = messages[i]['id'];
      if (id != null) {
        existingById[id] = i;
      }
    }

    for (final fresh in freshMessages) {
      final id = fresh['id'];
      if (id == null) continue;
      int? existingIndex = existingById[id];

      // No id match — fall back to matching an optimistic local entry by
      // content so a fresh reload doesn't duplicate a just-sent user message.
      if (existingIndex == null && fresh is Map) {
        final freshSender = fresh['sender_type']?.toString().toLowerCase();
        final freshContent = fresh['content']?.toString();
        if (freshSender == 'user' && freshContent != null) {
          for (int i = 0; i < messages.length; i++) {
            final m = messages[i];
            if (m is Map &&
                m['_optimistic'] == true &&
                m['sender_type']?.toString().toLowerCase() == 'user' &&
                m['content']?.toString() == freshContent) {
              existingIndex = i;
              break;
            }
          }
        }
      }

      if (existingIndex != null) {
        messages[existingIndex] = fresh;
        existingById[id] = existingIndex;
      } else {
        messages.add(fresh);
        existingById[id] = messages.length - 1;
      }
    }
  }

  // Attach to the shared user-scoped WebSocket for this session's messages.
  // VicoaWsClient owns the connection and its reconnect loop; this model just
  // subscribes and registers the catch-up watermark (§2.6).
  void _startMessageStreaming() {
    if (instanceId == null || isStreamingActive) return;
    // A closed session (terminal, paused, or stale) is not worth streaming.
    // The status is already known from instanceData; a reload re-evaluates if
    // the session later reactivates.
    if (functions.isSessionClosed(instanceData?['status']?.toString())) {
      return;
    }

    isStreamingActive = true;
    final client = actions.VicoaWsClient.instance;
    client.retain();
    _streamSubscription =
        client.messageEventsFor(instanceId!).listen(_handleWsEvent);
    // Catch-up fetches from the newest message the REST load already rendered.
    client.watchInstance(instanceId!, watermark: _newestMessageCreatedAt());
  }

  // Newest message `created_at` — the reconnect catch-up watermark (§2.6).
  String? _newestMessageCreatedAt() {
    String? newest;
    for (final m in messages) {
      if (m is Map) {
        final createdAt = m['created_at'];
        if (createdAt is String &&
            (newest == null || createdAt.compareTo(newest) > 0)) {
          newest = createdAt;
        }
      }
    }
    return newest;
  }

  void _handleWsEvent(Map<String, dynamic> event) {
    final eventType = event['event']?.toString() ?? '';
    final data = event['data'];

    switch (eventType) {
      case 'connected':
        _clearRealtimeDegraded();
        break;

      case 'disconnected':
        _onSseDisconnected();
        break;

      case 'status_update':
        if (data is Map) _handleStatusUpdate(data);
        break;

      case 'instance_updated':
        if (data is Map) _handleInstanceUpdated(data);
        break;

      case 'message':
        if (data is Map) _handleMessageUpdate(data);
        break;

      case 'message_metadata_update':
        if (data is Map) {
          _handleMessageMetadataUpdate(Map<String, dynamic>.from(data));
        }
        break;

      default:
        debugPrint('Unknown WS event type: $eventType');
    }
  }

  // Subset of canonical agent_instances columns that the chat page actually
  // renders. A WS instance-update changes outside this set (notably
  // `last_heartbeat_at` and `updated_at`, both touched on every heartbeat,
  // ~30s) silently updates instanceData but does NOT trigger a rebuild —
  // otherwise the whole chat page would repaint every heartbeat. Keep this
  // in sync with the fields read by agent_chat_widget.dart and
  // _AgentConfigPill.
  static const Set<String> _uiVisibleInstanceFields = {
    'session_config', // gear-pill sheet
    'name', // header title
    'project', // header subtitle path
    'home_dir', // resolves project path expansion (rendered in subtitle)
    'pinned_at', // pin icon
    'has_git_changes', // git-changes indicator
    'instance_metadata', // usage blob (context window + rate limits) chip
  };

  // Merge a canonical instance row from a WS instance-update frame into
  // instanceData. Lets the gear-pill sheet show the latest session_config
  // the moment the wrapper PATCHes it (e.g., after Shift+Tab in TUI) —
  // without requiring the user to close + reopen the chat page.
  //
  // The broadcast envelope (§2.4 in plans/websocket-migration.md) carries
  // only canonical agent_instances columns; presentation fields like
  // agent_type_name are joined client-side, so we MERGE rather than
  // replace to keep those intact.
  void _handleInstanceUpdated(Map data) {
    if (instanceData == null) return;
    bool uiChanged = false;
    for (final entry in data.entries) {
      final key = entry.key.toString();
      // 'status' is owned by _handleStatusUpdate (with its no-op suppression).
      if (key == 'status' || key == 't' || key == 'id') continue;
      if (instanceData![key] != entry.value) {
        instanceData![key] = entry.value;
        if (_uiVisibleInstanceFields.contains(key)) uiChanged = true;
      }
    }
    if (uiChanged) onStateChanged?.call();
  }

  // Schedule the "Reconnecting…" banner — only flips visible after the
  // debounce so transient blips don't flash a banner on screen.
  void _onSseDisconnected() {
    // SSE drops when the session ends — that's the expected terminal state,
    // not a connection problem, so don't show the reconnecting banner.
    if (functions.isSessionClosed(instanceData?['status']?.toString())) return;
    if (realtimeDegraded || _realtimeDegradedDebounceTimer != null) return;
    _realtimeDegradedDebounceTimer = Timer(_realtimeDegradedDebounce, () {
      _realtimeDegradedDebounceTimer = null;
      // Skip if streaming resumed or the session closed during the window.
      if (isStreamingActive ||
          functions.isSessionClosed(instanceData?['status']?.toString())) {
        return;
      }
      realtimeDegraded = true;
      onStateChanged?.call();
    });
  }

  // Clear the banner the moment we re-establish — no debounce on the way down.
  void _clearRealtimeDegraded() {
    _realtimeDegradedDebounceTimer?.cancel();
    _realtimeDegradedDebounceTimer = null;
    if (!realtimeDegraded) return;
    realtimeDegraded = false;
    onStateChanged?.call();
  }

  void _addOptimisticMessage(
    String optimisticId,
    String content, {
    List<PendingAttachment> attachments = const [],
  }) {
    messages.add(<String, dynamic>{
      'id': optimisticId,
      'content': content,
      'sender_type': 'user',
      'created_at': DateTime.now().toIso8601String(),
      '_optimistic': true,
      if (attachments.isNotEmpty) ...{
        // Mirror the server's message_metadata.attachments shape so the
        // bubble renders identically before and after the round-trip.
        'message_metadata': <String, dynamic>{
          'attachments': [
            for (final a in attachments) {...?a.meta, 'id': a.id},
          ],
        },
        // Local-only hint: render from disk instead of re-downloading what
        // we just uploaded. Stripped implicitly when the WS copy replaces
        // this entry; harmless if it survives in the cache.
        '_local_paths': <String, String>{
          for (final a in attachments)
            if (a.id != null) a.id!: a.localPath,
        },
      },
    });
    if (instanceId != null) {
      FFAppState().setCachedMessages(instanceId!, messages);
    }
  }

  void _promoteOptimistic(String optimisticId, dynamic realId) {
    final optimisticIndex = messages.indexWhere((msg) => msg['id'] == optimisticId);
    if (optimisticIndex == -1) return;

    // If SSE delivered the real message before our HTTP POST returned, an entry
    // with realId is already in the list. Drop the optimistic to avoid a
    // duplicate; otherwise rename the optimistic in place.
    final realIndex = realId == null
        ? -1
        : messages.indexWhere((msg) => msg['id'] == realId);
    if (realIndex != -1 && realIndex != optimisticIndex) {
      messages.removeAt(optimisticIndex);
    } else {
      final promoted = Map<String, dynamic>.from(messages[optimisticIndex] as Map);
      promoted['id'] = realId;
      promoted.remove('_optimistic');
      messages[optimisticIndex] = promoted;
    }

    if (instanceId != null) {
      FFAppState().setCachedMessages(instanceId!, messages);
    }
    onStateChanged?.call();
  }

  void _removeOptimistic(String optimisticId) {
    final index = messages.indexWhere((msg) => msg['id'] == optimisticId);
    if (index != -1) {
      messages.removeAt(index);
      if (instanceId != null) {
        FFAppState().setCachedMessages(instanceId!, messages);
      }
      onStateChanged?.call();
    }
  }

  // Append a message to the local welcome demo conversation. Demo-only — no
  // network, no optimistic/promote bookkeeping. Persists to the per-instance
  // cache so the appended message survives a chat reopen.
  void appendDemoMessage(Map<String, dynamic> message) {
    if (!isWelcomeDemoInstance(instanceId)) return;
    // De-dupe by id so re-tapping a CTA button doesn't stack duplicates.
    final id = message['id'];
    if (id != null && messages.any((m) => m is Map && m['id'] == id)) {
      return;
    }
    messages.add(message);
    if (instanceId != null) {
      FFAppState().setCachedMessages(instanceId!, messages);
    }
    onStateChanged?.call();
    scrollToBottom(animate: true);
  }

  /// Picks an image (library or camera) and shows it in the pending strip
  /// immediately. Upload happens at SEND time (sendMessage), not here —
  /// picking stays instant and bytes only move when the user commits. The
  /// picker downsizes client-side; the backend re-encodes (EXIF strip,
  /// 2048px cap) as the safety net.
  Future<void> pickImageFromLibrary() => _pickImage(ImageSource.gallery);
  Future<void> takePhotoAndAttach() => _pickImage(ImageSource.camera);

  Future<void> _pickImage(ImageSource source) async {
    if (instanceId == null) return;
    try {
      final picked = await ImagePicker().pickImage(
        source: source,
        maxWidth: 2048,
        maxHeight: 2048,
        imageQuality: 85,
      );
      if (picked == null) return;
      pendingAttachments.add(PendingAttachment(localPath: picked.path));
      _notifyAttachmentsChanged();
    } catch (e) {
      debugPrint('Error picking image: $e');
    }
  }

  /// Picks arbitrary files (any type) and shows them in the pending strip.
  /// Like image picks, upload is deferred to send time. The original filename
  /// is carried so the backend resolves the correct type; the backend enforces
  /// the size cap and the executable blocklist.
  Future<void> pickFilesAndAttach() async {
    if (instanceId == null) return;
    try {
      final result =
          await FilePicker.platform.pickFiles(allowMultiple: true, withData: false);
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
      _notifyAttachmentsChanged();
    } catch (e) {
      debugPrint('Error picking files: $e');
    }
  }

  Future<void> _uploadPendingAttachment(PendingAttachment attachment) async {
    attachment.uploading = true;
    attachment.failed = false;
    _notifyAttachmentsChanged();
    final result = await actions.apiUploadAttachment(
        instanceId!, attachment.localPath, attachment.filename);
    if (result is Map && result['id'] != null) {
      attachment.id = result['id'] as String;
      attachment.meta = Map<String, dynamic>.from(result);
    } else {
      attachment.failed = true;
    }
    attachment.uploading = false;
    _notifyAttachmentsChanged();
  }

  Future<void> retryAttachmentUpload(PendingAttachment attachment) =>
      _uploadPendingAttachment(attachment);

  void removePendingAttachment(PendingAttachment attachment) {
    pendingAttachments.remove(attachment);
    _notifyAttachmentsChanged();
  }

  // Send message to agent
  Future<void> sendMessage(BuildContext context, String content, {bool isOptionClick = false}) async {
    if (instanceId == null ||
        (content.trim().isEmpty && pendingAttachments.isEmpty)) {
      return;
    }

    // Welcome demo is a local, read-only preview — there's no agent to send to.
    // Echo the user's text, then nudge them toward setting up a real session.
    if (isWelcomeDemoInstance(instanceId)) {
      final stamp = DateTime.now().millisecondsSinceEpoch;
      appendDemoMessage(<String, dynamic>{
        'id': 'demo-user-$stamp',
        'content': content,
        'sender_type': 'user',
        'created_at': DateTime.now().toIso8601String(),
      });
      if (!isOptionClick) {
        messageController.clear();
        clearDraftMessage();
        filterSlashCommands('');
        filterFileMentions('');
      }
      appendDemoMessage(<String, dynamic>{
        'id': 'demo-nudge-$stamp',
        'content':
            "This is just a sample chat 🙂 To start a real session, set up the "
                "Vicoa CLI on your computer using the buttons above.",
        'sender_type': 'assistant',
        'created_at': DateTime.now().toIso8601String(),
        'message_metadata': <String, dynamic>{kWelcomeDemoMetadataKey: true},
      });
      return;
    }

    // Check credits/subscription before showing the message — avoids a flash
    // if the user hits the paywall and the send is aborted.
    final hasActiveSubscription = await actions.hasActiveSubscription();

    if (!hasActiveSubscription) {
      const creditsNeeded = 1;
      final currentCredits = FFAppState().credit.balance;

      if (currentCredits < creditsNeeded) {
        FocusManager.instance.primaryFocus?.unfocus();

        if (context.mounted) {
          await showModalBottomSheet(
            context: context,
            backgroundColor: Colors.transparent,
            enableDrag: false,
            builder: (context) {
              return NoCreditSheetWidget(
                paywall: 'agent_chat',
                creditsNeeded: creditsNeeded,
              );
            },
          );
        }
        isSendingMessage = false;
        return;
      }

      if (context.mounted) {
        await local_actions.useCredit(
          context,
          usedCredit: creditsNeeded,
          name: 'Agent Chat Message',
        );
      }
    }

    isSendingMessage = true;
    isWaitingForAgentResponse = true;
    onStateChanged?.call();

    // Send-time upload: picked images move to S3 only now, in parallel. The
    // strip thumbnails show spinners while this runs; failures stay in the
    // strip (with the retry overlay) instead of riding the message.
    final needUpload = pendingAttachments.where((a) => a.id == null).toList();
    if (needUpload.isNotEmpty) {
      await Future.wait(needUpload.map(_uploadPendingAttachment));
    }
    final sendAttachments =
        pendingAttachments.where((a) => a.id != null).toList();
    if (content.trim().isEmpty && sendAttachments.isEmpty) {
      // Image-only send and every upload failed — nothing to post.
      isSendingMessage = false;
      isWaitingForAgentResponse = false;
      onStateChanged?.call();
      return;
    }
    pendingAttachments.removeWhere((a) => a.id != null);
    pendingAttachmentsRevision++;
    final attachmentIds = [for (final a in sendAttachments) a.id!];

    // Show the message immediately — no need to wait for the round-trip.
    final optimisticId = 'opt_${DateTime.now().millisecondsSinceEpoch}';
    _addOptimisticMessage(optimisticId, content, attachments: sendAttachments);
    if (!isOptionClick) {
      messageController.clear();
      clearDraftMessage();
      // Clearing the controller doesn't fire onChanged, so any open slash or
      // file-mention overlay would linger over the chat after send.
      filterSlashCommands('');
      filterFileMentions('');
    }
    onStateChanged?.call();
    scrollToBottom();

    bool sentOk = false;
    try {
      final result = await actions.apiChatWithAgent(
        instanceId!,
        content,
        attachmentIds: attachmentIds,
      );
      if (result != null) {
        // Swap the optimistic ID for the real server-assigned ID so that when
        // the SSE delivery arrives with the same ID, _handleMessageUpdate's
        // dedup logic finds the existing entry and updates in-place rather than
        // appending a duplicate.
        final realId = result['id'];
        if (realId != null) {
          _promoteOptimistic(optimisticId, realId);
          // Remember option/permission responses by their server id so the
          // queue bar can skip the `queued` (never-consumed) row the backend
          // stamps on them. Bump the metadata revision so the bar recomputes
          // if the queued WS frame already landed.
          if (isOptionClick) {
            optionResponseMessageIds.add(realId.toString());
            messageMetadataRevision++;
          }
        } else {
          _removeOptimistic(optimisticId);
        }
        sentOk = true;
        debugPrint('Message sent successfully');
        // Mark the getting-started checklist's "Send a message" step done
        // instantly (per-account cache, reset on logout). The server's
        // total_user_messages stays the source of truth; this just avoids a
        // one-frame flash of the card on the next home load.
        FFAppState().gettingStartedActivated = true;
        if (!FFAppState().analyticsFlags.hasSentFirstMobileMessage) {
          await posthogCapture('first_mobile_message_sent');
          FFAppState().updateAnalyticsFlags((f) => f.hasSentFirstMobileMessage = true);
        }
      } else {
        debugPrint('Failed to send message. Please try again.');
        _removeOptimistic(optimisticId);
        // The uploads already succeeded server-side — put them back in the
        // strip so a retry doesn't force a re-pick.
        pendingAttachments.addAll(sendAttachments);
        pendingAttachmentsRevision++;
        if (!hasActiveSubscription && context.mounted) {
          await local_actions.grantCredit(
            context,
            creditGranted: 1,
            name: 'Refund: Failed Agent Chat Message',
          );
        }
      }
    } catch (e) {
      debugPrint('Error sending message: $e');
      _removeOptimistic(optimisticId);
      pendingAttachments.addAll(sendAttachments);
      pendingAttachmentsRevision++;
      if (!hasActiveSubscription && context.mounted) {
        await local_actions.grantCredit(
          context,
          creditGranted: 1,
          name: 'Refund: Failed Agent Chat Message',
        );
      }
    } finally {
      // Send button always returns to normal as soon as the POST completes.
      isSendingMessage = false;
      if (!sentOk) {
        // POST failed — vibing has nothing to wait for.
        isWaitingForAgentResponse = false;
        _sendingTimeoutTimer?.cancel();
        _sendingTimeoutTimer = null;
      } else {
        // POST succeeded — keep isWaitingForAgentResponse=true so vibing stays
        // on until the WebSocket confirms the agent is active. Safety net:
        // auto-clear after _sendingTimeout in case the WebSocket never fires.
        _sendingTimeoutTimer?.cancel();
        _sendingTimeoutTimer = Timer(_sendingTimeout, () {
          if (isWaitingForAgentResponse) {
            isWaitingForAgentResponse = false;
            onStateChanged?.call();
          }
        });
      }
    }
  }

  Future<void> requestPermissionModeChange(AgentPermissionMode newMode) async {
    if (instanceId == null) return;
    if (pendingPermissionMode == newMode) return;
    if (permissionMode == newMode) {
      return;
    }

    pendingPermissionMode = newMode;
    onStateChanged?.call();

    final requestMessage = _buildPermissionModeRequestMessage(newMode);

    try {
      await actions.apiChatWithAgent(instanceId!, requestMessage);
    } catch (e) {
      debugPrint('Error updating permission mode: $e');
      pendingPermissionMode = null;
      onStateChanged?.call();
    }
  }

  /// Send a model change to the active wrapper. The wrapper applies it
  /// (Claude TUI: PTY-types `/model <slug>`; Codex TUI: dispatches
  /// Op::OverrideTurnContext via vicoa_integration.rs; both headless: rebuild
  /// session config) and PATCHes session_config so the pill re-renders.
  /// No pending-state mirror today — mobile relies on the WS frame from the
  /// wrapper's PATCH to drive the next render.
  Future<void> requestModelChange(String slug) async {
    if (instanceId == null) return;
    final message = 'Change model to $slug. ${_buildControlMessage('model', slug)}';
    try {
      await actions.apiChatWithAgent(instanceId!, message);
    } catch (e) {
      debugPrint('Error updating model: $e');
    }
  }

  /// Send a reasoning/thinking effort change to the active wrapper. The
  /// wire format uses the unified `effort` setting cross-agent (Q4); each
  /// wrapper maps to its own catalog field (Claude: thinking_effort; Codex:
  /// reasoning_effort) when PATCHing session_config.
  Future<void> requestEffortChange(String slug) async {
    if (instanceId == null) return;
    final message = 'Change effort to $slug. ${_buildControlMessage('effort', slug)}';
    try {
      await actions.apiChatWithAgent(instanceId!, message);
    } catch (e) {
      debugPrint('Error updating effort: $e');
    }
  }

  Future<void> requestOpencodeAgentModeChange(OpencodeAgentMode newMode) async {
    if (instanceId == null) return;
    if (pendingOpencodeAgentMode == newMode) return;
    if (opencodeAgentMode == newMode) {
      return;
    }

    pendingOpencodeAgentMode = newMode;
    onStateChanged?.call();

    final requestMessage = _buildOpencodeAgentModeRequestMessage(newMode);

    try {
      await actions.apiChatWithAgent(instanceId!, requestMessage);
    } catch (e) {
      debugPrint('Error updating OpenCode agent mode: $e');
      pendingOpencodeAgentMode = null;
      onStateChanged?.call();
    }
  }

  Future<void> requestThinkingToggle(bool enabled) async {
    if (instanceId == null) return;
    if (thinkingSettingEnabled != null && thinkingSettingEnabled == enabled) {
      return;
    }

    final previousState = thinkingSettingEnabled;
    thinkingSettingEnabled = enabled;
    onStateChanged?.call();

    final requestMessage = _buildThinkingControlMessage(enabled);

    try {
      await actions.apiChatWithAgent(instanceId!, requestMessage);
    } catch (e) {
      debugPrint('Error updating thinking setting: $e');
      thinkingSettingEnabled = previousState;
      onStateChanged?.call();
    }
  }

  Future<void> sendInterrupt() async {
    if (instanceId == null) return;

    final requestMessage = _buildInterruptControlMessage();

    try {
      await actions.apiChatWithAgent(instanceId!, requestMessage);
      debugPrint('Interrupt sent successfully');
    } catch (e) {
      debugPrint('Error sending interrupt: $e');
    }
  }

  void _hydrateControlSettingsFromMessages() {
    final latestMode = _findLatestPermissionMode(messages);
    if (latestMode != null) {
      permissionMode = latestMode;
      if (pendingPermissionMode == latestMode) {
        pendingPermissionMode = null;
      }
    }

    final latestOpencodeMode = _findLatestOpencodeAgentMode(messages);
    if (latestOpencodeMode != null) {
      opencodeAgentMode = latestOpencodeMode;
      if (pendingOpencodeAgentMode == latestOpencodeMode) {
        pendingOpencodeAgentMode = null;
      }
    }

    final latestThinking = _findLatestThinkingSetting(messages);
    if (latestThinking != null) {
      thinkingSettingEnabled = latestThinking;
    }
  }

  void _applyControlSettingsFromMessage(Map newMessage) {
    final content = newMessage['content']?.toString();
    if (content == null || content.isEmpty) {
      return;
    }

    final derivedMode = _extractPermissionModeFromContent(content);
    if (derivedMode != null) {
      permissionMode = derivedMode;
      if (pendingPermissionMode == derivedMode) {
        pendingPermissionMode = null;
      }
    }

    final derivedOpencodeMode = _extractOpencodeAgentModeFromContent(content);
    if (derivedOpencodeMode != null) {
      opencodeAgentMode = derivedOpencodeMode;
      if (pendingOpencodeAgentMode == derivedOpencodeMode) {
        pendingOpencodeAgentMode = null;
      }
    }

    final thinkingSetting = _extractThinkingSettingFromContent(content);
    if (thinkingSetting != null) {
      thinkingSettingEnabled = thinkingSetting;
    }
  }

  AgentPermissionMode? _findLatestPermissionMode(List<dynamic> messageList) {
    for (int idx = messageList.length - 1; idx >= 0; idx--) {
      final message = messageList[idx];
      if (message is! Map) {
        continue;
      }
      final content = message['content']?.toString();
      if (content == null || content.isEmpty) {
        continue;
      }
      final detected = _extractPermissionModeFromContent(content);
      if (detected != null) {
        return detected;
      }
    }
    return null;
  }

  OpencodeAgentMode? _findLatestOpencodeAgentMode(List<dynamic> messageList) {
    for (int idx = messageList.length - 1; idx >= 0; idx--) {
      final message = messageList[idx];
      if (message is! Map) {
        continue;
      }
      final content = message['content']?.toString();
      if (content == null || content.isEmpty) {
        continue;
      }
      final detected = _extractOpencodeAgentModeFromContent(content);
      if (detected != null) {
        return detected;
      }
    }
    return null;
  }

  bool? _findLatestThinkingSetting(List<dynamic> messageList) {
    for (int idx = messageList.length - 1; idx >= 0; idx--) {
      final message = messageList[idx];
      if (message is! Map) {
        continue;
      }
      final content = message['content']?.toString();
      if (content == null || content.isEmpty) {
        continue;
      }
      final detected = _extractThinkingSettingFromContent(content);
      if (detected != null) {
        return detected;
      }
    }
    return null;
  }

  AgentPermissionMode? _extractPermissionModeFromContent(String content) {
    final detected = functions.extractPermissionModeFromContent(content);
    if (detected == null) {
      return null;
    }
    switch (detected) {
      case 'default':
        return AgentPermissionMode.defaultMode;
      case 'plan':
        return AgentPermissionMode.planMode;
      case 'auto':
        return AgentPermissionMode.auto;
      case 'acceptEdits':
        return AgentPermissionMode.acceptEdits;
      case 'bypassPermissions':
        return AgentPermissionMode.bypassPermissions;
      default:
        return null;
    }
  }

  OpencodeAgentMode? _extractOpencodeAgentModeFromContent(String content) {
    final controlValue = _extractControlSettingValue(content, 'agent_type');
    if (controlValue == null) {
      return null;
    }

    switch (controlValue.toLowerCase()) {
      case 'build':
        return OpencodeAgentMode.build;
      case 'plan':
        return OpencodeAgentMode.plan;
      default:
        return null;
    }
  }

  bool? _extractThinkingSettingFromContent(String content) {
    final controlValue = _extractControlSettingValue(content, 'thinking');
    if (controlValue == null) {
      return null;
    }

    final normalized = controlValue.toLowerCase();
    if (normalized == 'on') return true;
    if (normalized == 'off') return false;
    return null;
  }

  String? _extractControlSettingValue(String content, String setting) {
    final matches = _controlCommandJsonRegex.allMatches(content);
    for (final match in matches) {
      final snippet = match.group(0);
      final parsed = _parseControlCommand(snippet);
      final parsedSetting = parsed?['setting']?.toString();
      final parsedValue = parsed?['value'];
      if (parsedSetting == setting && parsedValue is String) {
        return parsedValue;
      }
    }
    return null;
  }

  Map<String, dynamic>? _parseControlCommand(String? value) {
    if (value == null || value.isEmpty) {
      return null;
    }

    try {
      final parsed = jsonDecode(value);
      if (parsed is Map && parsed['type'] == 'control') {
        return Map<String, dynamic>.from(parsed);
      }
    } catch (e) {
      debugPrint('Failed to parse control command: $e');
    }
    return null;
  }

  AgentPermissionMode? _permissionModeFromValue(String raw) {
    final normalized = raw.toLowerCase();
    for (final mode in AgentPermissionMode.values) {
      final controlValueNormalized = mode.controlValue.toLowerCase();
      if (controlValueNormalized == normalized ||
          mode.apiValue.toLowerCase() == normalized) {
        return mode;
      }
    }
    return null;
  }

  String _buildPermissionModeRequestMessage(AgentPermissionMode mode) {
    final label = _getPermissionModeLabel(mode);
    return 'Change the permission mode to $label. ${_buildControlMessage('permission_mode', mode.controlValue)}';
  }

  String _buildOpencodeAgentModeRequestMessage(OpencodeAgentMode mode) {
    final humanReadable = 'Switch agent to ${mode.apiValue}.';
    return '$humanReadable ${_buildControlMessage('agent_type', mode.apiValue)}';
  }

  String _buildThinkingControlMessage(bool enabled) {
    final humanReadable = enabled ? 'Turn thinking on.' : 'Turn thinking off.';
    final value = enabled ? 'on' : 'off';
    return '$humanReadable ${_buildControlMessage('thinking', value)}';
  }

  String _buildInterruptControlMessage() {
    const humanReadable = 'Stop current task.';
    return '$humanReadable ${jsonEncode({
          'type': 'control',
          'setting': 'interrupt'
        })}';
  }

  String _buildControlMessage(String setting, String value) {
    return jsonEncode({'type': 'control', 'setting': setting, 'value': value});
  }

  String _buildAskUserQuestionControlMessage(String action, [Map<String, dynamic>? payload]) {
    final value = action == 'submit' && payload != null
        ? 'submit:${_encodeAskUserQuestionPayload(payload)}'
        : 'cancel';
    final humanReadable = action == 'submit'
        ? 'Submit AskUserQuestion answers.'
        : 'Cancel AskUserQuestion prompt.';
    return '$humanReadable ${_buildControlMessage('ask_user_question', value)}';
  }

  String _encodeAskUserQuestionPayload(Map<String, dynamic> payload) {
    final jsonString = jsonEncode(payload);
    final bytes = utf8.encode(jsonString);
    final encoded = base64UrlEncode(bytes);
    return encoded.replaceAll('=', '');
  }

  String _buildAskUserQuestionSummaryContent(List<Map<String, String>>? displayAnswers) {
    if (displayAnswers == null || displayAnswers.isEmpty) return '';
    final blocks = <String>[];
    for (final answer in displayAnswers) {
      final question = (answer['question'] ?? '').trim();
      final header = (answer['header'] ?? '').trim();
      final prompt = question.isNotEmpty ? question : header;
      if (prompt.isEmpty) continue;
      final labelRaw = (answer['label'] ?? '').trim();
      final label = labelRaw.isEmpty ? '(empty)' : labelRaw;
      blocks.add('Q: $prompt\nA: $label');
    }
    return blocks.join('\n\n');
  }

  String _buildAskUserQuestionSummaryPersistMessage({
    required String messageId,
    required List<Map<String, dynamic>> answers,
    List<Map<String, String>>? displayAnswers,
  }) {
    final summaryContent = _buildAskUserQuestionSummaryContent(displayAnswers);
    if (summaryContent.isEmpty) return '';

    final payload = {
      'message_id': messageId,
      'answers': answers,
      if (displayAnswers != null) 'display_answers': displayAnswers,
    };
    final encoded = base64UrlEncode(utf8.encode(jsonEncode(payload))).replaceAll('=', '');
    final control = jsonEncode({
      'type': 'control',
      'action': 'persist_only',
      'kind': 'ask_user_question_summary',
      'value': 'v1:$encoded',
    });
    return '$summaryContent\n$control';
  }

  String _buildAskUserQuestionCancelPersistMessage() {
    final control = jsonEncode({
      'type': 'control',
      'action': 'persist_only',
    });
    return 'Declined to answer\n$control';
  }

  Future<void> submitAskUserQuestion({
    required String messageId,
    required List<Map<String, dynamic>> answers,
    List<Map<String, String>>? displayAnswers,
  }) async {
    if (instanceId == null) return;
    final payload = {
      'message_id': messageId,
      'answers': answers,
      if (displayAnswers != null) 'display_answers': displayAnswers,
    };
    final requestMessage = _buildAskUserQuestionControlMessage('submit', payload);
    final summaryPersistMessage = _buildAskUserQuestionSummaryPersistMessage(
      messageId: messageId,
      answers: answers,
      displayAnswers: displayAnswers,
    );

    final summaryContent = _buildAskUserQuestionSummaryContent(displayAnswers);
    String? optimisticId;
    if (summaryContent.isNotEmpty) {
      optimisticId = 'opt_ask_${DateTime.now().millisecondsSinceEpoch}';
      _addOptimisticMessage(optimisticId, summaryContent);
      onStateChanged?.call();
      scrollToBottom();
    }

    try {
      if (summaryPersistMessage.isNotEmpty) {
        final result = await actions.apiChatWithAgent(instanceId!, summaryPersistMessage);
        if (optimisticId != null) {
          final realId = result?['id'];
          if (realId != null) {
            _promoteOptimistic(optimisticId, realId);
          } else {
            _removeOptimistic(optimisticId);
          }
          optimisticId = null;
        }
      }
      await actions.apiChatWithAgent(instanceId!, requestMessage);
    } catch (e) {
      debugPrint('Error submitting AskUserQuestion answers: $e');
      if (optimisticId != null) {
        _removeOptimistic(optimisticId);
      }
    }
  }

  Future<void> cancelAskUserQuestion() async {
    if (instanceId == null) return;
    final requestMessage = _buildAskUserQuestionControlMessage('cancel');
    final persistMessage = _buildAskUserQuestionCancelPersistMessage();

    final optimisticId = 'opt_cancel_${DateTime.now().millisecondsSinceEpoch}';
    _addOptimisticMessage(optimisticId, 'Declined to answer');
    onStateChanged?.call();
    scrollToBottom();

    try {
      final result = await actions.apiChatWithAgent(instanceId!, persistMessage);
      final realId = result?['id'];
      if (realId != null) {
        _promoteOptimistic(optimisticId, realId);
      } else {
        _removeOptimistic(optimisticId);
      }
      await actions.apiChatWithAgent(instanceId!, requestMessage);
    } catch (e) {
      debugPrint('Error cancelling AskUserQuestion: $e');
      _removeOptimistic(optimisticId);
    }
  }

  String _getPermissionModeLabel(AgentPermissionMode mode) {
    switch (mode) {
      case AgentPermissionMode.defaultMode:
        return 'default mode';
      case AgentPermissionMode.planMode:
        return 'plan mode';
      case AgentPermissionMode.auto:
        return 'auto mode';
      case AgentPermissionMode.acceptEdits:
        return 'accept edits';
      case AgentPermissionMode.bypassPermissions:
        return 'bypass permissions';
    }
  }

  void scrollToBottom({bool animate = false}) {
    if (onScrollToBottomRequested != null) {
      onScrollToBottomRequested!(animate: animate);
      return;
    }

    void performScroll() {
      if (!itemScrollController.isAttached || messages.isEmpty) {
        return;
      }

      final targetIndex = messages.length - 1;
      if (targetIndex < 0) {
        return;
      }

      if (animate) {
        itemScrollController.scrollTo(
          index: targetIndex,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          alignment: 1.0,
        );
      } else {
        itemScrollController.jumpTo(
          index: targetIndex,
          alignment: 1.0,
        );
      }
    }

    if (itemScrollController.isAttached) {
      performScroll();
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) => performScroll());
    }
  }

  void scrollToTop({bool animate = true}) {
    void performScroll() {
      if (!itemScrollController.isAttached || messages.isEmpty) {
        return;
      }

      if (animate) {
        itemScrollController.scrollTo(
          index: 0,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeInOut,
          alignment: 0.0,
        );
      } else {
        // Place the list at the top instantly — no visible scroll motion.
        itemScrollController.jumpTo(index: 0, alignment: 0.0);
      }
    }

    if (itemScrollController.isAttached) {
      performScroll();
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) => performScroll());
    }
  }

  void _backfillRequiresUserInput() {
    for (final msg in messages) {
      if (msg is! Map) continue;
      final sender = msg['sender_type']?.toString().toLowerCase() ?? '';
      if (sender != 'assistant' && sender != 'agent') continue;
      if (msg['requires_user_input'] == true) continue;
      final content = msg['content']?.toString() ?? '';
      if (content.contains('[OPTIONS]') && content.contains('[/OPTIONS]')) {
        msg['requires_user_input'] = true;
      }
    }
  }

  void _markLastAgentMessageRequiresInput() {
    for (int i = messages.length - 1; i >= 0; i--) {
      final msg = messages[i];
      if (msg is! Map) continue;
      final sender = msg['sender_type']?.toString().toLowerCase() ?? '';
      if (sender == 'assistant' || sender == 'agent') {
        if (msg['requires_user_input'] != true) {
          msg['requires_user_input'] = true;
          onStateChanged?.call();
        }
        return;
      }
    }
  }

  // Handle status update events from stream.
  // The vibing indicator is derived from instanceData['status'] in the widget,
  // so updating the status and notifying listeners is all we need here.
  void _handleStatusUpdate(Map data) {
    final status = data['status']?.toString().toUpperCase() ?? '';
    final oldStatus = instanceData?['status']?.toString().toUpperCase() ?? '';
    // Server may emit instance-update frames at a higher rate than the status
    // actually changes (e.g. heartbeats refresh the row). Suppressing the
    // no-op propagation here keeps a chat scroll from stuttering on every
    // identical-status frame.
    if (status.isNotEmpty && status == oldStatus) return;

    debugPrint('[ChatModel] WS status_update received: $status (instance=$instanceId)');

    // Any status update from the server means the backend has picked up the
    // message — hand vibing control over to the status-based logic.
    if (isWaitingForAgentResponse) {
      isWaitingForAgentResponse = false;
      _sendingTimeoutTimer?.cancel();
      _sendingTimeoutTimer = null;
    }

    if (instanceData != null) {
      instanceData!['status'] = status;
    }

    // Session reached a terminal state — drop the reconnecting banner since
    // SSE won't reconnect for a closed session.
    if (functions.isSessionClosed(status)) {
      _clearRealtimeDegraded();
    }

    if (status == 'AWAITING_INPUT') {
      _markLastAgentMessageRequiresInput();
    }

    // Let the widget mirror the change to widget.instanceData and FFAppState.
    onStatusUpdate?.call(status);

    onStateChanged?.call();
  }

  // Handle message update events from stream
  static List<dynamic> _messageAttachments(Map? message) {
    final metadata = message?['message_metadata'];
    if (metadata is Map && metadata['attachments'] is List) {
      return metadata['attachments'] as List;
    }
    return const [];
  }

  void _handleMessageUpdate(Map newMessage) {
    // Filter out empty messages — except image-only ones, whose content is
    // empty but whose metadata carries attachments.
    final content = newMessage['content']?.toString().trim() ?? '';
    if (content.isEmpty && _messageAttachments(newMessage).isEmpty) return;

    // Check if this is an agent message
    final senderType = newMessage['sender_type']?.toString().toLowerCase() ?? '';
    final isAgentMessage = senderType == 'assistant' || senderType == 'agent';

    // First agent reply confirms the agent is actively responding — hand vibing
    // control over to the status-based logic (same as _handleStatusUpdate does).
    if (isAgentMessage && isWaitingForAgentResponse) {
      isWaitingForAgentResponse = false;
      _sendingTimeoutTimer?.cancel();
      _sendingTimeoutTimer = null;
    }

    // Ensure requires_user_input is set when OPTIONS are present or status indicates it
    if (isAgentMessage && newMessage['requires_user_input'] != true) {
      final hasOptions = content.contains('[OPTIONS]');
      final currentStatus = instanceData?['status']?.toString().toUpperCase() ?? '';
      if (hasOptions || currentStatus == 'AWAITING_INPUT') {
        newMessage['requires_user_input'] = true;
      }
    }

    // Check if message already exists to avoid duplicates
    final messageId = newMessage['id'];
    int existingIndex = messages.indexWhere((msg) => msg['id'] == messageId);

    // Race: SSE delivered the real message before sendMessage's HTTP POST
    // returned, so the local entry still has its optimistic id. Match it by
    // (sender_type, content, attachment ids) and update in place rather than
    // appending a copy — attachment ids disambiguate image-only messages
    // whose contents are both empty.
    if (existingIndex == -1 && senderType == 'user') {
      final newContent = newMessage['content']?.toString();
      if (newContent != null) {
        final newAttachmentIds = [
          for (final a in _messageAttachments(newMessage))
            if (a is Map) a['id']?.toString(),
        ];
        existingIndex = messages.indexWhere((msg) {
          if (msg is! Map ||
              msg['_optimistic'] != true ||
              msg['sender_type']?.toString().toLowerCase() != 'user' ||
              msg['content']?.toString() != newContent) {
            return false;
          }
          final existingIds = [
            for (final a in _messageAttachments(msg))
              if (a is Map) a['id']?.toString(),
          ];
          return listEquals(existingIds, newAttachmentIds);
        });
      }
    }

    if (existingIndex == -1) {
      // New message - add to list
      messages.add(newMessage);
      scrollToBottom();
    } else {
      // Update existing message; keep the local-file render hint so the
      // image bubble doesn't flash from disk to network after the echo.
      final existing = messages[existingIndex];
      if (existing is Map && existing['_local_paths'] != null) {
        newMessage['_local_paths'] = existing['_local_paths'];
      }
      messages[existingIndex] = newMessage;
    }

    _refreshLatestWebPreviewUrl();

    _applyControlSettingsFromMessage(newMessage);

    // Cache messages after update
    if (instanceId != null) {
      FFAppState().setCachedMessages(instanceId!, messages);
    }

    // Trigger UI update
    onStateChanged?.call();
  }

  // Patches `message_metadata` on an existing message from a
  // `message-update` WS frame (websocket-migration plan). Unlike
  // _handleMessageUpdate (the `new-message` append-or-replace path), this
  // NEVER appends a message: the frame only carries an id + the new
  // metadata, not a full row, so an id that isn't already in `messages` is
  // silently dropped rather than inserted as a partial message. The find +
  // patch logic itself is the pure, unit-tested
  // `ws_protocol.applyMessageMetadataUpdate`.
  void _handleMessageMetadataUpdate(Map<String, dynamic> body) {
    final patched = ws_protocol.applyMessageMetadataUpdate(messages, body);
    if (!patched) return;

    // Bump so the widget's needsRebuild gate (which otherwise only tracks
    // message count/sending/indicator/permission/attachment state) notices
    // this in-place mutation and actually repaints.
    messageMetadataRevision++;

    // Cache messages after update
    if (instanceId != null) {
      FFAppState().setCachedMessages(instanceId!, messages);
    }

    // Trigger UI update
    onStateChanged?.call();
  }

  // Check if instance can receive messages
  bool canSendMessages() {
    // The welcome demo is a read-only sample — there's no live agent to send
    // to, so the composer stays disabled (interaction is via the CTA buttons).
    if (isWelcomeDemoInstance(instanceId)) {
      return false;
    }

    if (isLoadingMessages) {
      return true;
    }

    final status = instanceData?['status']?.toString().toUpperCase();
    if (status == null || status.isEmpty || status == 'UNKNOWN') {
      return true;
    }

    // Just resumed: allow input even if the row still reads terminal. Reopening
    // is async on the daemon side, so an immediate refetch can still return
    // COMPLETED (seen in the logs as "Instance details: codex, COMPLETED") —
    // and the relaunched agent hasn't heartbeated yet either. This must come
    // BEFORE the closed-status and live_state checks, both of which would
    // otherwise lock the composer on that stale value. Only set by an explicit
    // resume, so it can't enable input on a session the user didn't resume.
    if (_withinResumeGrace) return true;

    if (functions.isSessionClosed(status)) return false;

    // A session whose agent is gone still reports a non-closed status --
    // status is self-reported and freezes when the process dies. Refuse input
    // rather than accept a message nothing will ever read. `unknown` does not
    // block: it covers legacy rows, where refusing would break working
    // sessions on no evidence.
    return !actions.liveStateBlocksSending(liveState);
  }

  // Just-resumed grace, from the shared registry keyed by instance id — the
  // same one the home-list dot consults, so the composer and the dot never
  // disagree about whether a session is reachable.
  bool get _withinResumeGrace => actions.isWithinResumeGrace(instanceId);

  /// Server-derived liveness for this session, or null when absent (older
  /// backend). See shared/database/liveness.py.
  String? get liveState => instanceData?['live_state']?.toString();

  /// Why the composer is refusing input, or null when it isn't.
  String? get liveStateHint {
    if (functions.isSessionClosed(
        instanceData?['status']?.toString().toUpperCase() ?? '')) {
      return null;
    }
    if (_withinResumeGrace) return null;
    return actions.liveStateHint(liveState);
  }

  void _refreshLatestWebPreviewUrl() {
    for (var i = messages.length - 1; i >= 0; i--) {
      final message = messages[i];
      if (message is! Map) {
        continue;
      }
      final content = message['content']?.toString();
      final detectedUrl = _extractLatestWebPreviewUrlFromContent(content);
      if (detectedUrl != null) {
        latestWebPreviewUrl = detectedUrl;
        return;
      }
    }
    latestWebPreviewUrl = null;
  }

  String? _extractLatestWebPreviewUrlFromContent(String? content) {
    if (content == null || content.isEmpty) {
      return null;
    }

    String? latestUrl;
    for (final match in _webUrlRegex.allMatches(content)) {
      final rawUrl = match.group(0);
      if (rawUrl == null || rawUrl.isEmpty) {
        continue;
      }
      final normalizedUrl = _trimTrailingUrlPunctuation(rawUrl);
      if (_isWebPreviewUrl(normalizedUrl)) {
        latestUrl = normalizedUrl;
      }
    }
    return latestUrl;
  }

  bool _isWebPreviewUrl(String url) {
    final normalizedUrl = url.trim().toLowerCase();
    if (normalizedUrl.isEmpty) {
      return false;
    }
    return _webPreviewLinkKeywords.any((keyword) => normalizedUrl.contains(keyword));
  }

  String _trimTrailingUrlPunctuation(String url) {
    var normalizedUrl = url.trim();
    while (normalizedUrl.isNotEmpty &&
        '.,;:!?)]}'.contains(normalizedUrl[normalizedUrl.length - 1])) {
      normalizedUrl = normalizedUrl.substring(0, normalizedUrl.length - 1);
    }
    return normalizedUrl;
  }

  @override
  void dispose() {
    // Detach from the shared WebSocket when disposing.
    if (isStreamingActive && instanceId != null) {
      actions.VicoaWsClient.instance.unwatchInstance(instanceId!);
      actions.VicoaWsClient.instance.release();
    }
    isStreamingActive = false;
    _streamSubscription?.cancel();
    _streamSubscription = null;
    _realtimeDegradedDebounceTimer?.cancel();
    _realtimeDegradedDebounceTimer = null;
    disposeFileMentionMixin();
    _voiceElapsedTimer?.cancel();
    _sendingTimeoutTimer?.cancel();
    _sendingTimeoutTimer = null;
    onScrollToBottomRequested = null;
    messageController.dispose();
    messageFocusNode.dispose();
    voiceTranscriptionProvider.dispose();
  }

  @override
  WidgetClassDebugData toWidgetClassDebugData() => WidgetClassDebugData(
        generatorVariables: debugGeneratorVariables,
        backendQueries: debugBackendQueries,
        componentStates: {
          ...widgetBuilderComponents.map(
            (key, value) => MapEntry(
              key,
              value.toWidgetClassDebugData(),
            ),
          ),
        }.withoutNulls,
        link: 'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=AgentChat',
        searchReference: 'reference=OgpBZ2VudENoYXRQAVoKQWdlbnRDaGF0',
        widgetClassName: 'AgentChat',
      );
}
