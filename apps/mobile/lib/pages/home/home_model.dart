import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/app_locale.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/custom_code/actions/index.dart' as actions;
import '/auth/supabase_auth/auth_util.dart';
import 'home_widget.dart' show HomeWidget;
import 'dart:async';
import 'dart:collection';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:flutter/foundation.dart';

// Re-export ErrorType from custom_functions for backward compatibility
export '/flutter_flow/custom_functions.dart' show ErrorType;

enum LoadingState { initial, loading, loaded, error }

class HomeModel extends FlutterFlowModel<HomeWidget> {
  static const int pageSize = 20;

  // Agent instances (sessions) state
  List<dynamic> agentInstances = [];
  LoadingState loadingState = LoadingState.initial;
  bool showFilters = false;
  String selectedTab = 'All';
  String selectedAgentType = 'All';
  String selectedDateRange = 'All Time';
  String selectedGroupBy = 'Time';
  DateTimeRange? customDateRange;
  Timer? _refreshTimer;
  // Instance-list events from the shared user-scoped WebSocket. The client
  // (VicoaWsClient) owns the connection and its reconnect/backoff loop.
  StreamSubscription<Map<String, dynamic>>? _wsSubscription;
  // Lightweight new-message arrivals (not gated on chat-page watch). Advances
  // each row's `latest_message_at` so the session list's "Xm ago" stays fresh.
  StreamSubscription<Map<String, dynamic>>? _messageArrivedSubscription;
  // Coalesces UI notifies during agent streaming bursts (10-50 msg/s). Without
  // this, every message triggers a full ListView rebuild — but the visible
  // "Xm ago" is minute-granular so sub-second rebuilds are pure waste. The
  // in-memory `agentInstances` patches are applied synchronously regardless;
  // only the rebuild is debounced. Cache writes ride on the next periodic
  // `instance_updated` (heartbeat-driven, ~30s) — no need to write here.
  Timer? _messageArrivedFlushTimer;
  static const Duration _messageArrivedFlushDelay = Duration(seconds: 2);

  // Realtime degradation indicator — `true` means the realtime connection has
  // been down long enough that the list is likely stale. Debounced so brief
  // blips (server hot-reload, cellular handoff) don't flash a banner.
  bool realtimeDegraded = false;
  Timer? _realtimeDegradedDebounceTimer;
  static const Duration _realtimeDegradedDebounce = Duration(seconds: 5);
  String? errorMessage;
  bool hasError = false;
  functions.ErrorType errorType = functions.ErrorType.none;
  bool isPerformingAction = false;
  bool _isRefreshing = false;
  Function? _notifyUI;
  int _previousSessionCount = 0;
  DateTime? _lastUserInteraction;
  bool isLoadingMore = false;
  bool hasMorePages = true;
  int? _nextPage = 1;
  int _highestLoadedPage = 1;
  bool _reachedPaginationEnd = false;
  final Set<String> _deletedInstanceIds = {};

  @override
  void initState(BuildContext context) {
    debugLogWidgetClass(this);
    final prefs = FFAppState().userPreferences;
    selectedGroupBy = prefs.homeFilterGroupBy;
    selectedTab = prefs.homeFilterStatus;
    _loadCachedData();
    _startPeriodicRefresh();
    _connectWs();
  }

  // Set UI notification callback
  void setNotifyUI(Function callback) {
    _notifyUI = callback;
  }

  // Centralized loading state management
  void _setLoadingState(LoadingState state) {
    loadingState = state;
    debugPrint('HomeModel: Loading state changed to $state');
  }

  // Load cached data immediately for instant display
  void _loadCachedData() {
    final appState = FFAppState();

    // Load cached data if available
    if (appState.cachedAgentInstances.isNotEmpty) {
      agentInstances = appState.cachedAgentInstances;
      _previousSessionCount = agentInstances.length;
      _highestLoadedPage =
          agentInstances.isEmpty ? 1 : ((agentInstances.length - 1) ~/ pageSize) + 1;
      _nextPage = _highestLoadedPage + 1;
      hasMorePages = true;
      _reachedPaginationEnd = false;
      _setLoadingState(LoadingState.loaded);
    } else {
      // Keep loading state as initial if no cache
      _setLoadingState(LoadingState.initial);
    }
  }

