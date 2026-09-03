import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/l10n/app_localizations.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/custom_code/widgets/index.dart' as custom_widgets;
import '/custom_code/utils/vibing_messages.dart';
import '/pages/common/session_actions.dart';
import '/pages/message_selection_sheet/message_selection_sheet_widget.dart';
import '/pages/share_options_sheet/share_options_sheet_widget.dart';
import '/pages/agent_chat/components/slash_commands.dart';
import '/pages/agent_chat/components/file_mentions.dart';
import '/constants/slash_commands.dart';
import '/pages/agent_chat/components/chat_input_area.dart';
import '/pages/agent_chat/components/ask_user_question_panel.dart';
import '/pages/agent_chat/components/message_attachments.dart';
import '/pages/agent_chat/components/message_queue_status.dart';
import '/pages/agent_chat/components/queued_messages_bar.dart';
import '/pages/agent_chat/components/session_loading_indicator.dart';
import '/pages/agent_chat/components/chat_block_spacing.dart';
import '/pages/files_screen/file_viewer/file_viewer_widget.dart' show kFileViewerAddToContextKey;
import '/components/welcome_demo/welcome_demo_cta.dart';
import '/components/welcome_demo/welcome_demo_chat_actions.dart';
import '/components/realtime_status_banner/realtime_status_banner_widget.dart';
import '/components/start_ellipsis_text.dart';
import '/custom_code/actions/index.dart' as actions;
import '/constants/welcome_demo_session.dart';
import '/index.dart';
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';
import 'package:share_plus/share_plus.dart';
import 'dart:async';

import 'agent_chat_model.dart';
import 'task_notification_formatter.dart';
export 'agent_chat_model.dart';

class AgentChatWidget extends StatefulWidget {
  const AgentChatWidget({
    super.key,
    required this.instanceId,
    this.instanceData,
    this.hasInitialPrompt = false,
  });

  static String routeName = 'AgentChat';
  static String routePath = '/agentChat/:instanceId';

  final String instanceId;
  final dynamic instanceData;

  /// True when this session was just spawned WITH an initial prompt, so the
  /// agent's first message is imminent. Drives the animated loading empty
  /// state (vs the static idle icon shown for blank/no-prompt sessions).
  final bool hasInitialPrompt;

  @override
  State<AgentChatWidget> createState() => _AgentChatWidgetState();
}

class _AgentChatWidgetState extends State<AgentChatWidget> with RouteAware, TickerProviderStateMixin, WidgetsBindingObserver {
  static const double _trailingSpacerHeight = 16.0;
  static const int _trailingSpacerCount = 1;
  static const Duration _scrollThrottleInterval = Duration(milliseconds: 100);
  late AgentChatModel _model;
  // late List<AnimationController> _dotAnimationControllers;
  // late List<Animation<double>> _dotAnimations;
  
  // Track scroll position and keyboard state
  bool _showScrollToBottomButton = false;
  // One-shot: show the jump-to-bottom button when the welcome demo first opens
  // (it opens at the top). Cleared on first scroll / reaching the bottom.
  bool _showInitialDemoScrollHint = false;
  bool _showNewMessagesBanner = false;
  int? _newMessagesBannerBaseIndex; // Fallback anchor when lastSeenMessageId is absent
  String _currentVibingMessage = '';
  bool _isAskUserQuestionInputFocused = false;
  // Welcome-demo CTA: true while the "set up CLI" email request is in flight.
  bool _demoCtaBusy = false;
  // Persisted AskUserQuestion selections, keyed by messageId, so a panel's
  // chosen options survive a State rebuild (e.g. after it scrolls out of the
  // lazy list once an answer is submitted).
  final Map<String, List<AskUserQuestionAnswer>> _askUserQuestionAnswers = {};
  // Queued-user-message ids with an in-flight cancel request, so the cancel
  // icon can disable/spin instead of firing a second POST on double-tap. The
  // authoritative flip to "cancelled" arrives via the WS message-update patch
  // (see messageMetadataRevision), which clears the queued chip on its own.
  final Set<String> _cancellingMessageIds = {};

  // Ticks whenever the staged-message queue changes (membership flips as the
  // agent consumes/the user cancels, or an in-flight cancel spinner toggles).
  // The open queue sheet rebuilds off this so it stays live while the chat
  // page is behind it. The collapsed bar rebuilds with the page itself.
  final ValueNotifier<int> _queueRevision = ValueNotifier<int>(0);

  final scaffoldKey = GlobalKey<ScaffoldState>();
  final GlobalKey _chatOptionsButtonKey = GlobalKey();
  bool _isChatOptionsMenuOpen = false;

  late final VoidCallback _itemPositionsListenerCallback;
  int _lastKnownMessageCount = 0;
  bool _isAtListBottom = true;
  bool _hasUserInteractedWithList = false;
  bool _forceNextScroll = false;
  bool _shouldAutoScrollAfterRebuild = false;
  bool _pendingAutoScrollToBottom = false;
  Timer? _scrollThrottleTimer;
  bool _isScrollThrottleActive = false;
  bool _isProgrammaticScroll = false; // Track programmatic scrolls to prevent keyboard dismissal

  // Track state to avoid unnecessary rebuilds
  bool _previousSendingState = false;
  bool _previousIndicatorState = false;
  AgentPermissionMode _previousPermissionMode = AgentPermissionMode.defaultMode;
  bool _previousShowSlashCommands = false;
  int _previousSlashCommandCount = 0;
  bool _previousShowFileMentions = false;
  int _previousFileMentionRevision = 0;
  int _previousAttachmentsRevision = 0;
  int _previousMessageMetadataRevision = 0;
  bool _previousVoiceDictationVisible = false;
  String _previousVoiceTranscript = '';
  String? _previousVoiceState;
  int _previousVoiceElapsedSeconds = 0;

  // Cache computed message metadata to avoid O(n²) recalculation on every rebuild
  final Map<int, bool> _isLastAgentMessageCache = {};
  final Map<int, String?> _dateLabelCache = {};
  final Map<int, GlobalKey> _userMessageContainerKeys = {};
  final Map<int, GlobalKey> _userMessageContentKeys = {};
  int? _cachedLastUserMessageIndex;

  // Tool-use groups expanded by the user (collapse-tool-use mode). Keyed by the
  // run's first message id so expansion survives ScrollablePositionedList row
  // recycling — the analog of vicoa-web's list-level expansion state.
  final Set<String> _expandedToolGroups = {};

  // Sub-agent (Task tool) groups expanded by the user. Keyed by the group's
  // `tool_use_id` (see message_metadata.subagent) rather than a message id,
  // since the group's anchor message can change identity across a rebuild
  // but the tool_use_id is stable — and it's shared by every message in the
  // group, unlike a first-message id.
  final Set<String> _expandedSubagentGroups = {};

  // Model-reasoning ("thinking") cards expanded by the user. Keyed by message
  // id — each reasoning message is its own standalone card (not grouped), so
  // the message id is a stable, unique key that survives row recycling.
  final Set<String> _expandedThinkingCards = {};

  // Anchor-at-first-occurrence bucketing of sub-agent messages by tool_use_id,
  // recomputed alongside the other message metadata caches (see
  // _rebuildMessageMetadataCache). Unlike collapse-tool-use's consecutive-run
  // grouping, this must handle parallel sub-agents whose child messages
  // interleave in chat order.
  custom_widgets.SubagentGrouping _subagentGrouping =
      const custom_widgets.SubagentGrouping(
    toolUseIdByIndex: [],
    indicesById: {},
  );

  // Cache computed build values to prevent recomputation on every rebuild
  String? _cachedAgentTypeName;
  bool? _cachedSupportsControlSettings;

  Map<String, dynamic>? _getLastMessage() {
    if (_model.messages.isEmpty) {
      return null;
    }

    final lastMessage = _model.messages.last;
    if (lastMessage is! Map) {
      return null;
    }

    return Map<String, dynamic>.from(lastMessage);
  }

  bool _hasValidOptionsBlock(String content) {
    if (!content.contains('[OPTIONS]') || !content.contains('[/OPTIONS]')) {
      return false;
    }

    final optionsStart = content.lastIndexOf('[OPTIONS]');
    final optionsEnd = content.lastIndexOf('[/OPTIONS]');
    if (optionsStart == -1 || optionsEnd == -1 || optionsEnd <= optionsStart) {
      return false;
    }

    final afterOptions = content.substring(optionsEnd + '[/OPTIONS]'.length).trim();
    if (afterOptions.isNotEmpty) {
      return false;
    }

    final optionsContent =
        content.substring(optionsStart + '[OPTIONS]'.length, optionsEnd).trim();
    final lines = optionsContent.split('\n');
    final validOptions = lines
        .where((line) =>
            line.trim().isNotEmpty &&
            RegExp(r'^\d+\.\s+.+').hasMatch(line.trim()))
        .length;

    return validOptions > 0;
  }

  /// Optimistically update the cached instance.
  ///
  /// [liveState] must be passed alongside a resume: the composer gates on both
  /// `status` and `live_state`, and a resumed session keeps a stale
  /// `agent_stopped` verdict until its relaunched agent heartbeats (~30s).
  /// Updating only `status` left the input disabled until the user navigated
  /// away and back, which is what forced a refetch.
  void _setLocalSessionStatus(String status, {String? liveState}) {
    for (final source in [_model.instanceData, widget.instanceData]) {
      if (source is Map) {
        source['status'] = status;
        if (liveState != null) source['live_state'] = liveState;
      }
    }

    final appState = FFAppState();
    final updatedInstances = appState.cachedAgentInstances.map((instance) {
      if (instance is Map && instance['id'] == widget.instanceId) {
        return {
          ...Map<String, dynamic>.from(instance),
          'status': status,
          if (liveState != null) 'live_state': liveState,
        };
      }
      return instance;
    }).toList();

    appState.cachedAgentInstances = updatedInstances;
    appState.cachedAgentInstancesTimestamp = DateTime.now();
  }

  void _setLocalPinnedAt(String? pinnedAtIso) {
    if (_model.instanceData is Map) {
      (_model.instanceData as Map)['pinned_at'] = pinnedAtIso;
    }
    if (widget.instanceData is Map) {
      (widget.instanceData as Map)['pinned_at'] = pinnedAtIso;
    }

    final appState = FFAppState();
    final updatedInstances = appState.cachedAgentInstances.map((instance) {
      if (instance is Map && instance['id'] == widget.instanceId) {
        return {
          ...Map<String, dynamic>.from(instance),
          'pinned_at': pinnedAtIso,
        };
      }
      return instance;
    }).toList();

    appState.cachedAgentInstances = updatedInstances;
    appState.cachedAgentInstancesTimestamp = DateTime.now();
  }

  bool _isInstancePinned() {
    final modelPinned = (_model.instanceData is Map)
        ? (_model.instanceData as Map)['pinned_at']
        : null;
    if (modelPinned != null) return true;
    final widgetPinned = (widget.instanceData is Map)
        ? (widget.instanceData as Map)['pinned_at']
        : null;
    return widgetPinned != null;
  }

  Future<void> _handlePinToggle() async {
    final wasPinned = _isInstancePinned();
    final nowIso = DateTime.now().toUtc().toIso8601String();
    final nextValue = wasPinned ? null : nowIso;
    safeSetState(() => _setLocalPinnedAt(nextValue));

    final ok = await SessionActions.togglePin(
      instanceId: widget.instanceId,
      pinned: !wasPinned,
    );
    if (!mounted) return;
    if (!ok) {
      safeSetState(() => _setLocalPinnedAt(wasPinned ? nowIso : null));
      await _showSnackBarMessage(
        wasPinned
            ? AppLocalizations.of(context).agentChatUnpinFailed
            : AppLocalizations.of(context).agentChatPinFailed,
      );
    }
  }