  bool get _isRealtimeConnected => actions.VicoaWsClient.instance.isConnected;

  // Fallback periodic refresh — only polls when the realtime stream is down
  void _startPeriodicRefresh() {
    _refreshTimer = Timer.periodic(Duration(seconds: 60), (timer) {
      if (_isRefreshing || _isRealtimeConnected) return;
      _fetchAllData(showLoading: false, notifyUI: true);
    });
  }

  // Attach to the shared user-scoped WebSocket for real-time instance updates.
  // The client owns the connection and reconnect loop; this model just listens.
  void _connectWs() {
    final client = actions.VicoaWsClient.instance;
    client.retain();
    _wsSubscription = client.instanceEvents.listen(_handleWsInstanceEvent);
    _messageArrivedSubscription =
        client.messageArrivedEvents.listen(_handleMessageArrived);
  }

  // Advance the matching instance's `latest_message_at` (and preview) when a
  // new message lands. The WS `instance-update` frame body doesn't carry
  // message metadata, so without this the row's relative time goes stale
  // until the next REST refresh (60s poll or pull-to-refresh).
  void _handleMessageArrived(Map<String, dynamic> event) {
    final data = event['data'];
    if (data is! Map) return;
    final instanceId = event['instance_id']?.toString() ??
        data['instance_id']?.toString();
    if (instanceId == null) return;
    final createdAt = data['created_at']?.toString();
    if (createdAt == null || createdAt.isEmpty) return;
    if (_deletedInstanceIds.contains(instanceId)) return;

    final idx =
        agentInstances.indexWhere((i) => i is Map && i['id'] == instanceId);
    if (idx == -1) return;

    final existing = Map<String, dynamic>.from(agentInstances[idx] as Map);
    // Don't go backwards if a stale arrival lands after a newer one.
    final prevAt = existing['latest_message_at']?.toString();
    if (prevAt != null && prevAt.compareTo(createdAt) >= 0) return;

    existing['latest_message_at'] = createdAt;
    existing['latest_message'] = data['content'];
    agentInstances = List.from(agentInstances)..[idx] = existing;
    // Coalesce notifies during streaming bursts. Cache is not written here —
    // the next `instance_updated` (heartbeat-driven, ~30s) writes the full
    // list including these patched fields.
    _messageArrivedFlushTimer?.cancel();
    _messageArrivedFlushTimer = Timer(_messageArrivedFlushDelay, () {
      _messageArrivedFlushTimer = null;
      _notifyUI?.call();
    });
  }

  // Schedule the "Reconnecting…" banner — only flips visible after the debounce
  // so transient blips don't flash a banner on screen.
  void _onWsDisconnected() {
    if (realtimeDegraded || _realtimeDegradedDebounceTimer != null) return;
    _realtimeDegradedDebounceTimer = Timer(_realtimeDegradedDebounce, () {
      _realtimeDegradedDebounceTimer = null;
      // Skip if we reconnected during the debounce window.
      if (_isRealtimeConnected) return;
      realtimeDegraded = true;
      _notifyUI?.call();
    });
  }

  // Clear the banner the moment we re-establish — no debounce on the way down.
  void _clearRealtimeDegraded() {
    _realtimeDegradedDebounceTimer?.cancel();
    _realtimeDegradedDebounceTimer = null;
    if (!realtimeDegraded) return;
    realtimeDegraded = false;
    _notifyUI?.call();
  }

  // Force a data refresh — used by the lifecycle hook when the app returns to
  // the foreground. VicoaWsClient reconnects the socket on resume itself; this
  // just resyncs the list in case updates were missed while backgrounded.
  void forceWsReconnect() {
    if (!_isRefreshing) {
      unawaited(_fetchAllData(showLoading: false, notifyUI: true));
    }
  }

  void _handleWsInstanceEvent(Map<String, dynamic> event) {
    final eventType = event['event'] as String?;
    final data = event['data'];

    // On (re)connect, resync the list — a fire-and-forget broadcast missed
    // during the disconnect window would otherwise only surface on the next
    // 60 s poll or a manual refresh.
    if (eventType == 'connected') {
      _clearRealtimeDegraded();
      _fetchAllData(showLoading: false, notifyUI: true);
      return;
    }

    if (eventType == 'disconnected') {
      _onWsDisconnected();
      return;
    }

    if (eventType == 'heartbeat' || data == null || data is! Map) return;

    final id = data['id']?.toString();
    if (id == null) return;

    if (eventType == 'instance_created') {
      if (_deletedInstanceIds.contains(id)) return;
      final existing = agentInstances.any((i) => i is Map && i['id'] == id);
      if (!existing) {
        agentInstances = [data, ...agentInstances];
        _previousSessionCount = agentInstances.length;
        FFAppState().cachedAgentInstances = agentInstances;
        FFAppState().cachedAgentInstancesTimestamp = DateTime.now();
        _notifyUI?.call();
      }
    } else if (eventType == 'instance_updated') {
      if (_deletedInstanceIds.contains(id)) return;
      final idx = agentInstances.indexWhere((i) => i is Map && i['id'] == id);
      if (idx != -1) {
        final updated = Map<String, dynamic>.from(agentInstances[idx] as Map);
        (data as Map).forEach((k, v) { updated[k.toString()] = v; });
        agentInstances = List.from(agentInstances)..[idx] = updated;
        FFAppState().cachedAgentInstances = agentInstances;
        FFAppState().cachedAgentInstancesTimestamp = DateTime.now();
        _notifyUI?.call();
      } else {
        // Unknown instance — do a background refresh to pick it up
        _fetchAllData(showLoading: false, notifyUI: true);
      }
    }
  }

  // Core data fetching logic - single source of truth
  Future<void> _fetchAllData({
    required bool showLoading,
    bool notifyUI = false,
  }) async {
    if (_isRefreshing) return;

    _isRefreshing = true;
    final appState = FFAppState();

    if (showLoading) {
      // Only flip to the centered-spinner state when we have nothing to show.
      // If cached data is already on screen, the RefreshIndicator's pull
      // spinner is the right affordance — blanking the list to a spinner is
      // jarring and hides what the user was reading.
      if (agentInstances.isEmpty) {
        _setLoadingState(LoadingState.loading);
      }
      hasError = false;
      errorMessage = null;
      errorType = functions.ErrorType.none;
    }

    try {
      final now = DateTime.now();
      final previousHasMorePages = hasMorePages;
      final previousNextPage = _nextPage;
      // Refresh the full loaded range so status changes / new instances on
      // pages 2+ become visible too. Backend caps `limit` at 100 (5 pages).
      // If the user has paginated past that, we still refresh the first 100
      // and preserve the rest of the local tail.
      final pagesToRefresh = _highestLoadedPage < 1 ? 1 : _highestLoadedPage;
      final refreshFetchSize = (pagesToRefresh * pageSize).clamp(pageSize, 100);
      final response = await actions.apiGetAllAgentInstances(
        page: 1,
        pageSize: refreshFetchSize,
      );
      final newInstances = (response['items'] as List?) ?? <dynamic>[];
      final pagesFetched = (newInstances.length / pageSize).ceil();
      // For a true full-range refresh, treat the fetched window as authoritative
      // (drops any locally-cached items that were deleted on the server within
      // that range). Only preserve a tail when the user has scrolled past the
      // backend's 100-item cap.
      final preserveTail =
          !showLoading && agentInstances.length > newInstances.length;
      final mergedInstances =
          _mergeRefreshedInstances(newInstances, preserveExistingTail: preserveTail);
      final responseHasMore = response['hasMore'] == true;
      final responseNextPage = response['nextPage'] as int?;

      // Update local state
      agentInstances = mergedInstances;
      _highestLoadedPage =
          pagesFetched > _highestLoadedPage ? pagesFetched : _highestLoadedPage;
      if (showLoading || !preserveTail) {
        hasMorePages = responseHasMore;
        _reachedPaginationEnd = !responseHasMore;
        _nextPage = responseNextPage ??
            (responseHasMore ? _highestLoadedPage + 1 : null);
      } else if (_reachedPaginationEnd) {
        hasMorePages = false;
        _nextPage = null;
      } else {
        final minimumNextPage = _highestLoadedPage + 1;
        hasMorePages = previousHasMorePages || responseHasMore;
        final candidateNextPage = responseNextPage ?? previousNextPage ?? minimumNextPage;
        _nextPage = hasMorePages
            ? (candidateNextPage < minimumNextPage ? minimumNextPage : candidateNextPage)
            : null;
      }

      // Update cache
      appState.cachedAgentInstances = mergedInstances;
      appState.cachedAgentInstancesTimestamp = now;

      // Track session count changes
      final hasNewSessions = mergedInstances.length > _previousSessionCount;
      _previousSessionCount = mergedInstances.length;

      if (hasNewSessions) {
        debugPrint('New sessions detected! Total: ${mergedInstances.length}');
      }

      hasError = false;
      errorType = functions.ErrorType.none;
      if (showLoading) {
        _setLoadingState(LoadingState.loaded);
      }

      // Notify UI if requested
      if (notifyUI && _notifyUI != null) {
        _notifyUI!();
      }
    } on actions.AuthenticationException catch (e) {
      debugPrint('Authentication error: $e');
      if (showLoading) {
        _handleAuthError(appState);
      }
    } on actions.ServiceUnavailableException catch (e) {
      debugPrint('Service unavailable: $e');
      if (showLoading) {
        _handleServiceUnavailableError(appState);
      }
    } on actions.NetworkException catch (e) {
      debugPrint('Network error: $e');
      if (showLoading) {
        _handleNetworkError(appState);
      }
    } catch (e) {
      debugPrint('Unexpected error: $e');
      if (showLoading) {
        _handleServerError(appState);
      }
    } finally {
      _isRefreshing = false;
    }
  }