  /// Clear the "awaiting input" blue dot once the user has seen the last
  /// message — either by opening the session, or by leaving it (see
  /// [didPop]/[didPushNext]). A session can flip to AWAITING_INPUT *while it's
  /// on screen* (the agent finishes its turn as you watch), so relying on open
  /// alone left the dot stuck until you re-entered the session; marking it on
  /// leave means switching away is enough. Skipped when the last message is a
  /// real question (ask-user-question / options block) — those still need input.
  Future<void> _maybeAutoReviewSession() async {
    final currentStatus =
        (_model.instanceData?['status'] ?? widget.instanceData?['status'])
            ?.toString()
            .toUpperCase();
    if (currentStatus != 'AWAITING_INPUT') {
      return;
    }

    final lastMessage = _getLastMessage();
    if (lastMessage == null) {
      return;
    }

    final hasAskUserQuestion =
        parseAskUserQuestionPayload(lastMessage) != null;
    final hasOptions =
        _hasValidOptionsBlock(lastMessage['content']?.toString() ?? '');

    if (hasAskUserQuestion || hasOptions) {
      return;
    }

    _setLocalSessionStatus('REVIEWED');
    final success =
        await actions.apiUpdateInstanceStatus(widget.instanceId, 'REVIEWED');
    if (!success) {
      _setLocalSessionStatus('AWAITING_INPUT');
    }
  }


  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => AgentChatModel());
    _currentVibingMessage = getRandomVibingMessage();
    _model.onScrollToBottomRequested = ({bool animate = true}) {
      // Auto-follow new messages only when the user hasn't pulled away. We
      // can't gate on !_showScrollToBottomButton: it depends on the inverse
      // of _isAtListBottom, but a model-triggered scrollToBottom() (e.g. a
      // status_update arriving from the shared WS) would otherwise snap the
      // user back to the bottom mid-scroll.
      if (_forceNextScroll || !_hasUserInteractedWithList || _isAtListBottom) {
        _scrollToBottom(animate: animate);
        _forceNextScroll = false; // Reset the flag after use
      }
    };
    _itemPositionsListenerCallback = _handleVisibleItemsChanged;
    _model.itemPositionsListener.itemPositions
        .addListener(_itemPositionsListenerCallback);
    WidgetsBinding.instance.addObserver(this);

    // // Initialize typing indicator animation controllers
    // _dotAnimationControllers = List.generate(3, (index) {
    //   return AnimationController(
    //     duration: const Duration(milliseconds: 800),
    //     vsync: this,
    //   );
    // });
    //
    // _dotAnimations = _dotAnimationControllers.map((controller) {
    //   return Tween<double>(begin: 0.3, end: 1.0).animate(
    //     CurvedAnimation(parent: controller, curve: Curves.easeInOut),
    //   );
    // }).toList();
    //
    // // Start animations with staggered delays
    // for (int i = 0; i < _dotAnimationControllers.length; i++) {
    //   Future.delayed(Duration(milliseconds: i * 200), () {
    //     if (mounted) {
    //       _dotAnimationControllers[i].repeat(reverse: true);
    //     }
    //   });
    // }
    
    // Set up state change callback for streaming updates
    _model.onStateChanged = _handleModelChanged;
    // Mirror SSE status_update events into widget.instanceData and
    // FFAppState's cachedAgentInstances so the whole app sees fresh status.
    _model.onStatusUpdate = (status) {
      debugPrint(
          '[ChatPage] propagating WS status to widget+FFAppState: $status (instance=${widget.instanceId})');
      _setLocalSessionStatus(status);
    };
    
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'AgentChat'});
    
    // Initialize chat with instance data
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      try {
        _model.instanceId = widget.instanceId;
        _model.instanceData = widget.instanceData;

        // Check if we have cached messages
        final cachedMessages = FFAppState().getCachedMessages(widget.instanceId);
        final hasCachedData = cachedMessages.isNotEmpty;

        // Only show full loading spinner if we don't have cached data
        _model.isLoadingMessages = !hasCachedData;
        if (mounted) safeSetState(() {});

        // Restore last seen message info before loading
        _model.restoreLastSeenMessage();

        await _model.loadMessages(hasCachedData: hasCachedData);
        await _maybeAutoReviewSession();
        _lastKnownMessageCount = _model.messages.length;

        // Build initial message metadata cache
        _rebuildMessageMetadataCache();

        // Cache agent type information
        _cachedAgentTypeName = (_model.instanceData?['agent_type_name'] ?? widget.instanceData?['agent_type_name'] ?? '').toString();
        _cachedSupportsControlSettings = _cachedAgentTypeName!.toLowerCase().contains('claude');

        // Check if there are new messages to show the banner
        if (_model.hasNewMessages()) {
          _showNewMessagesBanner = true;
        }

        // Restore draft message after loading
        _model.restoreDraftMessage();

        if (mounted) {
          _model.isLoadingMessages = false;
          safeSetState(() {});
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted) return;
            // Initial scroll-to-bottom on chat open. If the user has already
            // touched the list (cached messages render before REST returns,
            // and they may scroll up during that window), don't override
            // their position. Can't gate on _isAtListBottom — it's throttled
            // ~100ms and would still report stale-true if they just started
            // dragging, snapping them back to the bottom.
            // The welcome demo reads top-to-bottom like an article, so leave
            // it at the top on open instead of jumping to the latest message.
            if (isWelcomeDemoInstance(widget.instanceId)) {
              // Open at the top instantly — no visible scroll animation — and
              // hint that there's more below via the jump-to-bottom button.
              _model.scrollToTop(animate: false);
              if (_model.messages.isNotEmpty) {
                _showInitialDemoScrollHint = true;
              }
            } else if (!_hasUserInteractedWithList) {
              _scrollToBottom(animate: false);
            }
          });
        }
      } catch (e) {
        debugPrint('Error initializing chat: $e');
        _model.hasError = true;
        _model.errorMessage = AppLocalizations.of(context).agentChatInitFailed;
        if (mounted) safeSetState(() {});
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    routeObserver.unsubscribe(this);
    _model.itemPositionsListener.itemPositions
        .removeListener(_itemPositionsListenerCallback);
    _scrollThrottleTimer?.cancel();
    // for (var controller in _dotAnimationControllers) {
    //   controller.dispose();
    // }
    // Save draft message and last seen message before disposing
    _model.saveDraftMessage();
    _model.saveLastSeenMessage();
    _model.onScrollToBottomRequested = null;
    _queueRevision.dispose();
    _model.dispose();
    super.dispose();
  }


  @override
  void didUpdateWidget(AgentChatWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    _model.widget = widget;
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

  @override
  void didPopNext() {
    if (mounted && DebugFlutterFlowModelContext.maybeOf(context) == null) {
      setState(() => _model.isRouteVisible = true);
      debugLogWidgetClass(_model);
    }
  }

  @override
  void didPush() {
    if (mounted && DebugFlutterFlowModelContext.maybeOf(context) == null) {
      setState(() => _model.isRouteVisible = true);
      debugLogWidgetClass(_model);
    }
  }

  @override
  void didPop() {
    _model.isRouteVisible = false;
    // Save draft message and last seen message when navigating back
    _model.saveDraftMessage();
    _model.saveLastSeenMessage();
    // Leaving the session counts as having seen the last message — clear the
    // awaiting-input blue dot instead of forcing a re-open. Fire-and-forget.
    _maybeAutoReviewSession();
  }

  @override
  void didPushNext() {
    _model.isRouteVisible = false;
    // Save draft message and last seen message when pushing new route
    _model.saveDraftMessage();
    _model.saveLastSeenMessage();
    // Switching away from the session counts as seen — clear the blue dot.
    _maybeAutoReviewSession();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _model.refreshSpeechAvailability();
      // Re-fetch messages and restart SSE stream — the connection likely dropped
      // while the app was backgrounded and the one-shot retry may have expired.
      if (!_model.isLoadingMessages) {
        _model.loadMessages(hasCachedData: _model.messages.isNotEmpty);
      }
    } else if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      _model.saveDraftMessage();
      _model.saveLastSeenMessage();
    }
  }

  bool get _shouldShowTypingIndicator {
    if (_model.isWaitingForAgentResponse) return true;
    final status =
        (_model.instanceData?['status'] as String? ?? '').toUpperCase();
    return status == 'ACTIVE';
  }

  int get _listItemCount {
    final baseCount = _model.messages.length;
    final typingCount = _shouldShowTypingIndicator ? 1 : 0;
    return baseCount + typingCount + _trailingSpacerCount;
  }

  void _rebuildMessageMetadataCache() {
    // Clear old caches
    _isLastAgentMessageCache.clear();
    _dateLabelCache.clear();
    _subagentGrouping = custom_widgets.computeSubagentGrouping(_model.messages);

    // Find last user message index ONCE for all messages
    _cachedLastUserMessageIndex = null;
    for (int i = _model.messages.length - 1; i >= 0; i--) {
      final msgSender = _model.messages[i]['sender_type']?.toString().toLowerCase() ?? '';
      if (msgSender == 'user' || msgSender == 'human') {
        _cachedLastUserMessageIndex = i;
        break;
      }
    }

    // Precompute all message metadata
    for (int index = 0; index < _model.messages.length; index++) {
      // Cache date labels
      _dateLabelCache[index] = _computeDateLabelForMessage(index);

      // Cache isLastAgentMessage
      _isLastAgentMessageCache[index] = _computeIsLastAgentResponseInGroup(index);
    }
  }


  String? _dateLabelForMessage(int index) {
    return _dateLabelCache[index];
  }

  String? _computeDateLabelForMessage(int index) {
    if (index < 0 || index >= _model.messages.length) {
      return null;
    }

    final rawContent = _model.messages[index]['content']?.toString() ?? '';
    final sanitizedContent = _model.sanitizeMessageContent(rawContent);
    if (sanitizedContent.isEmpty) {
      return null;
    }

    final timestamp = _model.messages[index]['created_at']?.toString() ?? '';
    if (timestamp.isEmpty) {
      return null;
    }

    final messageDate = DateTime.tryParse(timestamp);
    if (messageDate == null) {
      return null;
    }

    final formattedDate = dateTimeFormat('MMMEd', messageDate);
    if (index == 0) {
      return formattedDate;
    }

    final previousTimestamp =
        _model.messages[index - 1]['created_at']?.toString() ?? '';
    if (previousTimestamp.isEmpty) {
      return formattedDate;
    }

    final previousDate = DateTime.tryParse(previousTimestamp);
    if (previousDate == null) {
      return formattedDate;
    }

    final previousFormatted = dateTimeFormat('MMMEd', previousDate);
    if (previousFormatted == formattedDate) {
      return null;
    }

    return formattedDate;
  }

  void _handleVisibleItemsChanged() {
    if (!mounted) {
      return;
    }

    if (_isScrollThrottleActive) {
      return;
    }

    _isScrollThrottleActive = true;
    _scrollThrottleTimer?.cancel();
    _scrollThrottleTimer = Timer(_scrollThrottleInterval, () {
      _isScrollThrottleActive = false;
    });

    if (_model.messages.isEmpty) {
      return;
    }

    final positions = _model.itemPositionsListener.itemPositions.value;
    if (positions.isEmpty) {
      return;
    }

    final totalItems = _listItemCount;
    if (totalItems == 0) {
      return;
    }

    // With reverse:false, index increases downward
    // So "at bottom" means the maximum visible index reaches the last item
    var maxVisibleIndex = positions.first.index;
    for (final position in positions) {
      if (position.index > maxVisibleIndex) {
        maxVisibleIndex = position.index;
      }
    }

    // At bottom when the last index (newest content) is visible
    // Account for typing indicator - if it just appeared, we're still conceptually "at bottom"
    final lastIndex = totalItems - 1;
    final lastMessageIndex = _model.messages.length - 1;

    // Consider "at bottom" if we're viewing either:
    // 1. The actual last item (spacer), OR
    // 2. The typing indicator, OR
    // 3. The last message (if no typing indicator)
    final atBottom = maxVisibleIndex >= lastMessageIndex;

    if (_isAtListBottom != atBottom) {
      _isAtListBottom = atBottom;
      setState(() {
        // Show the scroll-to-bottom button as soon as the user has pulled
        // away from the bottom. Gating on _hasUserInteractedWithList (rather
        // than a fixed _isInitialScrolling timer) means the down-arrow
        // appears immediately when the user scrolls — no 150ms hole where
        // they've scrolled up but the UI gives no affordance to return.
        _showScrollToBottomButton = !atBottom && _hasUserInteractedWithList;
        // One-time "there's more below" hint shown on opening the welcome demo
        // (it opens at the top). Clear it once we reach the bottom or the user
        // starts scrolling, after which normal button logic applies.
        if (atBottom || _hasUserInteractedWithList) {
          _showInitialDemoScrollHint = false;
        }
        if (atBottom && _hasUserInteractedWithList) {
          _showNewMessagesBanner = false;
          _newMessagesBannerBaseIndex = null;
        }
        // If user manually scrolled away, clear the flag
        if (!atBottom && _hasUserInteractedWithList) {
          _pendingAutoScrollToBottom = false;
        }
      });
      if (atBottom && _hasUserInteractedWithList) {
        _model.saveLastSeenMessage();
      }
      return;
    }

    if ((atBottom || _hasUserInteractedWithList) && _showInitialDemoScrollHint) {
      setState(() => _showInitialDemoScrollHint = false);
    }

    final shouldShowButton = !atBottom && _hasUserInteractedWithList;
    if (_showScrollToBottomButton != shouldShowButton) {
      setState(() => _showScrollToBottomButton = shouldShowButton);
    }

    if (atBottom && _showNewMessagesBanner && _hasUserInteractedWithList) {
      setState(() {
        _showNewMessagesBanner = false;
        _newMessagesBannerBaseIndex = null;
      });
      _model.saveLastSeenMessage();
    }
  }

  void _requestAutoScrollForNextMessages() {
    // When user explicitly sends a message, always auto-scroll to show the response
    // This provides better UX - user wants to see their message and the agent's response
    _pendingAutoScrollToBottom = true;
    // Also set forceNextScroll to ensure the scroll callback executes immediately
    // when the model calls scrollToBottom() before onStateChanged is triggered
    _forceNextScroll = true;
  }

  Uri _normalizePreviewUri(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) {
      return Uri.parse('https://vicoa.ai');
    }
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      return Uri.parse(trimmed);
    }
    return Uri.parse('https://$trimmed');
  }

  String? _previewOrigin(String? raw) {
    if (raw == null || raw.trim().isEmpty) {
      return null;
    }
    final uri = _normalizePreviewUri(raw);
    final host = uri.host.trim().toLowerCase();
    if (host.isEmpty) {
      return null;
    }
    final scheme = uri.scheme.trim().toLowerCase();
    final port = uri.hasPort ? ':${uri.port}' : '';
    return '$scheme://$host$port';
  }

  Future<void> _openLatestWebPreview() async {
    final previewUrl = _model.latestWebPreviewUrl;
    if (previewUrl == null || previewUrl.isEmpty) {
      return;
    }
    final normalizedPreviewUrl = _normalizePreviewUri(previewUrl).toString();
    final cachedPreviewUrl = FFAppState().lastWebPreviewUrl.trim();
    final initialUrl = cachedPreviewUrl.isNotEmpty &&
            _previewOrigin(cachedPreviewUrl) == _previewOrigin(normalizedPreviewUrl)
        ? cachedPreviewUrl
        : normalizedPreviewUrl;

    await context.pushNamed(
      WebPreviewWidget.routeName,
      extra: <String, dynamic>{
        'initialUrl': initialUrl,
        kTransitionInfoKey: const TransitionInfo(
          hasTransition: true,
          transitionType: PageTransitionType.bottomToTop,
        ),
      },
    );
  }

  void _handleModelChanged() {
    if (!mounted) {
      return;
    }

    final messageCount = _model.messages.length;
    final hasNewMessages = messageCount > _lastKnownMessageCount;
    final currentSendingState = _model.isSendingMessage;
    final currentIndicatorState = _shouldShowTypingIndicator;
    final permissionModeChanged = _model.permissionMode != _previousPermissionMode;
    final slashCommandStateChanged = _model.showSlashCommandSuggestions != _previousShowSlashCommands ||
        _model.filteredSlashCommands.length != _previousSlashCommandCount;
    final fileMentionStateChanged = _model.showFileMentionSuggestions != _previousShowFileMentions ||
        _model.fileMentionSuggestionsRevision != _previousFileMentionRevision;
    final attachmentsStateChanged =
        _model.pendingAttachmentsRevision != _previousAttachmentsRevision;
    final messageMetadataStateChanged =
        _model.messageMetadataRevision != _previousMessageMetadataRevision;
    final voiceStateChanged = _model.isVoiceDictationVisible != _previousVoiceDictationVisible ||
        _model.voiceDisplayTranscript != _previousVoiceTranscript ||
        _model.voiceDictationUiState?.name != _previousVoiceState ||
        _model.voiceElapsedDuration.inSeconds != _previousVoiceElapsedSeconds;

    // Check if anything actually changed that requires a rebuild
    final sendingStateChanged = currentSendingState != _previousSendingState;
    final indicatorStateChanged = currentIndicatorState != _previousIndicatorState;
    final needsRebuild =
        hasNewMessages ||
        sendingStateChanged ||
        indicatorStateChanged ||
        permissionModeChanged ||
        slashCommandStateChanged ||
        fileMentionStateChanged ||
        attachmentsStateChanged ||
        messageMetadataStateChanged ||
        voiceStateChanged;

    // Update tracked state (do this BEFORE early return to stay in sync)
    _previousSendingState = currentSendingState;
    _previousIndicatorState = currentIndicatorState;
    _previousPermissionMode = _model.permissionMode;
    _previousShowSlashCommands = _model.showSlashCommandSuggestions;
    _previousSlashCommandCount = _model.filteredSlashCommands.length;
    _previousShowFileMentions = _model.showFileMentionSuggestions;
    _previousFileMentionRevision = _model.fileMentionSuggestionsRevision;
    _previousAttachmentsRevision = _model.pendingAttachmentsRevision;
    _previousMessageMetadataRevision = _model.messageMetadataRevision;
    _previousVoiceDictationVisible = _model.isVoiceDictationVisible;
    _previousVoiceTranscript = _model.voiceDisplayTranscript;
    _previousVoiceState = _model.voiceDictationUiState?.name;
    _previousVoiceElapsedSeconds = _model.voiceElapsedDuration.inSeconds;

    if (!needsRebuild) {
      // Nothing changed, skip rebuild
      return;
    }

    // Rebuild cache when messages change or the typing indicator toggles
    // (indicator state affects which messages show action buttons)
    if (hasNewMessages || indicatorStateChanged) {
      _rebuildMessageMetadataCache();
    }

    if (hasNewMessages) {
      // Check if we're at bottom RIGHT NOW (don't rely on throttled _isAtListBottom)
      // This is more reliable than the throttled position listener
      bool wasAtBottom = _isAtListBottom;

      // Double-check by looking at actual positions (bypass throttle)
      final positions = _model.itemPositionsListener.itemPositions.value;
      if (positions.isNotEmpty) {
        var maxVisibleIndex = positions.first.index;
        for (final position in positions) {
          if (position.index > maxVisibleIndex) {
            maxVisibleIndex = position.index;
          }
        }
        // Before adding new message, check if we're viewing the current last message
        final currentLastMessageIndex = _lastKnownMessageCount - 1;
        wasAtBottom = maxVisibleIndex >= currentLastMessageIndex;
      }

      // Generate new vibing message when messages change
      _currentVibingMessage = getRandomVibingMessage();

      var shouldAutoScroll = wasAtBottom || _pendingAutoScrollToBottom;

      // The welcome demo opens at the top (read like an article). Suppress the
      // open-time auto-scroll-to-bottom until the user interacts; CTA-button
      // appends still scroll down via appendDemoMessage's direct scrollToBottom.
      if (isWelcomeDemoInstance(widget.instanceId) &&
          !_hasUserInteractedWithList) {
        shouldAutoScroll = false;
      }

      if (shouldAutoScroll && _isAskUserQuestionInputFocused) {
        // Scroll physics are locked while the AskUserQuestion text field is
        // focused — attempting programmatic scroll would fail silently.
        // Show the banner instead so the user knows messages arrived.
        _showNewMessagesBanner = true;
        _newMessagesBannerBaseIndex ??= _lastKnownMessageCount - 1;
      } else if (shouldAutoScroll) {
        // Only clear the banner on auto-scroll if the user has already
        // interacted with the list. This prevents WebSocket catch-up messages
        // (arriving right after page load while _isAtListBottom=true) from
        // clearing a banner that was set by the initial hasNewMessages() check.
        if (_hasUserInteractedWithList) {
          _showNewMessagesBanner = false;
        }
        _shouldAutoScrollAfterRebuild = true;
      } else {
        // User is scrolled up - show banner but don't scroll
        _showNewMessagesBanner = true;
        _newMessagesBannerBaseIndex ??= _lastKnownMessageCount - 1;
      }

      _pendingAutoScrollToBottom = false;
    }

    _lastKnownMessageCount = messageCount;
    // Queue membership only shifts on a new message or an in-place metadata
    // patch (queued → consumed/cancelled) — tick the sheet in those cases.
    if (messageMetadataStateChanged || hasNewMessages) {
      _queueRevision.value++;
    }
    safeSetState(() {});

    // After rebuild, check if we should auto-scroll
    if (_shouldAutoScrollAfterRebuild) {
      _shouldAutoScrollAfterRebuild = false;
      // Use a short delay to ensure the list has rebuilt
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          // Force the scroll since we determined the user was at the bottom before the new message
          _forceNextScroll = true;
          _model.scrollToBottom(animate: false);
        }
      });
    }
  }

  void _scrollToMessageByIndex(int messageIndex, {int attempt = 0}) {
    if (messageIndex < 0 || messageIndex >= _model.messages.length) {
      return;
    }

    // With reverse:false, use actual message index directly (no conversion needed!)
    if (_model.itemScrollController.isAttached) {
      _isProgrammaticScroll = true;
      _model.itemScrollController.scrollTo(
        index: messageIndex,
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeInOut,
        alignment: 0.1, // Show message near top of viewport
      );
      // Reset flag after scroll completes
      Future.delayed(const Duration(milliseconds: 300), () {
        if (mounted) _isProgrammaticScroll = false;
      });
      return;
    }

    if (attempt >= 3) {
      return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _scrollToMessageByIndex(messageIndex, attempt: attempt + 1);
    });
  }

  /// Re-anchors the list on the item at [index] so it stays fixed while it
  /// grows. Call this *before* mutating the expansion state.
  ///
  /// ScrollablePositionedList lays out from a center item (the last
  /// jumpTo/scrollTo target — normally the newest message at the bottom) and
  /// grows downward from it; items ABOVE that center are laid out upward. So an
  /// item above the center that grows pushes itself, and everything above it,
  /// up — which reads backwards when a tool-use row expands.
  ///
  /// Jumping to this item at *exactly* its current leading edge is a visual
  /// no-op, but it makes the item the center, so the imminent growth extends
  /// downward from its now-pinned top. Doing this up front avoids the visible
  /// pop-and-snap of correcting the position after the frame.
  void _pinListItemPosition(int index) {
    if (!_model.itemScrollController.isAttached) return;
    double? edge;
    for (final position in _model.itemPositionsListener.itemPositions.value) {
      if (position.index == index) {
        edge = position.itemLeadingEdge;
        break;
      }
    }
    if (edge == null) return; // Off-screen — nothing to preserve.
    _model.itemScrollController.jumpTo(index: index, alignment: edge);
  }

  void _scrollToBottom({bool animate = false}) {
    if (_model.messages.isEmpty && !_shouldShowTypingIndicator) {
      return;
    }

    void performScroll() {
      // With reverse:false, scroll to the last index (the trailing spacer)
      // This ensures we scroll to the very bottom
      final targetIndex = _listItemCount - 1;

      if (targetIndex < 0) {
        return;
      }

      // For reverse:false with trailing spacer at the end:
      // alignment: 1.0 = align item's trailing edge to viewport's trailing edge (bottom)
      // This should scroll to show the spacer at the very bottom
      const alignmentValue = 0.945;

      // Mark as programmatic scroll to prevent keyboard dismissal
      _isProgrammaticScroll = true;

      if (animate) {
        _model.itemScrollController.scrollTo(
          index: targetIndex,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          alignment: alignmentValue,
        );
        // Reset flag after animation completes, BUT NOT if ask user question input is focused
        Future.delayed(const Duration(milliseconds: 250), () {
          if (mounted && !_isAskUserQuestionInputFocused) {
            _isProgrammaticScroll = false;
          }
        });
      } else {
        _model.itemScrollController.jumpTo(
          index: targetIndex,
          alignment: alignmentValue,
        );
        // Reset flag immediately for jumpTo, BUT NOT if ask user question input is focused
        Future.delayed(const Duration(milliseconds: 50), () {
          if (mounted && !_isAskUserQuestionInputFocused) {
            _isProgrammaticScroll = false;
          }
        });
      }
    }

    if (_model.itemScrollController.isAttached) {
      performScroll();
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        _scrollToBottom(animate: animate);
      });
    }
  }

  Widget _buildMessage(
    dynamic message, {
    required int messageIndex,
    bool isLastAgentMessage = false,
  }) {
    final senderType = message['sender_type']?.toString() ?? '';
    final isUser = senderType.toLowerCase() == 'user' ||
                   senderType.toLowerCase() == 'human';
    final rawContent = message['content']?.toString() ?? '';
    final content = _model.sanitizeMessageContent(rawContent);
    final requiresUserInput = message['requires_user_input'] == true;
    final askUserQuestionPayload = parseAskUserQuestionPayload(message);
    final messageId = message['id']?.toString() ?? '';

    // Send-queue status is only meaningful on USER messages (only they can be
    // queued behind a busy agent). `consumed`/absent renders like normal.
    final messageQueueStatus = isUser ? queueStatus(message) : null;
    final isQueuedMessage = messageQueueStatus == kQueueStatusQueued;
    final isCancelledMessage = messageQueueStatus == kQueueStatusCancelled;

    // Queued (and cancelled-before-consumed) user messages never enter the
    // transcript — they're staged in the queue bar above the input until the
    // agent picks them up (backend flips them to `consumed`, at which point
    // they render here as a normal message). Cancelled ones just vanish.
    if (isUser && (isQueuedMessage || isCancelledMessage)) {
      return const SizedBox.shrink();
    }

    // Image attachments stamped into message_metadata at send time, plus the
    // local-file render hint carried by optimistic/just-sent entries.
    final metadata = message['message_metadata'];
    final attachments = (metadata is Map && metadata['attachments'] is List)
        ? metadata['attachments'] as List
        : const [];
    final localPaths = <String, String>{
      if (message['_local_paths'] is Map)
        for (final entry in (message['_local_paths'] as Map).entries)
          entry.key.toString(): entry.value.toString(),
    };

    // A sub-agent neighbour is NOT part of this row's bordered group: it draws
    // its own `SubagentGroup` box (at its anchor index — the other members
    // render nothing), so this row must close/open its own borders against it
    // rather than fuse with content the user can't even see.
    final prevIsSubagent = _isSubagentMessage(messageIndex - 1);
    final nextIsSubagent = _isSubagentMessage(messageIndex + 1);

    // Compute tool-use grouping flags for border rendering. Computed here,
    // ABOVE the empty-content early return below, because the sub-agent
    // branch (which also sits above that early return) needs the spacing —
    // see the comment on that branch for why the ordering matters.
    final isToolUse = !isUser && _isToolUseMessage(content);
    // An AskUserQuestion tool use always renders as its own standalone box: it
    // never fuses (border or spacing) with the tool use above or below, so its
    // interactive prompt reads as a distinct block with the same breathing room
    // as any other tool use — whether it follows another tool use or plain text.
    final isAskUserQuestionTool =
        isToolUse && custom_widgets.isAskUserQuestionToolContent(content);
    bool toolUseIsFirst = true;
    bool toolUseIsLast = true;
    if (isToolUse) {
      if (messageIndex > 0) {
        final prevRaw = _model.messages[messageIndex - 1]['content']?.toString() ?? '';
        final prevContent = _model.sanitizeMessageContent(prevRaw);
        final prevSender = _model.messages[messageIndex - 1]['sender_type']?.toString() ?? '';
        final prevIsUser = prevSender.toLowerCase() == 'user' || prevSender.toLowerCase() == 'human';
        // Previous message breaks the group if it's not a tool-use OR if it
        // had a trailing code block (which acts as a visual separator).
        toolUseIsFirst = prevIsUser ||
            prevIsSubagent ||
            !_isToolUseMessage(prevContent) ||
            _toolUseHasTrailingCodeBlock(prevContent);
      }
      if (messageIndex < _model.messages.length - 1) {
        final nextRaw = _model.messages[messageIndex + 1]['content']?.toString() ?? '';
        final nextContent = _model.sanitizeMessageContent(nextRaw);
        final nextSender = _model.messages[messageIndex + 1]['sender_type']?.toString() ?? '';
        final nextIsUser = nextSender.toLowerCase() == 'user' || nextSender.toLowerCase() == 'human';
        // An AskUserQuestion below breaks the group too, so the tool above
        // rounds its bottom and a full gap opens between them.
        final nextIsAskUserQuestion =
            custom_widgets.isAskUserQuestionToolContent(nextContent);
        toolUseIsLast = nextIsUser ||
            nextIsSubagent ||
            !_isToolUseMessage(nextContent) ||
            nextIsAskUserQuestion;
      }
      // A tool-use with its own trailing code block — or an AskUserQuestion,
      // which always stands alone — is the last in its group.
      if (_toolUseHasTrailingCodeBlock(content) || isAskUserQuestionTool) {
        toolUseIsLast = true;
      }
      // ...and an AskUserQuestion always opens its own box (never fuses upward).
      if (isAskUserQuestionTool) {
        toolUseIsFirst = true;
      }
    }

    // True when this tool-use starts a new group immediately after a fused code
    // block. A sub-agent predecessor never counts: its code block is drawn
    // inside its own group box, not against this row.
    final toolUseAfterCodeBlock = isToolUse &&
        toolUseIsFirst &&
        messageIndex > 0 &&
        !prevIsSubagent &&
        _toolUseHasTrailingCodeBlock(
          _model.sanitizeMessageContent(
            _model.messages[messageIndex - 1]['content']?.toString() ?? '',
          ),
        );

    // Which neighbour owns the gap on each side, and how wide it should be —
    // see `chat_block_spacing.dart`. Above: a bordered block already
    // contributed the gap below itself. Below: a sub-agent group owns its own
    // gap on both sides (its hidden members make the ordinary "block above
    // owns it" rule unreliable), so this block must yield; otherwise the gap
    // is wide when another bordered block follows, narrow against plain
    // content.
    final followsBorderedBlock = _followsBorderedBlock(messageIndex - 1);
    final precedesSubagentGroup = _precedesSubagentGroup(messageIndex + 1);
    final precedesBorderedBlock = _precedesBorderedBlock(messageIndex + 1);

    const double userHorizontalPadding = 18.0;
    const double agentHorizontalPadding = 8.0;
    const double userVerticalPadding = 14.0;
    const double agentVerticalPadding = 10.0;

    // Spacing around tool-use groups
    final double topMargin;
    final double bottomMargin;
    if (isUser) {
      topMargin = 16.0;
      bottomMargin = 16.0;
    } else if (isToolUse) {
      // AskUserQuestion flows through here too — it's a standalone bordered box
      // (see the grouping flags above), spaced like any other tool use.
      topMargin = chatBlockTopMargin(
        followsBorderedBlock: followsBorderedBlock,
        startsNewToolGroup: toolUseIsFirst,
        followsFusedCodeBlock: toolUseAfterCodeBlock,
      );
      bottomMargin = chatBlockBottomMargin(
        endsToolGroup: toolUseIsLast,
        precedesSubagentGroup: precedesSubagentGroup,
        precedesBorderedBlock: precedesBorderedBlock,
      );
    } else {
      topMargin = 0.0;
      bottomMargin = 0.0;
    }

    // Sub-agent (Task tool) grouping: every message tagged with the same
    // message_metadata.subagent.tool_use_id folds into one "Sub-agent: <type>"
    // collapsible group, rendered from the group's first (anchor) occurrence —
    // NOT a consecutive run, since parallel sub-agents interleave their child
    // messages in chat order. Every other member of the group renders nothing
    // (the anchor draws them all).
    //
    // Deliberately checked BEFORE the empty-content early return below (and
    // before the tool-use collapse branch): the anchor is just "whichever
    // index carries this tool_use_id first" — it can be a message whose OWN
    // content sanitises to empty (e.g. a stderr-only tool result), even
    // though the group as a whole has real content from its other members.
    // `_collectSubagentRunIndices` re-reads every member's content
    // independently of this anchor's own (possibly empty) content, so
    // rendering the group here — ahead of the early return — is what lets
    // the rest of the group survive an empty-content anchor instead of the
    // whole group silently vanishing.
    if (_isSubagentMessage(messageIndex)) {
      if (!_isSubagentRunStart(messageIndex)) {
        return const SizedBox.shrink();
      }
      final runIndices = _collectSubagentRunIndices(messageIndex);
      final runContents = [
        for (final i in runIndices)
          _model.sanitizeMessageContent(
              _model.messages[i]['content']?.toString() ?? ''),
      ];
      final groupKey = custom_widgets.subagentToolUseIdOf(message) ??
          'idx_$messageIndex';
      final agentType = _model.instanceData?['agent_type_name'] ??
          widget.instanceData?['agent_type_name'];
      final runIsLastAgent = runIndices.isNotEmpty &&
          _isLastAgentResponseInGroup(runIndices.last);

      return RepaintBoundary(
        child: Container(
          // The group owns its gap on BOTH sides itself, applied here rather
          // than relying on the neighbour above. That neighbour can be one of
          // this group's own hidden members (they render nothing but stay in
          // the list), so keying the top gap off it collapsed the gap to
          // nearly zero. Owning it makes the gap robust; the neighbours yield
          // (`precedesSubagentGroup` above, `followsBorderedBlock` below) so
          // it never doubles. Each side still picks its own width based on
          // whether what's actually next to it is bordered or plain content.
          margin: subagentBlockMargin(
            followsBorderedBlock: followsBorderedBlock,
            precedesSubagentGroup: precedesSubagentGroup,
            precedesBorderedBlock: precedesBorderedBlock,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Flexible(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    custom_widgets.SubagentGroup(
                      subagentType: custom_widgets.subagentTypeOf(message),
                      description: custom_widgets.subagentDescriptionOf(message),
                      contents: runContents,
                      expanded: _expandedSubagentGroups.contains(groupKey),
                      // Fires before any expand/collapse in this group so the
                      // tapped line stays put instead of being pushed up by
                      // the list's anchoring (mirrors the tool-use group).
                      onBeforeToggle: () => _pinListItemPosition(messageIndex),
                      onToggle: () {
                        safeSetState(() {
                          if (!_expandedSubagentGroups.remove(groupKey)) {
                            _expandedSubagentGroups.add(groupKey);
                          }
                        });
                      },
                      agentTypeName: agentType,
                      filterProjectRoot: _model.filterProjectRootFromContent,
                    ),
                    if (runIsLastAgent)
                      _buildMessageActionsRow(_model.messages[runIndices.last]),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    // Model reasoning (Claude ThinkingBlock / Codex reasoning) renders as its
    // own standalone collapsed "Thinking" card — its own bordered box, spaced
    // like a collapsed tool run. Checked here, ahead of the empty-content
    // early return, for symmetry with the sub-agent branch (a reasoning
    // message always has content, so this ordering is belt-and-braces).
    if (_isThinkingMessage(messageIndex)) {
      final groupKey = messageId.isNotEmpty ? messageId : 'idx_$messageIndex';
      final agentType = _model.instanceData?['agent_type_name'] ??
          widget.instanceData?['agent_type_name'];

      return RepaintBoundary(
        child: Container(
          // A thinking card is always its own bordered box; own its gap on both
          // sides like the collapsed tool-run and sub-agent branches.
          margin: chatBlockMargin(
            followsBorderedBlock: followsBorderedBlock,
            precedesSubagentGroup: precedesSubagentGroup,
            precedesBorderedBlock: precedesBorderedBlock,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Flexible(
                child: custom_widgets.ThinkingGroup(
                  content: content,
                  expanded: _expandedThinkingCards.contains(groupKey),
                  onBeforeToggle: () => _pinListItemPosition(messageIndex),
                  onToggle: () {
                    safeSetState(() {
                      if (!_expandedThinkingCards.remove(groupKey)) {
                        _expandedThinkingCards.add(groupKey);
                      }
                    });
                  },
                  agentTypeName: agentType,
                  filterProjectRoot: _model.filterProjectRootFromContent,
                ),
              ),
            ],
          ),
        ),
      );
    }

    // Only skip the message entirely when content is empty AND there is
    // neither an AskUserQuestion panel nor an image attachment to render.
    // Both live in message_metadata, so they can be present even when the
    // text content sanitises to empty. Sub-agent messages are handled above,
    // before this point, so this only ever short-circuits non-sub-agent
    // messages.
    if (content.isEmpty &&
        attachments.isEmpty &&
        (isUser || askUserQuestionPayload == null || messageId.isEmpty)) {
      return const SizedBox.shrink();
    }

    // Images render OUTSIDE the text bubble — right-aligned like the user's
    // messages, with their own rounded corners. The bubble itself only
    // renders when there is text (or a panel) to put inside it.
    final showAskPanel =
        !isUser && askUserQuestionPayload != null && messageId.isNotEmpty;
    final showWelcomeCta = !isUser && _isWelcomeCtaMessage(message);
    final hasBubbleContent = content.isNotEmpty || showAskPanel || showWelcomeCta;

    // Collapsed tool-use mode: fold a run of consecutive tool uses into one
    // tap-to-expand group, rendered from the run's first message. The run's
    // other rows render nothing (this group draws them). When the setting is
    // off, this branch is skipped and rendering is byte-for-byte the old path.
    // Interactive tool uses ([OPTIONS] / user input / questions) are excluded so
    // they never get hidden inside a collapsed group.
    if (FFAppState().setting.collapseToolUse &&
        _isCollapsibleToolUse(messageIndex)) {
      if (!_isCollapseRunStart(messageIndex)) {
        return const SizedBox.shrink();
      }
      final runIndices = _collectToolRunIndices(messageIndex);
      final runContents = [
        for (final i in runIndices)
          _model.sanitizeMessageContent(
              _model.messages[i]['content']?.toString() ?? ''),
      ];
      final groupKey = messageId.isNotEmpty ? messageId : 'idx_$messageIndex';
      final agentType = _model.instanceData?['agent_type_name'] ??
          widget.instanceData?['agent_type_name'];
      final runIsLastAgent = runIndices.isNotEmpty &&
          _isLastAgentResponseInGroup(runIndices.last);

      return RepaintBoundary(
        child: Container(
          // A collapsed run is always its own box, never a continuation of the
          // run above it.
          margin: chatBlockMargin(
            followsBorderedBlock: followsBorderedBlock,
            precedesSubagentGroup: precedesSubagentGroup,
            precedesBorderedBlock: precedesBorderedBlock,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Flexible(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    custom_widgets.ToolUseGroup(
                      contents: runContents,
                      expanded: _expandedToolGroups.contains(groupKey),
                      // Fires before any expand/collapse in this group (header
                      // or a nested row) so the tapped line stays put instead
                      // of being pushed up by the list's anchoring.
                      onBeforeToggle: () => _pinListItemPosition(messageIndex),
                      onToggle: () {
                        safeSetState(() {
                          if (!_expandedToolGroups.remove(groupKey)) {
                            _expandedToolGroups.add(groupKey);
                          }
                        });
                      },
                      agentTypeName: agentType,
                      filterProjectRoot: _model.filterProjectRootFromContent,
                    ),
                    if (runIsLastAgent)
                      _buildMessageActionsRow(_model.messages[runIndices.last]),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    return RepaintBoundary(
      child: Container(
      margin: EdgeInsetsDirectional.fromSTEB(
        isUser ? 48.0 : 16.0,
        topMargin,
        isUser ? 16.0 : 16.0,
        bottomMargin,
      ),
      child: Row(
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Flexible(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final maxBubbleWidth =
                    isUser ? constraints.maxWidth * 0.9 : double.infinity;

                return Column(
                  crossAxisAlignment:
                      isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                  children: [
                    if (attachments.isNotEmpty) ...[
                      Container(
                        constraints: BoxConstraints(maxWidth: maxBubbleWidth),
                        child: MessageAttachments(
                          attachments: attachments,
                          localPaths: localPaths,
                          alignEnd: isUser,
                        ),
                      ),
                      if (hasBubbleContent) const SizedBox(height: 8.0),
                    ],
                    if (hasBubbleContent)
                    Container(
                      constraints: BoxConstraints(
                        maxWidth: maxBubbleWidth,
                      ),
                      padding: isToolUse
                          ? EdgeInsets.zero
                          : EdgeInsetsDirectional.fromSTEB(
                              isUser ? userHorizontalPadding : agentHorizontalPadding,
                              isUser ? userVerticalPadding : agentVerticalPadding,
                              isUser ? userHorizontalPadding : agentHorizontalPadding,
                              isUser ? userVerticalPadding : agentVerticalPadding,
                            ),
                      decoration: isToolUse
                          ? const BoxDecoration()
                          : BoxDecoration(
                              color: isUser
                                  ? FlutterFlowTheme.of(context).secondaryText.withValues(
                                        alpha: Theme.of(context).brightness == Brightness.light
                                            ? 0.08
                                            : 0.15,
                                      )
                                  : FlutterFlowTheme.of(context).secondaryBackground,
                              borderRadius: const BorderRadius.all(
                                Radius.circular(20.0),
                              ),
                            ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildMessageContent(
                            content,
                            isUser: isUser,
                            messageIndex: messageIndex,
                            requiresUserInput: requiresUserInput,
                            toolUseIsFirst: toolUseIsFirst,
                            toolUseIsLast: toolUseIsLast,
                            isCancelled: isCancelledMessage,
                          ),
                          if (!isUser && askUserQuestionPayload != null && messageId.isNotEmpty)
                            AskUserQuestionPanel(
                              key: ValueKey('aqp_$messageId'),
                              messageId: messageId,
                              payload: askUserQuestionPayload,
                              initialAnswers: _askUserQuestionAnswers[messageId],
                              onAnswersChanged: (answers) {
                                _askUserQuestionAnswers[messageId] = answers;
                              },
                              onTextInputFocusChanged: (focused) {
                                if (!mounted || _isAskUserQuestionInputFocused == focused) return;
                                safeSetState(() => _isAskUserQuestionInputFocused = focused);

                                // Keep programmatic scroll flag set while text input is focused
                                // This prevents any scroll notifications from dismissing the keyboard
                                if (focused) {
                                  _isProgrammaticScroll = true;
                                } else {
                                  _isProgrammaticScroll = false;
                                }
                              },
                              onRequestScrollToBottom: () {
                                // Scroll the entire list to the bottom when text input is focused
                                _scrollToBottom(animate: true);
                              },
                              onSubmit: (payload) async {
                                // Welcome demo: the waitlist answer is recorded
                                // locally + forwarded to the team, never sent to
                                // an agent.
                                if (isWelcomeDemoInstance(widget.instanceId)) {
                                  await _handleDemoWaitlistSubmit(payload);
                                  return;
                                }
                                await _model.submitAskUserQuestion(
                                  messageId: payload.messageId,
                                  answers: payload.answers.map((answer) => answer.toJson()).toList(),
                                  displayAnswers: payload.displayAnswers,
                                );
                              },
                              onCancel: (_) async {
                                if (isWelcomeDemoInstance(widget.instanceId)) {
                                  return;
                                }
                                await _model.cancelAskUserQuestion();
                              },
                            ),
                          if (!isUser && _isWelcomeCtaMessage(message))
                            WelcomeDemoCta(
                              busy: _demoCtaBusy,
                              onSetupCli: _handleDemoSetupCli,
                              onNoComputer: _handleDemoNoComputer,
                            ),
                        ],
                      ),
                    ),
                    // Surface actions on the trailing agent message in each response group
                    if (!isUser && isLastAgentMessage)
                      _buildMessageActionsRow(message),
                  ],
                );
              },
            ),
          ),
        ],
      ),
      ),
    );
  }

  bool _isToolUseMessage(String content) {
    final t = content.trim();
    return t.startsWith('Using tool:') ||
        t.startsWith('🔧 Using tool:') ||
        t.startsWith('**Exec:**') ||
        (t.contains('✏️ Applying patch to') && t.contains('file (+'));
  }

  /// Whether the message at [index] can be folded into a collapsed tool-use
  /// run. Unlike the border grouping used by the expanded (setting-off) path,
  /// this deliberately ignores trailing code blocks — an Edit with an inline
  /// diff still groups with its neighbours (its diff collapses per-row). It
  /// excludes interactive messages ([OPTIONS] / user input / AskUserQuestion)
  /// so they never get hidden inside a collapsed group.
  ///
  /// AskUserQuestion is checked twice on purpose. The payload check only sees
  /// the message carrying `message_metadata.ask_user_question`; the plain
  /// "Using tool: **AskUserQuestion** - ..." announcement has no metadata, so on
  /// its own it satisfies the tool-use-shape check and folds into the
  /// neighbouring run. The tool-name check keeps it standalone.
  ///
  /// Also excludes sub-agent-tagged messages (`_isSubagentMessage`): those
  /// are exclusively owned by the sub-agent grouping branch above (rendered
  /// once at their `SubagentGroup` anchor). Without this guard, a sub-agent's
  /// leading "Using tool: ..." child message(s) satisfy this same
  /// tool-use-shape check and get absorbed into a consecutive tool-use run —
  /// duplicating that content on screen (once via the tool-use run, once via
  /// the sub-agent group). Gating here — the single source `_isCollapseRunStart`
  /// and `_collectToolRunIndices` both call — keeps run-start, run-collection,
  /// and membership all consistent with zero separate guards needed.
  bool _isCollapsibleToolUse(int index) {
    if (index < 0 || index >= _model.messages.length) return false;
    final m = _model.messages[index];
    final sender = m['sender_type']?.toString().toLowerCase() ?? '';
    final c = _model.sanitizeMessageContent(m['content']?.toString() ?? '');
    return custom_widgets.isCollapsibleToolUseMessage(
      isUserOrHumanSender: sender == 'user' || sender == 'human',
      requiresUserInput: m['requires_user_input'] == true,
      hasAskUserQuestionPayload: parseAskUserQuestionPayload(m) != null,
      isAskUserQuestionTool: custom_widgets.isAskUserQuestionToolContent(c),
      isSubagentMessage: _isSubagentMessage(index),
      isToolUseContent: _isToolUseMessage(c),
      hasValidOptionsBlock: _hasValidOptionsBlock(c),
    );
  }

  /// True when [index] starts a collapse run: it's collapsible and the previous
  /// message is not part of the same run.
  bool _isCollapseRunStart(int index) =>
      _isCollapsibleToolUse(index) && !_isCollapsibleToolUse(index - 1);

  /// Indices of the maximal run of consecutive collapsible tool uses starting
  /// at [startIndex].
  List<int> _collectToolRunIndices(int startIndex) {
    final indices = <int>[];
    for (int i = startIndex;
        i < _model.messages.length && _isCollapsibleToolUse(i);
        i++) {
      indices.add(i);
    }
    return indices;
  }

  /// Whether message[index] carries sub-agent tagging
  /// (message_metadata.subagent.tool_use_id). Thin wrapper around the
  /// precomputed [_subagentGrouping] (see _rebuildMessageMetadataCache).
  bool _isSubagentMessage(int index) => _subagentGrouping.isSubagentMessage(index);

  /// Whether message[index] is model reasoning tagged with
  /// `message_metadata.thinking` — rendered as a standalone collapsed
  /// "Thinking" card. Sub-agent-tagged reasoning is excluded (owned by the
  /// sub-agent group, which renders its own children), so this stays a clean
  /// "top-level thinking card" predicate everywhere it's used.
  bool _isThinkingMessage(int index) {
    if (index < 0 || index >= _model.messages.length) return false;
    if (_isSubagentMessage(index)) return false;
    return custom_widgets.isThinkingMessage(_model.messages[index]);
  }

  /// Whether the block VISIBLE above [index] is a bordered block — a tool-use
  /// row, a collapsed tool-use run, or a sub-agent group. Those blocks own the
  /// [kChatBlockGap] beneath them, so the block below adds no top margin and
  /// the two are separated by exactly one gap.
  ///
  /// Walks past messages that draw nothing, because they contribute no margins
  /// either: answering about them instead of the block on screen is what makes
  /// a gap silently double.
  ///
  /// A sub-agent-tagged index answers true without any walk — whether it's the
  /// anchor (which draws the group box right there) or a later member (whose
  /// anchor drew that box above), the visible neighbour is that box.
  bool _followsBorderedBlock(int index) {
    for (int i = index; i >= 0; i--) {
      if (_isSubagentMessage(i)) return true;
      // A thinking card is a bordered block too — it draws its box right at its
      // own index, so the visible neighbour above is that box.
      if (_isThinkingMessage(i)) return true;
      if (_rendersNothing(i)) continue;
      final m = _model.messages[i];
      final sender = m['sender_type']?.toString().toLowerCase() ?? '';
      if (sender == 'user' || sender == 'human') return false;
      return _isToolUseMessage(
          _model.sanitizeMessageContent(m['content']?.toString() ?? ''));
    }
    return false;
  }

  /// Index of the next message at/after [from] that actually renders
  /// something on screen at its own position, or null if none does. Skips
  /// every index that draws nothing there: a sub-agent group's hidden
  /// non-anchor members (drawn by an anchor ABOVE, not about to appear here),
  /// a collapsed tool-use run's hidden continuation rows (drawn by the run's
  /// start, same reasoning), and messages whose content sanitizes to empty
  /// with nothing else to show.
  ///
  /// Shared by every forward-looking neighbour check
  /// ([_precedesSubagentGroup], [_precedesBorderedBlock]) so they can't drift
  /// out of sync with each other or with what `_buildMessage` actually
  /// renders at each index — a real risk here, since `_buildMessage` has two
  /// independent early returns (`_isSubagentMessage`, collapsed tool-use run)
  /// that both mean "renders nothing," and a walk that only knows about one
  /// of them stops early and wrongly concludes the next visible thing is
  /// whatever hidden message it happened to land on.
  int? _nextVisibleIndex(int from) {
    final collapseToolUseOn = FFAppState().setting.collapseToolUse;
    for (int i = from; i < _model.messages.length; i++) {
      if (_isSubagentMessage(i) && !_isSubagentRunStart(i)) continue;
      if (collapseToolUseOn &&
          _isCollapsibleToolUse(i) &&
          !_isCollapseRunStart(i)) {
        continue;
      }
      if (_rendersNothing(i)) continue;
      return i;
    }
    return null;
  }

  /// Whether the block VISIBLE below [index] is a sub-agent group — i.e. the
  /// next message that draws anything is a group anchor. The group owns its own
  /// gap above itself, so the block above must yield its bottom gap or the two
  /// would stack.
  bool _precedesSubagentGroup(int index) {
    final next = _nextVisibleIndex(index);
    return next != null && _isSubagentRunStart(next);
  }

  /// Whether the block VISIBLE below [index] is itself bordered — a tool-use
  /// row/run or a sub-agent group — rather than plain text. Used to pick the
  /// wide bordered-to-bordered gap over the narrower gap against plain
  /// content; see `chat_block_spacing.dart`.
  bool _precedesBorderedBlock(int index) {
    final next = _nextVisibleIndex(index);
    if (next == null) return false;
    if (_isSubagentRunStart(next)) return true;
    // A thinking card below is bordered too (wide bordered-to-bordered gap).
    if (_isThinkingMessage(next)) return true;
    final m = _model.messages[next];
    final sender = m['sender_type']?.toString().toLowerCase() ?? '';
    if (sender == 'user' || sender == 'human') return false;
    return _isToolUseMessage(
        _model.sanitizeMessageContent(m['content']?.toString() ?? ''));
  }

  /// Whether message[index] draws nothing at all: a user message still staged
  /// in the send queue (or cancelled before the agent took it), or one whose
  /// content sanitizes to empty with no attachment and no question panel to
  /// render in its place. Mirrors the two early returns in [_buildMessage].
  bool _rendersNothing(int index) {
    if (index < 0 || index >= _model.messages.length) return false;
    final m = _model.messages[index];
    final sender = m['sender_type']?.toString().toLowerCase() ?? '';
    final isUser = sender == 'user' || sender == 'human';
    if (isUser) {
      final status = queueStatus(m);
      if (status == kQueueStatusQueued || status == kQueueStatusCancelled) {
        return true;
      }
    }
    if (_model.sanitizeMessageContent(m['content']?.toString() ?? '').isNotEmpty) {
      return false;
    }
    final metadata = m['message_metadata'];
    if (metadata is Map &&
        metadata['attachments'] is List &&
        (metadata['attachments'] as List).isNotEmpty) {
      return false;
    }
    final messageId = m['id']?.toString() ?? '';
    return isUser ||
        parseAskUserQuestionPayload(m) == null ||
        messageId.isEmpty;
  }

  /// True only at the FIRST index in the whole messages list carrying this
  /// sub-agent's tool_use_id — the anchor at which its group renders. Unlike
  /// [_isCollapseRunStart], this is NOT "previous index isn't part of the
  /// run": parallel sub-agents can interleave their child messages (A, B, A,
  /// B, ...), so the anchor is simply first-occurrence-by-id, wherever that
  /// falls in the list.
  bool _isSubagentRunStart(int index) => _subagentGrouping.isRunStart(index);

  /// All indices in the messages list sharing [startIndex]'s sub-agent
  /// tool_use_id, in list order. May be non-contiguous when sub-agents run in
  /// parallel and their messages interleave with another sub-agent's (or the
  /// parent's) messages.
  List<int> _collectSubagentRunIndices(int startIndex) =>
      _subagentGrouping.runIndices(startIndex);

  /// A tool-use message that ends with a fused code block acts as a group
  /// terminator — it should not join with what follows.
  bool _toolUseHasTrailingCodeBlock(String content) {
    if (!_isToolUseMessage(content)) return false;
    final lines = content.split('\n');
    if (lines.length < 2) return false;
    final remaining = lines.sublist(1).join('\n').trim();
    if (remaining.isEmpty) return false;
    // Check if remaining starts with a fenced code block marker (``` or ~~~)
    return RegExp(r'^\s*(`{3,}|~{3,})').hasMatch(remaining);
  }

  Widget _buildMessageContent(
    String content, {
    required bool isUser,
    required int messageIndex,
    required bool requiresUserInput,
    bool toolUseIsFirst = true,
    bool toolUseIsLast = true,
    bool isCancelled = false,
  }) {
    final rendered = formatTaskNotifications(content);
    Widget markdownContent = SelectionArea(
      child: custom_widgets.buildMarkdownText(
        context,
        rendered,
        isUser,
        requiresUserInput: requiresUserInput,
        onSendMessage: (text) async {
          _requestAutoScrollForNextMessages();
          await _model.sendMessage(context, text, isOptionClick: true);
        },
        filterProjectRoot: _model.filterProjectRootFromContent,
        agentTypeName: _model.instanceData?['agent_type_name'] ??
            widget.instanceData?['agent_type_name'],
        toolUseIsFirst: toolUseIsFirst,
        toolUseIsLast: toolUseIsLast,
      ),
    );

    if (!isUser) return markdownContent;

    // Cancelled queued messages render struck-through + faded so it reads as
    // "withdrawn" without hiding what was said. The ambient DefaultTextStyle
    // decoration is picked up by the markdown builder's Text.rich spans that
    // don't set their own `decoration`.
    if (isCancelled) {
      markdownContent = Opacity(
        opacity: 0.55,
        child: DefaultTextStyle.merge(
          style: const TextStyle(decoration: TextDecoration.lineThrough),
          child: markdownContent,
        ),
      );
    }

    return _CollapsibleUserMessage(
      fadeColor: Color.alphaBlend(
        FlutterFlowTheme.of(context).secondaryText.withValues(
          alpha: Theme.of(context).brightness == Brightness.light ? 0.08 : 0.15,
        ),
        FlutterFlowTheme.of(context).secondaryBackground,
      ),
      iconColor: FlutterFlowTheme.of(context).secondaryText,
      child: markdownContent,
    );
  }

  // ---- Welcome demo CTA handling -----------------------------------------
  // Logic lives in WelcomeDemoChatActions to keep this file lean.

  WelcomeDemoChatActions get _demoActions =>
      WelcomeDemoChatActions(appendMessage: _model.appendDemoMessage);

  bool _isWelcomeCtaMessage(dynamic message) {
    if (!isWelcomeDemoInstance(widget.instanceId)) return false;
    final metadata = message is Map ? message['message_metadata'] : null;
    return metadata is Map && metadata[kWelcomeCtaMetadataKey] == true;
  }

  Future<void> _handleDemoSetupCli() async {
    if (_demoCtaBusy) return;
    safeSetState(() => _demoCtaBusy = true);
    await _demoActions.setUpCli();
    if (!mounted) return;
    safeSetState(() => _demoCtaBusy = false);
  }

  Future<void> _handleDemoNoComputer() async =>
      _demoActions.showWaitlistQuestion();

  Future<void> _handleDemoWaitlistSubmit(
      AskUserQuestionSubmitPayload payload) async {
    final answer = payload.displayAnswers?.isNotEmpty == true
        ? (payload.displayAnswers!.first['label'] ?? '').trim()
        : '';
    _demoActions.submitWaitlist(answer);
  }

  Widget _buildMessageActionsRow(dynamic message) {
    return Container(
      margin: const EdgeInsetsDirectional.fromSTEB(0.0, 6.0, 0.0, 0.0),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildActionIcon(
            icon: Icons.copy_rounded,
            onTap: () => _copyAgentMessagesFromLastUser(message),
            tooltip: AppLocalizations.of(context).agentChatCopyResponse,
          ),
          const SizedBox(width: 4.0),
          _buildActionIcon(
            icon: Icons.ios_share_rounded,
            onTap: () async => await _shareAgentMessagesFromLastUser(message),
            tooltip: AppLocalizations.of(context).agentChatShareResponse,
          ),
        ],
      ),
    );
  }

  Widget _buildActionIcon({
    required IconData icon,
    required VoidCallback onTap,
    required String tooltip,
  }) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          onTap: () {
            HapticFeedback.lightImpact();
            onTap();
          },
          child: Container(
            width: 28.0,
            height: 28.0,
            child: Icon(
              icon,
              size: 18.0,
              color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.7),
            ),
          ),
        ),
      ),
    );
  }

  /// The staged (queued-behind-a-busy-agent) user messages, oldest first, for
  /// the queue bar above the input. Skips anything that sanitizes to empty so
  /// the bar never shows a blank row. The backend flips these to `consumed`
  /// when the agent picks them up, at which point they leave this list and
  /// render in the transcript instead.
  List<QueuedMessageEntry> _collectQueuedMessages() {
    final result = <QueuedMessageEntry>[];
    for (final message in _model.messages) {
      final senderType = message['sender_type']?.toString().toLowerCase() ?? '';
      final isUser = senderType == 'user' || senderType == 'human';
      if (!isUser) continue;
      if (queueStatus(message) != kQueueStatusQueued) continue;
      // Control/artifact commands (permission, model, thinking, AskUserQuestion
      // submit/summary) get stamped `queued` too but are never consumed — keep
      // these phantoms out of the bar (mirrors the web queue-bar filter).
      if (isControlOrArtifactMessage(message)) continue;
      final id = message['id']?.toString() ?? '';
      if (id.isEmpty) continue;
      // Inline option / permission responses ("Always allow", etc.) unblock the
      // current turn but get stamped `queued` and never consumed — keep these
      // phantoms out of the bar (see AgentChatModel.optionResponseMessageIds).
      if (_model.optionResponseMessageIds.contains(id)) continue;
      final text = _model
          .sanitizeMessageContent(message['content']?.toString() ?? '')
          .trim();
      if (text.isEmpty) continue;
      result.add(QueuedMessageEntry(id: id, text: text));
    }
    return result;
  }

  void _openQueueSheet() {
    showQueuedMessagesSheet(
      context: context,
      revision: _queueRevision,
      itemsProvider: _collectQueuedMessages,
      isCancelling: (id) => _cancellingMessageIds.contains(id),
      onCancel: _cancelQueuedMessage,
      onRevert: _revertQueuedMessage,
    );
  }

  /// Pulls a still-queued message back into the composer for editing: appends
  /// its text below any in-progress draft (newline-separated, so a half-typed
  /// message is never clobbered), focuses the input, then cancels the queued
  /// copy on the backend. The composer is filled first — before the cancel POST
  /// — so the text survives even if that request is slow or fails. Mirrors the
  /// web queue's "Edit in input" affordance.
  Future<void> _revertQueuedMessage(String messageId, String text) async {
    if (messageId.isEmpty) return;
    final controller = _model.messageController;
    final current = controller.text;
    final separator = current.isEmpty ? '' : '\n';
    controller.text = '$current$separator$text';
    controller.selection = TextSelection.fromPosition(
      TextPosition(offset: controller.text.length),
    );
    _model.filterSlashCommands(controller.text);
    _model.filterFileMentions(controller.text);
    safeSetState(() {});
    _model.messageFocusNode.requestFocus();
    await _cancelQueuedMessage(messageId);
  }

  /// Fires the cancel POST for a still-queued message. Guards double-tap via
  /// [_cancellingMessageIds]; the message drops out of [_collectQueuedMessages]
  /// once the WS message-update patch lands (see
  /// [AgentChatModel.messageMetadataRevision]), so this only needs to manage
  /// the in-flight spinner, not the end state. Bumps [_queueRevision] so an
  /// open queue sheet reflects the spinner immediately.
  Future<void> _cancelQueuedMessage(String messageId) async {
    if (messageId.isEmpty || _cancellingMessageIds.contains(messageId)) return;
    safeSetState(() => _cancellingMessageIds.add(messageId));
    _queueRevision.value++;
    HapticFeedback.lightImpact();
    final cancelled = await actions.apiCancelQueuedMessage(widget.instanceId, messageId);
    if (!cancelled) {
      debugPrint('Cancel request for queued message $messageId was not accepted');
    }
    if (!mounted) return;
    safeSetState(() => _cancellingMessageIds.remove(messageId));
    _queueRevision.value++;
  }

  List<String> _collectAgentResponsesForActions(dynamic currentMessage) {
    final currentIndex =
        _model.messages.indexWhere((msg) => msg['id'] == currentMessage['id']);
    if (currentIndex == -1) {
      return const [];
    }

    int lastUserIndex = -1;
    for (int i = currentIndex - 1; i >= 0; i--) {
      final senderType =
          _model.messages[i]['sender_type']?.toString().toLowerCase() ?? '';
      if (senderType == 'user' || senderType == 'human') {
        lastUserIndex = i;
        break;
      }
    }

    final startIndex = lastUserIndex == -1 ? 0 : lastUserIndex + 1;
    final agentMessages = <String>[];

    for (int i = startIndex; i <= currentIndex; i++) {
      final message = _model.messages[i];
      final senderType = message['sender_type']?.toString().toLowerCase() ?? '';
      final isAgentMessage = senderType == 'assistant' || senderType == 'agent';

      if (!isAgentMessage) {
        continue;
      }

      final rawContent = message['content']?.toString() ?? '';
      final sanitizedContent = _model.sanitizeMessageContent(rawContent);
      final filteredContent = _model.filterProjectRootFromContent(sanitizedContent);
      if (filteredContent.trim().isNotEmpty) {
        agentMessages.add(filteredContent);
      }
    }

    return agentMessages;
  }

  void _copyAgentMessagesFromLastUser(dynamic currentMessage) {
    try {
      final agentMessages = _collectAgentResponsesForActions(currentMessage);
      if (agentMessages.isEmpty) {
        return;
      }

      final combinedText = agentMessages.join('\n\n');
      Clipboard.setData(ClipboardData(text: combinedText));

      final copyMessage =
          AppLocalizations.of(context).agentChatCopiedToClipboard(agentMessages.length);
      _showSnackBarMessage(copyMessage);
    } catch (e) {
      debugPrint('Error copying messages: $e');
      _showSnackBarMessage(AppLocalizations.of(context).agentChatCopyFailed, waitTime: 2000);
    }
  }

  Future<void> _shareAgentMessagesFromLastUser(dynamic currentMessage) async {
    try {
      final agentMessages = _collectAgentResponsesForActions(currentMessage);
      if (agentMessages.isEmpty) {
        return;
      }

      final combinedText = agentMessages.join('\n\n');
      await SharePlus.instance.share(
        ShareParams(
          text: combinedText,
          subject: 'Vibe Code Anywhere (Vicoa) Chat',
        ),
      );
    } catch (e) {
      debugPrint('Error sharing messages: $e');
      _showSnackBarMessage(AppLocalizations.of(context).agentChatShareFailed, waitTime: 2000);
    }
  }

  Widget _buildTypingIndicator() {
    return RepaintBoundary(
      child: Container(
      margin: const EdgeInsetsDirectional.fromSTEB(16.0, 6.0, 16.0, 6.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Flexible(
            child: Container(
              padding: const EdgeInsetsDirectional.fromSTEB(8.0, 12.0, 16.0, 12.0),
              decoration: BoxDecoration(
                color: FlutterFlowTheme.of(context).secondaryBackground,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(20.0),
                  topRight: Radius.circular(20.0),
                  bottomLeft: Radius.circular(20.0),
                  bottomRight: Radius.circular(20.0),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Vibing message text with wave animation
                  VibingTextWidget(
                    message: _currentVibingMessage,
                    textColor: FlutterFlowTheme.of(context).secondaryText.withValues(
                          alpha: Theme.of(context).brightness == Brightness.dark
                              ? 0.6
                              : 1.0,
                        ),
                    fontSize: 16.0,
                  ),
                  // const SizedBox(width: 8.0),
                  // Animated dots
                  // _buildTypingDot(0),
                  // const SizedBox(width: 4.0),
                  // _buildTypingDot(1),
                  // const SizedBox(width: 4.0),
                  // _buildTypingDot(2),
                ],
              ),
            ),
          ),
        ],
      ),
    ),
    );
  }


  Widget _buildDateSeparator(String date) {
    return RepaintBoundary(
      child: Container(
      margin: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 8.0),
      child: Center(
        child: Container(
          padding: const EdgeInsetsDirectional.fromSTEB(12.0, 6.0, 12.0, 6.0),
          decoration: BoxDecoration(
            color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(16.0),
          ),
          child: Text(
            date,
            style: FlutterFlowTheme.of(context).bodySmall.override(
              color: FlutterFlowTheme.of(context).secondaryText,
              fontSize: 12.0,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ),
    ),
    );
  }

  bool _isLastAgentResponseInGroup(int index) {
    return _isLastAgentMessageCache[index] ?? false;
  }

  bool _computeIsLastAgentResponseInGroup(int index) {
    if (index < 0 || index >= _model.messages.length) {
      return false;
    }

    final message = _model.messages[index];
    final senderType = message['sender_type']?.toString().toLowerCase() ?? '';
    final isAgentMessage = senderType == 'assistant' || senderType == 'agent';

    if (!isAgentMessage) {
      return false;
    }

    // Check if this is the last agent message in the group
    bool isLastInGroup = false;
    for (int i = index + 1; i < _model.messages.length; i++) {
      final nextSender = _model.messages[i]['sender_type']?.toString().toLowerCase() ?? '';

      if (nextSender == 'assistant' || nextSender == 'agent') {
        return false;
      }

      if (nextSender == 'user' || nextSender == 'human') {
        isLastInGroup = true;
        break;
      }
    }

    // If no user message follows, this is the last message
    if (!isLastInGroup) {
      isLastInGroup = true;
    }

    // Use cached last user message index instead of scanning again
    final lastUserMessageIndex = _cachedLastUserMessageIndex;

    // If this message is BEFORE the last user message, always show buttons (it's completed)
    if (lastUserMessageIndex != null && index < lastUserMessageIndex) {
      return isLastInGroup;
    }

    // If this message is AFTER the last user message, only show if the agent
    // isn't actively working (matches the typing-indicator state).
    return isLastInGroup && !_shouldShowTypingIndicator;
  }






  /// Field from the live model, falling back to the value we were routed with.
  String? _instanceField(String key) {
    final v = (_model.instanceData is Map) ? (_model.instanceData as Map)[key] : null;
    if (v != null) return v.toString();
    final w = (widget.instanceData is Map) ? (widget.instanceData as Map)[key] : null;
    return w?.toString();
  }

  /// Raw map field from the live model, falling back to the routed value.
  /// Distinct from [_instanceField], which stringifies — a Map would come back
  /// as "{agent: kimi, ...}" and every lookup into it would miss.
  Map<String, dynamic>? _instanceMap(String key) {
    for (final source in [_model.instanceData, widget.instanceData]) {
      final v = (source is Map) ? source[key] : null;
      if (v is Map) return Map<String, dynamic>.from(v);
    }
    return null;
  }

  /// Server-derived liveness ("live" / "agent_stopped" / "machine_offline" /
  /// "unknown"). Derived rather than stored, so it reflects the heartbeats at
  /// fetch time; see shared/database/liveness.py.
  String? _liveState() => _instanceField('live_state');

  bool _canResumeSession() => actions.canResumeSession(
        status: _instanceField('status'),
        machineId: _instanceField('machine_id'),
        project: _instanceField('project'),
        liveState: _liveState(),
      );

  String? _resumeBlockedReason() => actions.resumeBlockedReason(
        status: _instanceField('status'),
        machineId: _instanceField('machine_id'),
        project: _instanceField('project'),
        liveState: _liveState(),
      );

  Future<void> _handleResumeSession() async {
    final l10n = AppLocalizations.of(context);
    final machineId = _instanceField('machine_id') ?? '';
    final project = _instanceField('project') ?? '';
    final metadata = _instanceMap('instance_metadata');
    final result = await actions.apiResumeSession(
      machineId,
      widget.instanceId ?? (_instanceField('id') ?? ''),
      actions.resumeExpandProjectPath(project, _instanceField('home_dir')),
      agent: actions.resumeAgentSlug(
        _instanceField('agent_type_name'),
        sessionConfig: _instanceMap('session_config'),
      ),
      agentSessionId: actions.resumeAgentSessionHandle(metadata),
      // Carry the stored model / effort / permission mode through so the
      // resumed session isn't reset to the daemon's defaults.
      sessionConfig: _instanceMap('session_config'),
    );
    if (!mounted) return;
    if (result['success'] != true) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(result['error']?.toString() ?? l10n.sessionResumeFailed)));
      return;
    }
    // Open a resume grace so both the composer and the home-list dot treat the
    // session as reachable while the relaunched agent comes up. Keyed by
    // instance id in a shared registry (not on instanceData, which the
    // loadMessages refetch replaces wholesale) so the home card sees it too.
    final resumedId = widget.instanceId ?? (_instanceField('id') ?? '');
    actions.markResumed(resumedId);
    // Reopen the cached status too, so the row doesn't read as archived in the
    // brief window before the refetch returns.
    _setLocalSessionStatus('AWAITING_INPUT', liveState: 'live');
    safeSetState(() {});

    // Re-fetch and restart the message stream. The old stream belonged to the
    // agent that exited, so nothing was listening for the resumed agent's
    // replies — the first answer only appeared after navigating away and back,
    // which ran exactly this. Subsequent messages worked because the send path
    // re-establishes the stream itself.
    if (!_model.isLoadingMessages) {
      await _model.loadMessages(hasCachedData: _model.messages.isNotEmpty);
      if (mounted) safeSetState(() {});
    }
  }

  Future<void> _showChatOptionsMenu() async {
    if (_isChatOptionsMenuOpen) return;

    final RenderBox? buttonRenderBox =
        _chatOptionsButtonKey.currentContext?.findRenderObject() as RenderBox?;
    final OverlayState? overlayState = Overlay.of(context);
    if (buttonRenderBox == null || overlayState == null) return;

    final RenderBox overlayRenderBox =
        overlayState.context.findRenderObject() as RenderBox;

    final Offset buttonTopRight = buttonRenderBox.localToGlobal(
      buttonRenderBox.size.topRight(Offset.zero),
      ancestor: overlayRenderBox,
    );
    final Offset buttonBottomRight = buttonRenderBox.localToGlobal(
      buttonRenderBox.size.bottomRight(Offset.zero),
      ancestor: overlayRenderBox,
    );

    const double menuWidth = 140.0;
    const double horizontalGap = 8.0;
    const double verticalGap = 8.0;
    const double screenPadding = 16.0;

    final double overlayWidth = overlayRenderBox.size.width;
    double left = buttonTopRight.dx + horizontalGap;
    final double top = buttonBottomRight.dy + verticalGap;

    if (left + menuWidth > overlayWidth - screenPadding) {
      left = overlayWidth - menuWidth - screenPadding;
    }
    if (left < screenPadding) {
      left = screenPadding;
    }

    final showCloseOption = !['CLOSED', 'COMPLETED'].contains(
      (_model.instanceData?['status'] as String? ?? '').toUpperCase(),
    );

    if (mounted) safeSetState(() => _isChatOptionsMenuOpen = true);

    await showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
      barrierColor: Colors.transparent,
      transitionDuration: const Duration(milliseconds: 180),
      pageBuilder: (dialogContext, _, __) {
        return Stack(
          children: [
            Positioned(
              left: left,
              top: top,
              width: menuWidth,
              child: Material(
                color: Colors.transparent,
                child: custom_widgets.ChatOptionsMenu(
                  showCloseOption: showCloseOption,
                  showResumeOption: _canResumeSession(),
                  resumeDisabledReason: _resumeBlockedReason(),
                  onResume: () {
                    Navigator.of(dialogContext).pop();
                    _handleResumeSession();
                  },
                  isPinned: _isInstancePinned(),
                  onPin: () {
                    Navigator.of(dialogContext).pop();
                    _handlePinToggle();
                  },
                  onInfo: () {
                    Navigator.of(dialogContext).pop();
                    _showSessionInfoSheet();
                  },
                  onShare: () {
                    Navigator.of(dialogContext).pop();
                    _shareConversation();
                  },
                  onRename: () {
                    Navigator.of(dialogContext).pop();
                    _showRenameDialog();
                  },
                  onClose: () {
                    Navigator.of(dialogContext).pop();
                    _showCloseConfirmation();
                  },
                  onDelete: () {
                    Navigator.of(dialogContext).pop();
                    _showDeleteConfirmation();
                  },
                ),
              ),
            ),
          ],
        );
      },
      transitionBuilder: (ctx, animation, _, child) {
        final curved = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
          reverseCurve: Curves.easeInCubic,
        );
        return FadeTransition(
          opacity: curved,
          child: ScaleTransition(
            scale: Tween<double>(begin: 0.88, end: 1.0).animate(curved),
            alignment: Alignment.topRight,
            child: child,
          ),
        );
      },
    );

    if (mounted) safeSetState(() => _isChatOptionsMenuOpen = false);
  }

  Future<void> _showSnackBarMessage(String message, {int waitTime = 2000}) async {
    if (!mounted) {
      return;
    }
    await SessionActions.showSnack(context, message, waitTime: waitTime);
  }

  void _shareConversation() async {
    if (_model.messages.isEmpty) {
      await _showSnackBarMessage(AppLocalizations.of(context).agentChatNoMessagesToShare);
      return;
    }

    logFirebaseEvent('AGENT_CHAT_share_conversation');
    
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: true,
      builder: (context) => MessageSelectionSheetWidget(
        messages: _model.messages,
        onShareSelected: (selectedMessages) async {
          if (selectedMessages.isEmpty) {
            await _showSnackBarMessage(AppLocalizations.of(context).agentChatNoMessagesSelected);
            return;
          }
          
          // Show export options sheet
          await showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            backgroundColor: Colors.transparent,
            isDismissible: true,
            enableDrag: true,
            builder: (context) => ShareOptionsSheetWidget(
              selectedMessages: selectedMessages,
            ),
          );
        },
      ),
    );
  }

  Future<void> _showSessionInfoSheet() async {
    final data = _model.instanceData ?? widget.instanceData;
    await SessionActions.showSessionInfo(
      context,
      instanceId: widget.instanceId,
      instanceData: data,
      firebaseEventName: 'AGENT_CHAT_session_info_open',
      onTitleChanged: (newName) {
        if (_model.instanceData != null) {
          _model.instanceData!['name'] = newName;
        }
        if (widget.instanceData != null) {
          widget.instanceData['name'] = newName;
        }
        _model.sessionChangeType = 'renamed';
        if (mounted) safeSetState(() {});
      },
    );
  }

  Future<void> _showRenameDialog() async {
    final currentName =
        (_model.instanceData?['name']?.toString().isNotEmpty == true)
            ? _model.instanceData!['name'] as String
            : (widget.instanceData?['name']?.toString().isNotEmpty == true)
                ? widget.instanceData!['name'] as String
                : '';

    await SessionActions.renameSession(
      context,
      instanceId: widget.instanceId,
      currentName: currentName,
      firebaseEventName: 'AGENT_CHAT_rename_session',
      onSuccess: (newName) async {
        if (_model.instanceData != null) {
          _model.instanceData!['name'] = newName;
        }
        if (widget.instanceData != null) {
          widget.instanceData['name'] = newName;
        }
        _model.sessionChangeType = 'renamed';
        if (mounted) safeSetState(() {});
        await _showSnackBarMessage(AppLocalizations.of(context).agentChatSessionRenamed);
      },
      onFailure: () async {
        await _showSnackBarMessage(
            AppLocalizations.of(context).agentChatRenameFailed,
            waitTime: 2000);
      },
    );
  }

  Future<void> _showCloseConfirmation() async {
    await SessionActions.closeSession(
      context,
      instanceId: widget.instanceId,
      firebaseEventName: 'AGENT_CHAT_close_session_confirmed',
      onSuccess: () async {
        _setLocalSessionStatus('COMPLETED');
        _model.sessionChangeType = 'closed';
        if (mounted) context.pop(_model.sessionChangeType);
      },
      onFailure: () async {
        await _showSnackBarMessage(
            AppLocalizations.of(context).agentChatCloseFailed,
            waitTime: 2000);
      },
    );
  }

  Future<void> _showDeleteConfirmation() async {
    await SessionActions.deleteSession(
      context,
      instanceId: widget.instanceId,
      firebaseEventName: 'AGENT_CHAT_delete_session_confirmed',
      onSuccess: () async {
        _model.clearDraftMessage();
        if (mounted) context.pop('deleted');
      },
      onFailure: () async {
        await _showSnackBarMessage(
            AppLocalizations.of(context).agentChatDeleteFailed,
            waitTime: 2000);
      },
    );
  }


  void _navigateBack() {
    // Check if we can pop (i.e., there's a previous route in the stack)
    if (Navigator.of(context).canPop()) {
      // Normal navigation - pop with result
      context.pop(_model.sessionChangeType);
    } else {
      // No navigation stack (e.g., came from push notification)
      context.goNamed(
        HomeWidget.routeName,
        extra: <String, dynamic>{
          kTransitionInfoKey: const TransitionInfo(
            hasTransition: true,
            transitionType: PageTransitionType.leftToRight,
            duration: Duration(milliseconds: 220),
          ),
        },
      );
    }
  }


  Widget _buildNewMessagesBanner() {
    if (!_showNewMessagesBanner) return const SizedBox.shrink();

    // Use the model's saved last-seen index first; fall back to the locally
    // recorded base index captured when new messages first arrived.
    final lastSeenIndex = _model.getLastSeenMessageIndex() ?? _newMessagesBannerBaseIndex;
    if (lastSeenIndex == null || lastSeenIndex < 0) return const SizedBox.shrink();

    final newMessagesCount = _model.messages.length - lastSeenIndex - 1;
    if (newMessagesCount <= 0) return const SizedBox.shrink();

    return Positioned(
      top: 12.0,
      right: 0.0,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            HapticFeedback.lightImpact();
            _hasUserInteractedWithList = true;
            setState(() {
              _showNewMessagesBanner = false;
              _newMessagesBannerBaseIndex = null;
            });
            // Scroll to the first new message (the one after last seen)
            _scrollToMessageByIndex(lastSeenIndex + 1);
          },
          child: Container(
            padding: const EdgeInsetsDirectional.fromSTEB(10.0, 10.0, 10.0, 10.0),
            decoration: BoxDecoration(
              color: FlutterFlowTheme.of(context).primaryBackground,
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(20.0),
                topRight: Radius.circular(0.0),
                bottomLeft: Radius.circular(20.0),
                bottomRight: Radius.circular(0.0),
              ),
              border: Border.all(
                color: FlutterFlowTheme.of(context)
                    .secondaryText
                    .withValues(alpha: 0.25),
                width: 0.75,
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.15),
                  blurRadius: 10.0,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.unfold_more_rounded,
                  color: FlutterFlowTheme.of(context).primaryText,
                  size: 16.0,
                ),
                const SizedBox(width: 3.0),
                Text(
                  AppLocalizations.of(context)
                      .agentChatNewMessagesCount(newMessagesCount),
                  style: FlutterFlowTheme.of(context).bodyMedium.override(
                    color: FlutterFlowTheme.of(context).primaryText,
                    fontSize: 15.0,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                // const SizedBox(width: 8.0),
                // Icon(
                //   Icons.close_rounded,
                //   color: FlutterFlowTheme.of(context).info.withValues(alpha: 0.7),
                //   size: 16.0,
                // ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _handleSlashCommandSelect(SlashCommand command) async {
    HapticFeedback.lightImpact();

    if (_model.isSendingMessage) {
      return;
    }

    _model.insertSlashCommand(command.command, insertText: command.insert);
    if (mounted) safeSetState(() {});
  }

  // Pushes the Files screen for the current session. Null when the session
  // pre-dates the machine_id column — folder button stays hidden in that case.
  // If the user picks "Add to context" inside the viewer, FilesScreen forwards
  // the result here and we drop `@<path> ` into the chat input.
  VoidCallback? _openFilesCallback() {
    final machineId = (_model.instanceData?['machine_id'] ?? widget.instanceData?['machine_id'])?.toString();
    if (machineId == null || machineId.isEmpty) return null;
    final cwd = (_model.instanceData?['project'] ?? widget.instanceData?['project'])?.toString() ?? '';
    final projectName = (_model.instanceData?['name'] ?? widget.instanceData?['name'])?.toString();
    return () async {
      final result = await context.pushNamed(
        FilesScreenWidget.routeName,
        extra: <String, dynamic>{
          'machineId': machineId,
          'cwd': cwd,
          if (projectName != null) 'projectName': projectName,
        },
      );
      if (!mounted) return;
      if (result is Map && result[kFileViewerAddToContextKey] is String) {
        final relPath = result[kFileViewerAddToContextKey] as String;
        final mention = '@$relPath ';
        final controller = _model.messageController;
        final current = controller.text;
        // Append a space if the user already had non-trailing-space text so
        // the mention doesn't fuse with whatever was there.
        final separator = current.isEmpty || current.endsWith(' ') ? '' : ' ';
        controller.text = '$current$separator$mention';
        controller.selection = TextSelection.fromPosition(
          TextPosition(offset: controller.text.length),
        );
        _model.filterFileMentions(controller.text);
        safeSetState(() {});
      }
    };
  }



  @override
  Widget build(BuildContext context) {
    DebugFlutterFlowModelContext.maybeOf(context)
        ?.parentModelCallback
        ?.call(_model);

    // Use cached values to avoid recomputation on every rebuild (especially during keyboard transitions)
    final agentTypeName = _cachedAgentTypeName ?? (_model.instanceData?['agent_type_name'] ?? widget.instanceData?['agent_type_name'] ?? '').toString();
    final supportsControlSettings = _cachedSupportsControlSettings ?? agentTypeName.toLowerCase().contains('claude');

    // Claude's bypassPermissions is sticky in the interactive CLI — its
    // Shift+Tab cycle can't reach YOLO unless the session launched in it — so
    // the TUI wrapper can't be switched into YOLO mid-session and the sheet
    // hides it there. Headless (daemon-spawned) sessions set it through the
    // SDK's set_permission_mode, so they can switch in freely:
    // `instance_metadata.source == 'app'` marks those (the TUI wrapper stamps
    // "terminal"). A session already running in YOLO always keeps the entry so
    // the sheet can label its own current value.
    // `hasRemoteSessionStartMessage` only still matches sessions started before
    // June 2026, when headless spawns stopped sending that bootstrap prompt —
    // relying on it alone is what hid YOLO from every remote Claude session.
    final showYoloMode = functions.hasInitialBypassPermissionMode(_model.messages) ||
        functions.hasRemoteSessionStartMessage(_model.messages) ||
        _instanceMap('instance_metadata')?['source'] == 'app' ||
        _instanceMap('session_config')?['permission_mode'] == 'bypassPermissions';


    return Builder(
      builder: (context) {
        final keyboardVisible = MediaQuery.of(context).viewInsets.bottom > 0;
        final bottomSpacerHeight = keyboardVisible ? 12.0 : 18.0;

        return GestureDetector(
          onTap: () {
            // Always unfocus when tapping outside, including ask user question input
            FocusScope.of(context).unfocus();
            FocusManager.instance.primaryFocus?.unfocus();
          },
          onHorizontalDragEnd: (details) {
            // Detect left swipe (positive velocity means left-to-right swipe)
            if (details.primaryVelocity != null && details.primaryVelocity! > 300) {
              HapticFeedback.lightImpact();
              _navigateBack();
            }
          },
          child: Scaffold(
            key: scaffoldKey,
            resizeToAvoidBottomInset: true,
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
                  // buttonSize: 40.0,
                  // fillColor: FlutterFlowTheme.of(context).primaryBackground,
                  icon: Icon(
                    Icons.chevron_left_rounded,
                    color: FlutterFlowTheme.of(context).secondaryText,
                    size: 24.0,
                  ),
                  onPressed: () async {
                    logFirebaseEvent('AGENT_CHAT_back_btn_tap');
                    HapticFeedback.lightImpact();
                    _navigateBack();
                  },
                ),
              ),
            title: GestureDetector(
              onTap: () async {
                logFirebaseEvent('AGENT_CHAT_title_tap_scroll_to_top');
                HapticFeedback.lightImpact();
                _model.scrollToTop();
              },
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (_isInstancePinned()) ...[
                        Icon(
                          Icons.push_pin_rounded,
                          size: 14,
                          color: FlutterFlowTheme.of(context).secondaryText,
                        ),
                        const SizedBox(width: 4),
                      ],
                      Flexible(
                        child: AutoSizeText(
                          (_model.instanceData?['name']?.toString().isNotEmpty == true)
                            ? _model.instanceData!['name']
                            : (widget.instanceData?['name']?.toString().isNotEmpty == true)
                              ? widget.instanceData!['name']
                              : (_model.instanceData?['agent_type_name'] ?? widget.instanceData?['agent_type_name'] ?? AppLocalizations.of(context).agentChatSessionTitle),
                          textAlign: TextAlign.center,
                          overflow: TextOverflow.ellipsis,
                          maxLines: 1,
                          minFontSize: 15.0,
                          maxFontSize: 18.0,
                          style: FlutterFlowTheme.of(context).titleLarge.override(
                            fontFamily: GoogleFonts.sourceSans3().fontFamily,
                            color: FlutterFlowTheme.of(context).primaryText,
                            fontSize: 18.0,
                            letterSpacing: 0.0,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if ((_model.instanceData?['project'] ?? widget.instanceData?['project'])?.toString().isNotEmpty == true) ...[
                    const SizedBox(height: 2.0),
                    StartEllipsisText(
                      (_model.instanceData?['project'] ?? widget.instanceData?['project']).toString(),
                      textAlign: TextAlign.center,
                      style: FlutterFlowTheme.of(context).bodySmall.override(
                        fontFamily: GoogleFonts.sourceSans3().fontFamily,
                        color: FlutterFlowTheme.of(context).secondaryText,
                        fontSize: 13.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                    const SizedBox(height: 6.0),
                  ],
                ],
              ),
            ),
            actions: [
              Align(
                alignment: const AlignmentDirectional(-1.0, 0.0),
                child: Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 16.0, 0.0),
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(10.0),
                      onTap: () {
                        logFirebaseEvent('AGENT_CHAT_menu_btn_tap');
                        HapticFeedback.lightImpact();
                        _showChatOptionsMenu();
                      },
                      child: Container(
                        key: _chatOptionsButtonKey,
                        width: 40.0,
                        height: 40.0,
                        decoration: BoxDecoration(
                          // color: FlutterFlowTheme.of(context).primaryBackground,
                          // borderRadius: BorderRadius.circular(10.0),
                        ),
                        alignment: Alignment.center,
                        child: Icon(
                          Icons.more_horiz_rounded,
                          color: _isChatOptionsMenuOpen
                              ? FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5)
                              : FlutterFlowTheme.of(context).secondaryText,
                          size: 24.0,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
            centerTitle: true,
            elevation: 0.0,
          ),
          body: SafeArea(
            top: true,
            bottom: false,
            child: Column(
            children: [
                // Messages area
                Expanded(
                  child: RepaintBoundary(
                    child: Stack(
                    children: [
                      // Main messages list
                      _model.isLoadingMessages
                  ? Center(
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(
                          FlutterFlowTheme.of(context).primary,
                        ),
                      ),
                    )
                  : _model.hasError
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.error_outline,
                              size: 48.0,
                              color: FlutterFlowTheme.of(context).error,
                            ),
                            SizedBox(height: 16.0),
                            Text(
                              AppLocalizations.of(context).agentChatErrorLoadingMessages,
                              style: FlutterFlowTheme.of(context).titleMedium.override(
                                color: FlutterFlowTheme.of(context).error,
                                fontSize: 16.0,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            SizedBox(height: 8.0),
                            Padding(
                              padding: EdgeInsets.symmetric(horizontal: 32.0),
                              child: Text(
                                _model.errorMessage ?? AppLocalizations.of(context).agentChatUnexpectedError,
                                style: FlutterFlowTheme.of(context).bodyMedium.override(
                                  color: FlutterFlowTheme.of(context).error,
                                  fontSize: 14.0,
                                ),
                                textAlign: TextAlign.center,
                              ),
                            ),
                            SizedBox(height: 16.0),
                            FFButtonWidget(
                              onPressed: () async {
                                await _model.loadMessages();
                                if (mounted) {
                                  _lastKnownMessageCount =
                                      _model.messages.length;
                                  _isAtListBottom = true;
                                  _showNewMessagesBanner = false;
                                  _hasUserInteractedWithList = false;
                                  setState(() {});
                                  WidgetsBinding.instance.addPostFrameCallback((_) {
                                    if (!mounted) return;
                                    _scrollToBottom(animate: false);
                                  });
                                }
                              },
                              text: AppLocalizations.of(context).commonRetry,
                              icon: Icon(
                                Icons.refresh_rounded,
                                size: 18.0,
                              ),
                              options: FFButtonOptions(
                                height: 40.0,
                                padding: EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
                                iconPadding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 8.0, 0.0),
                                color: FlutterFlowTheme.of(context).error,
                                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                                  color: FlutterFlowTheme.of(context).primaryText,
                                  fontSize: 14.0,
                                  fontWeight: FontWeight.w500,
                                ),
                                elevation: 2.0,
                                borderSide: BorderSide(
                                  color: Colors.transparent,
                                  width: 1.0,
                                ),
                                borderRadius: BorderRadius.circular(8.0),
                              ),
                            ),
                          ],
                        ),
                      )
                    : _model.messages.isEmpty
                    // ? (widget.hasInitialPrompt
                    ? (widget.hasInitialPrompt
                        // Spawned with an initial prompt: the first message is
                        // on its way — show an active loading state instead of
                        // the static idle icon (see SessionLoadingIndicator).
                        ? SessionLoadingIndicator(
                            vibingMessage: _currentVibingMessage,
                          )
                        : Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            FaIcon(
                              FontAwesomeIcons.solidCommentDots,
                              size: 48.0,
                              color: FlutterFlowTheme.of(context).secondaryText,
                            ),
                            SizedBox(height: 16.0),
                            Text(
                              AppLocalizations.of(context).agentChatSessionReady,
                              style: FlutterFlowTheme.of(context).titleMedium.override(
                                color: FlutterFlowTheme.of(context).primaryText,
                                fontSize: 16.0,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            SizedBox(height: 8.0),
                            Text(
                              AppLocalizations.of(context).agentChatWaitingForMessages,
                              style: FlutterFlowTheme.of(context).bodyMedium.override(
                                color: FlutterFlowTheme.of(context).secondaryText,
                                fontSize: 14.0,
                              ),
                            ),
                          ],
                        ),
                      ))
                    : NotificationListener<ScrollNotification>(
                        onNotification: (scrollNotification) {
                          if (scrollNotification is ScrollStartNotification) {
                            // Dismiss keyboard only for user drag starts.
                            // Programmatic/layout scroll starts (e.g. keyboard/layout shifts) should not close input focus.
                            final isUserDragStart = scrollNotification.dragDetails != null;
                            if (isUserDragStart && !_isProgrammaticScroll) {
                              final keyboardVisible = MediaQuery.of(context).viewInsets.bottom > 0;
                              if (keyboardVisible) {
                                FocusScope.of(context).unfocus();
                              }
                            }
                            if (isUserDragStart && !_hasUserInteractedWithList && !_isProgrammaticScroll) {
                              _hasUserInteractedWithList = true;
                            }
                          }
                          return false;
                        },
                        child: ScrollablePositionedList.builder(
                          itemScrollController:
                              _model.itemScrollController,
                          itemPositionsListener:
                              _model.itemPositionsListener,
                          physics: _isAskUserQuestionInputFocused
                              ? const NeverScrollableScrollPhysics() // Lock scroll when typing
                              : null, // Default scroll physics otherwise
                          reverse: false, // Normal order: oldest at top, newest at bottom (no scroll drift!)
                          padding: const EdgeInsets.fromLTRB(
                            0.0,
                            16.0,
                            0.0,
                            16.0,
                          ),
                          itemCount: _listItemCount,
                          itemBuilder: (context, index) {
                            // With reverse:false, index = actual position (no conversion needed)
                            final actualIndex = index;
                            final hasTypingIndicator = _shouldShowTypingIndicator;
                            final typingIndex = _model.messages.length;
                            final spacerIndex = typingIndex + (hasTypingIndicator ? 1 : 0);

                            if (actualIndex < _model.messages.length) {
                              final message = _model.messages[actualIndex];
                              final messageId = message['id'] ?? actualIndex;
                              final dateLabel = _dateLabelForMessage(actualIndex);
                              final shouldShowActions =
                                  _isLastAgentResponseInGroup(actualIndex);

                              return Column(
                                key: ValueKey('message_$messageId'),
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (dateLabel != null)
                                    _buildDateSeparator(dateLabel),
                                  _buildMessage(
                                    message,
                                    messageIndex: actualIndex,
                                    isLastAgentMessage: shouldShowActions,
                                  ),
                                ],
                              );
                            }

                            if (hasTypingIndicator && actualIndex == typingIndex) {
                              return _buildTypingIndicator();
                            }

                            if (actualIndex == spacerIndex) {
                              return const SizedBox(height: _trailingSpacerHeight);
                            }

                            return const SizedBox.shrink();
                          },
                        ),
                      ),

                      // Floating scroll-to-bottom button
                      if (_showScrollToBottomButton || _showInitialDemoScrollHint)
                        Positioned(
                          bottom: 12.0,
                          left: 0,
                          right: 0,
                          child: Center(
                            child: Container(
                              width: 36.0,
                              height: 36.0,
                              decoration: BoxDecoration(
                                color: FlutterFlowTheme.of(context).primaryBackground,
                                borderRadius: BorderRadius.circular(18.0),
                                border: Theme.of(context).brightness ==
                                        Brightness.dark
                                    ? Border.all(
                                        color: FlutterFlowTheme.of(context)
                                            .secondaryText
                                            .withValues(alpha: 0.25),
                                        width: 0.75,
                                      )
                                    : null,
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.15),
                                    blurRadius: 8.0,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: Material(
                                color: Colors.transparent,
                                child: InkWell(
                                  borderRadius: BorderRadius.circular(18.0),
                                  onTap: () async {
                                    logFirebaseEvent('AGENT_CHAT_scroll_to_bottom_btn_tap');
                                    HapticFeedback.lightImpact();
                                    _hasUserInteractedWithList = true;
                                    _forceNextScroll = true; // Force scroll even if not at bottom
                                    _model.scrollToBottom(animate: true); // Use animation for smoother UX
                                    // Don't manually hide button - let _handleVisibleItemsChanged detect we're at bottom
                                  },
                                  child: Icon(
                                    Icons.arrow_downward_rounded,
                                    color: FlutterFlowTheme.of(context).primaryText,
                                    size: 18.0,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),

                      // Suggestions overlay (do not affect layout)
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 0,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            SlashCommandSuggestions(
                              visible: _model.showSlashCommandSuggestions,
                              commands: _model.filteredSlashCommands,
                              onCommandSelected: _handleSlashCommandSelect,
                            ),
                            FileMentionSuggestions(
                              mixin: _model,
                              onFileSelected: (_) {},
                            ),
                          ],
                        ),
                      ),

                      // New messages banner
                      _buildNewMessagesBanner(),

                      // Realtime degraded banner — floats at the bottom of
                      // the message list, just above the chat input, so it
                      // sits where the user's eyes are when composing.
                      // Suppressed once the session is closed: SSE intentionally
                      // disconnects then, so a reconnect banner would be noise.
                      // if (_model.realtimeDegraded &&
                      //     !functions.isSessionClosed(
                      //         widget.instanceData?['status']?.toString()))
                      //   const Positioned(
                      //     bottom: 8.0,
                      //     left: 0,
                      //     right: 0,
                      //     child: RealtimeStatusBannerWidget(),
                      //   ),
                    ],
                  ),
                  ),
                ),
                // Staged messages queued behind a busy agent — collapsed bar
                // fused above the input; tap expands the full stack in a sheet.
                if (!_isAskUserQuestionInputFocused)
                  QueuedMessagesBar(
                    items: _collectQueuedMessages(),
                    onTap: _openQueueSheet,
                  ),
                // Floating Input Area - Extracted to separate component for better performance
                if (!_isAskUserQuestionInputFocused)
                  ChatInputArea(
                    model: _model,
                    supportsControlSettings: supportsControlSettings,
                    showYoloMode: showYoloMode,
                    onSendMessage: (message) async {
                      logFirebaseEvent('AGENT_CHAT_send_message');
                      safeSetState(() {});
                      await _model.sendMessage(context, message);
                      if (mounted) safeSetState(() {});
                    },
                    onRequestAutoScroll: _requestAutoScrollForNextMessages,
                    onOpenWebPreview: _openLatestWebPreview,
                    onOpenFiles: _openFilesCallback(),
                  ),
                // Additional bottom space
                SizedBox(height: _isAskUserQuestionInputFocused ? 0.0 : bottomSpacerHeight),
              ],
            ),
          ),
          ),
        );
      },
    );
  }
}