  List<dynamic> _mergeRefreshedInstances(
    List<dynamic> firstPageInstances, {
    required bool preserveExistingTail,
  }) {
    if (!preserveExistingTail || agentInstances.isEmpty) {
      return firstPageInstances.where((instance) {
        if (instance is! Map) return true;
        final instanceId = instance['id']?.toString();
        return instanceId == null || !_deletedInstanceIds.contains(instanceId);
      }).toList();
    }

    final firstPageIds = firstPageInstances
        .whereType<Map>()
        .map((instance) => instance['id']?.toString())
        .whereType<String>()
        .toSet();

    final remainingInstances = agentInstances.where((instance) {
      if (instance is! Map) {
        return true;
      }
      final instanceId = instance['id']?.toString();
      return instanceId == null || !firstPageIds.contains(instanceId);
    }).toList();

    final filteredFirstPage = firstPageInstances.where((instance) {
      if (instance is! Map) return true;
      final instanceId = instance['id']?.toString();
      return instanceId == null || !_deletedInstanceIds.contains(instanceId);
    }).toList();

    final filteredRemaining = remainingInstances.where((instance) {
      if (instance is! Map) return true;
      final instanceId = instance['id']?.toString();
      return instanceId == null || !_deletedInstanceIds.contains(instanceId);
    }).toList();

    return [...filteredFirstPage, ...filteredRemaining];
  }

  Future<void> loadMoreAgents() async {
    final pageToLoad = _nextPage;
    if (pageToLoad == null || !hasMorePages || isLoadingMore || _isRefreshing) {
      return;
    }

    isLoadingMore = true;
    _notifyUI?.call();

    try {
      final response = await actions.apiGetAllAgentInstances(
        page: pageToLoad,
        pageSize: pageSize,
      );
      final nextItems = (response['items'] as List?) ?? <dynamic>[];
      final existingIds = agentInstances
          .whereType<Map>()
          .map((instance) => instance['id']?.toString())
          .whereType<String>()
          .toSet();

      final uniqueNextItems = nextItems.where((instance) {
        if (instance is! Map) {
          return true;
        }
        final instanceId = instance['id']?.toString();
        return instanceId == null ||
            (!existingIds.contains(instanceId) &&
                !_deletedInstanceIds.contains(instanceId));
      }).toList();

      if (uniqueNextItems.isNotEmpty) {
        agentInstances = [...agentInstances, ...uniqueNextItems];
        final appState = FFAppState();
        appState.cachedAgentInstances = agentInstances;
        appState.cachedAgentInstancesTimestamp = DateTime.now();
        _previousSessionCount = agentInstances.length;
        _highestLoadedPage = pageToLoad;
      }

      if (uniqueNextItems.isEmpty) {
        hasMorePages = false;
        _nextPage = null;
        _reachedPaginationEnd = true;
      } else {
        hasMorePages = response['hasMore'] == true;
        _nextPage = response['nextPage'] as int?;
        if (_nextPage == null && hasMorePages) {
          _nextPage = pageToLoad + 1;
        }
        _reachedPaginationEnd = false;
      }
    } catch (e) {
      debugPrint('Error loading more agent instances: $e');
    } finally {
      isLoadingMore = false;
      _notifyUI?.call();
    }
  }

  // Handle authentication errors (only when refresh fails)
  void _handleAuthError(FFAppState appState) {
    hasError = true;
    errorType = functions.ErrorType.authentication;
    final l = tr();
    if (loggedIn) {
      errorMessage = l.homeErrorConnecting;
    } else {
      errorMessage = l.homeErrorSessionExpired;
    }

    if (appState.cachedAgentInstances.isNotEmpty) {
      // Show cached data with error indicator
      agentInstances = appState.cachedAgentInstances;
      _setLoadingState(LoadingState.loaded);
      debugPrint('Using cached data due to auth error');
    } else {
      // No cache - show empty state with error
      agentInstances = [];
      _setLoadingState(LoadingState.error);
    }
  }

  // Handle network errors
  void _handleNetworkError(FFAppState appState) {
    final l = tr();
    hasError = true;
    errorType = functions.ErrorType.network;
    errorMessage = l.homeErrorOfflineCached;

    if (appState.cachedAgentInstances.isNotEmpty) {
      // Show cached data with warning
      agentInstances = appState.cachedAgentInstances;
      _setLoadingState(LoadingState.loaded);
      debugPrint('Using cached data due to network error');
    } else {
      // No cache - show empty state
      agentInstances = [];
      errorMessage = l.homeErrorOffline;
      _setLoadingState(LoadingState.error);
    }
  }

  void _handleServiceUnavailableError(FFAppState appState) {
    final l = tr();
    hasError = true;
    errorType = functions.ErrorType.server;
    errorMessage = l.homeErrorServiceUnavailable;

    if (appState.cachedAgentInstances.isNotEmpty) {
      agentInstances = appState.cachedAgentInstances;
      _setLoadingState(LoadingState.loaded);
      debugPrint('Using cached data due to service unavailable');
    } else {
      agentInstances = [];
      errorMessage = l.homeErrorServiceUnavailableRetry;
      _setLoadingState(LoadingState.error);
    }
  }

  // Handle server/general errors
  void _handleServerError(FFAppState appState) {
    hasError = true;
    errorType = functions.ErrorType.server;
    errorMessage = tr().homeErrorLoadSessionsFailed;

    if (appState.cachedAgentInstances.isNotEmpty) {
      // Silently use cache for server errors
      agentInstances = appState.cachedAgentInstances;
      hasError = false; // Don't show error for server issues if cache exists
      _setLoadingState(LoadingState.loaded);
    } else {
      // No cache - show error
      agentInstances = [];
      _setLoadingState(LoadingState.error);
    }
  }

  // Main entry point for loading data
  Future<void> loadAgents({bool forceRefresh = false}) async {
    final appState = FFAppState();

    if (forceRefresh) {
      // User-initiated refresh (pull-to-refresh)
      _lastUserInteraction = DateTime.now();

      // Wait for ongoing refresh to complete
      int waitCount = 0;
      while (_isRefreshing && waitCount < 50) {
        await Future.delayed(Duration(milliseconds: 100));
        waitCount++;
      }

      await _fetchAllData(showLoading: true);
      return;
    }

    // Smart caching for non-force refresh
    final hasValidCache = _isCacheValid() && appState.cachedAgentInstances.isNotEmpty;

    if (hasValidCache) {
      _loadFromCache(appState);
      unawaited(_fetchAllData(showLoading: false, notifyUI: true));
    } else {
      await _fetchAllData(showLoading: true);
    }
  }