class _CollapsibleUserMessage extends StatefulWidget {
  const _CollapsibleUserMessage({
    required this.child,
    required this.fadeColor,
    required this.iconColor,
  });

  final Widget child;
  final Color fadeColor;
  final Color iconColor;

  @override
  State<_CollapsibleUserMessage> createState() => _CollapsibleUserMessageState();
}

class _CollapsibleUserMessageState extends State<_CollapsibleUserMessage> {
  static const double _maxHeight = 195.0;

  bool _isOverflow = false;
  bool _isExpanded = false;
  final _contentKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback(_measure);
  }

  void _measure(_) {
    if (!mounted) return;
    final box = _contentKey.currentContext?.findRenderObject() as RenderBox?;
    if (box == null) return;
    final overflows = box.size.height > _maxHeight + 1.0;
    if (overflows != _isOverflow) setState(() => _isOverflow = overflows);
  }

  @override
  Widget build(BuildContext context) {
    final content = KeyedSubtree(key: _contentKey, child: widget.child);

    if (!_isOverflow) {
      return content;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_isExpanded)
          content
        else
          Stack(
            children: [
              ClipRect(
                child: SizedBox(
                  height: _maxHeight,
                  child: OverflowBox(
                    alignment: Alignment.topLeft,
                    maxHeight: double.infinity,
                    child: content,
                  ),
                ),
              ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                height: 48.0,
                child: IgnorePointer(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [widget.fadeColor.withValues(alpha: 0.0), widget.fadeColor],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        GestureDetector(
          onTap: () => setState(() => _isExpanded = !_isExpanded),
          behavior: HitTestBehavior.opaque,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4.0),
            child: Center(
              child: Icon(
                _isExpanded
                    ? Icons.keyboard_double_arrow_up_rounded
                    : Icons.keyboard_double_arrow_down_rounded,
                color: widget.iconColor,
                size: 16.0,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