  // Load data from cache
  void _loadFromCache(FFAppState appState) {
    if (agentInstances.isEmpty || agentInstances != appState.cachedAgentInstances) {
      agentInstances = appState.cachedAgentInstances;
      _setLoadingState(LoadingState.loaded);
    }
  }

  // Check if cache is still valid (less than 1 minute old)
  bool _isCacheValid() {
    final appState = FFAppState();
    if (appState.cachedAgentInstancesTimestamp == null) {
      return false;
    }

    final cacheAge = DateTime.now().difference(appState.cachedAgentInstancesTimestamp!);
    return cacheAge.inMinutes < 1;
  }

  List<dynamic> getFilteredSessions() {
    List<dynamic> filtered = agentInstances;

    // Filter by status
    if (selectedTab != 'All') {
      if (selectedTab == 'In progress' || selectedTab == 'Running' || selectedTab == 'Active') {
        filtered = filtered
            .where((instance) => instance['status'] == 'ACTIVE')
            .toList();
      } else if (selectedTab == 'In review' || selectedTab == 'Need Input' || selectedTab == 'Waiting') {
        filtered = filtered
            .where((instance) => instance['status'] == 'AWAITING_INPUT')
            .toList();
      } else if (selectedTab == 'Done' || selectedTab == 'Tasks Done' || selectedTab == 'Completed') {
        filtered = filtered
            .where((instance) => instance['status'] == 'REVIEWED')
            .toList();
      } else if (selectedTab == 'Not closed') {
        filtered = filtered
            .where((instance) {
              final status = instance['status'];
              return status == 'ACTIVE' ||
                  status == 'AWAITING_INPUT' ||
                  status == 'REVIEWED';
            })
            .toList();
      } else if (selectedTab == 'Closed') {
        filtered = filtered
            .where((instance) {
              final status = instance['status'];
              return status != 'ACTIVE' &&
                  status != 'AWAITING_INPUT' &&
                  status != 'REVIEWED';
            })
            .toList();
      }
    }

    // Filter by agent type
    if (selectedAgentType != 'All') {
      filtered = filtered.where((instance) {
        final agentTypeName =
            instance['agent_type_name']?.toString().toLowerCase() ?? '';
        return agentTypeName == selectedAgentType.toLowerCase();
      }).toList();
    }

    // Filter by date range
    if (selectedDateRange == 'All Time') {
      return filtered;
    }

    final now = DateTime.now();
    final todayStart = DateTime(now.year, now.month, now.day);
    final tomorrowStart = todayStart.add(Duration(days: 1));
    final sevenDaysAgo = now.subtract(Duration(days: 7));

    filtered = filtered.where((instance) {
      final sessionDateRaw = instance['latest_message_at'] ?? instance['started_at'];
      if (sessionDateRaw == null) {
        return false;
      }
      final sessionDate = DateTime.tryParse(sessionDateRaw.toString());
      if (sessionDate == null) {
        return false;
      }
      final localSessionDate = sessionDate.toLocal();

      switch (selectedDateRange) {
        case 'Today':
          return !localSessionDate.isBefore(todayStart) &&
              localSessionDate.isBefore(tomorrowStart);
        case 'Last 7 Days':
          return !localSessionDate.isBefore(sevenDaysAgo);
        case 'Custom':
          if (customDateRange == null) {
            return true;
          }
          final startDate = DateTime(customDateRange!.start.year,
              customDateRange!.start.month, customDateRange!.start.day);
          final endExclusive = DateTime(customDateRange!.end.year,
                  customDateRange!.end.month, customDateRange!.end.day)
              .add(Duration(days: 1));
          return !localSessionDate.isBefore(startDate) &&
              localSessionDate.isBefore(endExclusive);
        default:
          return true;
      }
    }).toList();

    return filtered;
  }

  Map<String, List<dynamic>> getGroupedSessions() {
    int compareLatest(dynamic a, dynamic b) {
      final aDate = DateTime.tryParse(a['latest_message_at'] ?? a['started_at'] ?? '') ?? DateTime.now();
      final bDate = DateTime.tryParse(b['latest_message_at'] ?? b['started_at'] ?? '') ?? DateTime.now();
      return bDate.compareTo(aDate);
    }

    // Pinned bypasses the status tab + agent filters: pulled from the raw
    // instance list, deduped out of the regular grouped stream.
    final pinned = agentInstances
        .where((s) => s['pinned_at'] != null)
        .toList()
      ..sort(compareLatest);
    final pinnedIds = pinned.map((s) => s['id']).toSet();

    final unpinned = getFilteredSessions()
        .where((s) => !pinnedIds.contains(s['id']))
        .toList()
      ..sort(compareLatest);

    final Map<String, List<dynamic>> grouped =
        LinkedHashMap<String, List<dynamic>>();
    if (pinned.isNotEmpty) {
      grouped['Pinned'] = pinned;
    }

    final Map<String, List<dynamic>> rest;
    if (selectedGroupBy == 'Project') {
      rest = _groupByProject(unpinned);
    } else if (selectedGroupBy == 'Status') {
      rest = _groupByStatus(unpinned);
    } else {
      rest = _groupByTime(unpinned);
    }
    grouped.addAll(rest);
    return grouped;
  }

  Map<String, List<dynamic>> _groupByTime(List<dynamic> sessions) {
    final Map<String, List<dynamic>> grouped = LinkedHashMap<String, List<dynamic>>();
    for (final session in sessions) {
      final sessionDate = DateTime.tryParse(session['latest_message_at'] ?? session['started_at'] ?? '');
      if (sessionDate != null) {
        final dateKey = _getDateLabel(sessionDate.toLocal());
        grouped.putIfAbsent(dateKey, () => []).add(session);
      }
    }
    return grouped;
  }

  Map<String, List<dynamic>> _groupByProject(List<dynamic> sessions) {
    // Map from full project path -> (display label, sessions list)
    final Map<String, String> pathToLabel = {};
    final Map<String, List<dynamic>> pathToSessions = LinkedHashMap<String, List<dynamic>>();

    for (final session in sessions) {
      final project = session['project']?.toString().trim() ?? '';
      String path;
      String label;
      if (project.isEmpty) {
        path = '';
        label = 'No Project';
      } else {
        final clean = project.endsWith('/') ? project.substring(0, project.length - 1) : project;
        path = clean;
        final last = clean.split('/').last;
        label = last.isNotEmpty ? last : 'No Project';
      }
      pathToLabel[path] = label;
      pathToSessions.putIfAbsent(path, () => []).add(session);
    }

    // Sort groups by full project path alphabetically so group order is stable
    final sortedPaths = pathToSessions.keys.toList()..sort((a, b) {
      if (a.isEmpty) return 1;
      if (b.isEmpty) return -1;
      return a.compareTo(b);
    });

    final Map<String, List<dynamic>> grouped = LinkedHashMap<String, List<dynamic>>();
    for (final path in sortedPaths) {
      final label = pathToLabel[path]!;
      grouped.putIfAbsent(label, () => []).addAll(pathToSessions[path]!);
    }
    return grouped;
  }

  Map<String, List<dynamic>> _groupByStatus(List<dynamic> sessions) {
    const order = ['In progress', 'In review', 'Done', 'Closed'];
    final Map<String, List<dynamic>> grouped = LinkedHashMap<String, List<dynamic>>();
    for (final label in order) {
      grouped[label] = [];
    }
    for (final session in sessions) {
      final status = session['status'] as String? ?? '';
      if (status == 'ACTIVE') {
        grouped['In progress']!.add(session);
      } else if (status == 'AWAITING_INPUT') {
        grouped['In review']!.add(session);
      } else if (status == 'REVIEWED') {
        grouped['Done']!.add(session);
      } else {
        grouped['Closed']!.add(session);
      }
    }
    return grouped;
  }

  String _getDateLabel(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final sessionDate = DateTime(date.year, date.month, date.day);
    
    if (sessionDate == today) return tr().dateToday;
    if (sessionDate == today.subtract(Duration(days: 1))) return tr().dateYesterday;
    if (sessionDate.isAfter(today.subtract(Duration(days: 7)))) {
      return DateFormat.EEEE().format(date); // localized weekday
    }
    return DateFormat.MMMd().format(date); // localized month + day
  }

  void selectGroupBy(String groupBy) {
    selectedGroupBy = groupBy;
    FFAppState().updateUserPreferences((p) => p..homeFilterGroupBy = groupBy);
  }

  void selectTab(String tab) {
    selectedTab = tab;
    FFAppState().updateUserPreferences((p) => p..homeFilterStatus = tab);
  }

  void selectAgentType(String agentType) {
    selectedAgentType = agentType;
  }

  void selectDateRange(String range) {
    selectedDateRange = range;
    if (range != 'Custom') {
      customDateRange = null;
    }
  }

  void selectCustomDateRange(DateTimeRange range) {
    customDateRange = range;
    selectedDateRange = 'Custom';
  }

  String get selectedDateFilterLabel {
    if (selectedDateRange == 'Custom' && customDateRange != null) {
      final formatter = DateFormat.MMMd();
      final startLabel = formatter.format(customDateRange!.start);
      final endLabel = formatter.format(customDateRange!.end);
      if (startLabel == endLabel) {
        return startLabel;
      }
      return '$startLabel - $endLabel';
    }
    return localizedFilterLabel(selectedDateRange);
  }

  String get dateRangeChipLabel {
    if (selectedDateRange == 'All Time' && customDateRange == null) {
      return tr().filterDate;
    }
    return selectedDateFilterLabel;
  }

  // Optimistically remove an instance from the local list (e.g. deleted from chat page)
  void removeInstance(String instanceId) {
    _deletedInstanceIds.add(instanceId);
    agentInstances.removeWhere((instance) => instance['id'] == instanceId);
    final appState = FFAppState();
    appState.cachedAgentInstances = agentInstances;
    appState.cachedAgentInstancesTimestamp = DateTime.now();
    appState.clearChatDraft(instanceId);
  }

  // Delete session/instance
  Future<bool> deleteSession(String instanceId) async {
    isPerformingAction = true;

    try {
      final success = await actions.apiDeleteAgentInstance(instanceId);
      if (success) {
        final appState = FFAppState();

        _deletedInstanceIds.add(instanceId);
        agentInstances.removeWhere((instance) => instance['id'] == instanceId);

        // Update cache to reflect deletion
        appState.cachedAgentInstances = agentInstances;
        appState.cachedAgentInstancesTimestamp = DateTime.now();

        // Clear the draft message for this session
        appState.clearChatDraft(instanceId);
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error deleting session: $e');
      return false;
    } finally {
      isPerformingAction = false;
    }
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _realtimeDegradedDebounceTimer?.cancel();
    _wsSubscription?.cancel();
    _messageArrivedSubscription?.cancel();
    _messageArrivedFlushTimer?.cancel();
    actions.VicoaWsClient.instance.release();
  }
}

/// Maps a stored filter value (kept in English for logic/persistence) to its
/// localized display label. Brand/agent names (Claude Code, Codex, OpenCode)
/// and anything unknown (e.g. a formatted custom date range) pass through.
String localizedFilterLabel(String value) {
  final l = tr();
  switch (value) {
    case 'Project':
      return l.filterProject;
    case 'Status':
      return l.filterStatus;
    case 'Time':
      return l.filterTime;
    case 'All':
      return l.filterAll;
    case 'Not closed':
      return l.filterNotClosed;
    case 'In progress':
      return l.filterInProgress;
    case 'In review':
      return l.filterInReview;
    case 'Done':
      return l.commonDone;
    case 'Closed':
      return l.filterClosed;
    case 'Pinned':
      return l.homeGroupPinned;
    case 'No Project':
      return l.homeGroupNoProject;
    case 'All Time':
      return l.filterAllTime;
    case 'Today':
      return l.dateToday;
    case 'Last 7 Days':
      return l.filterLast7Days;
    case 'Custom Range':
      return l.filterCustomRange;
    case 'Group By':
      return l.filterGroupBy;
    case 'Filter':
      return l.filterFilter;
    case 'Date Range':
      return l.filterDateRange;
    case 'Agent Type':
      return l.filterAgentType;
    case 'Date':
      return l.filterDate;
    case 'Type':
      return l.filterType;
    case 'STATUS':
      return l.filterStatusHeader;
    case 'DATE RANGE':
      return l.filterDateRangeHeader;
    case 'AGENT TYPE':
      return l.filterAgentTypeHeader;
    default:
      return value;
  }
}
