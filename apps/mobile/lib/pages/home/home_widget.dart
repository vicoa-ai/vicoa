import 'package:vicoa/backend/push_notifications/notification_util.dart';

import 'agent_filters_panel.dart';
import 'session_list.dart';
import '/pages/common/session_actions.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import 'dart:async';
import '/actions/actions.dart' as action_blocks;
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/widgets/index.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/components/error_state_display/error_state_display_widget.dart';
import '/components/error_banner/error_banner_widget.dart';
import '/components/floating_tab_bar.dart';
import '/components/realtime_status_banner/realtime_status_banner_widget.dart';
import '/components/review_dialog/review_prompt_helper.dart' as review_prompts;
import '/components/empty_filter_state/empty_filter_state_widget.dart';
import '/components/welcome_demo/welcome_demo_card.dart';
import '/components/getting_started/getting_started_checklist.dart';
import '/index.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:go_router/go_router.dart';
import 'home_model.dart';
export 'home_model.dart';
import '/auth/supabase_auth/auth_util.dart';

class HomeWidget extends StatefulWidget {
  const HomeWidget({super.key});

  static String routeName = 'Home';
  static String routePath = '/home';

  @override
  State<HomeWidget> createState() => _HomeWidgetState();
}

class _HomeWidgetState extends State<HomeWidget>
    with RouteAware, WidgetsBindingObserver {
  late HomeModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();
  final _filterButtonKey = GlobalKey();
  final ScrollController _scrollController = ScrollController();
  final Map<String, bool> _collapsedGroups = {};
  void _handleScroll() {
    if (!_scrollController.hasClients) {
      return;
    }
    final position = _scrollController.position;
    if (position.maxScrollExtent - position.pixels <= 400.0) {
      _model.loadMoreAgents();
    }
  }

  void _schedulePrefetchCheck() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _handleScroll();
    });
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => HomeModel());
    _scrollController.addListener(_handleScroll);
    WidgetsBinding.instance.addObserver(this);

    // Set up UI notification callback for silent refreshes
    _model.setNotifyUI(() {
      if (mounted) {
        safeSetState(() {});
        _schedulePrefetchCheck();
      }
    });

    // Start loading agents immediately
    // Trigger setState right away to show loading indicator
    safeSetState(() {});

    // Load agents first, then check for review prompt after completion
    _model.loadAgents().then((_) async {
      if (mounted) {
        safeSetState(() {});
        _schedulePrefetchCheck();
        // Add a small delay before showing review prompt
        // to ensure user sees the home page first
        await Future.delayed(Duration(milliseconds: 800));
        if (mounted) {
          // Only prompt for review after agents have fully loaded
          // and we have confirmed there are actual sessions
          await _maybePromptForSessionReview();
        }
      }
    });

    // Handle other initialization tasks after first frame
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      logFirebaseEvent('HOME_PAGE_Home_ON_INIT_STATE');

      try {
        // Background tasks that don't affect initial UI
        unawaited(
          () async {
            await actions.syncSubscriptionStatus(forceRefresh: true);

            // FCM token is automatically set up when permissions are granted
            await notificationHandler.getFCMToken();

            // Reconcile the launcher badge on cold start — the resume observer
            // only fires on later foregrounds, so without this a stale badge
            // from a push (or one the user already cleared elsewhere) would
            // linger through the first session.
            await actions.refreshAppBadge();
          }(),
        );

        if (FFAppState().creditTransactions.isEmpty) {
          await action_blocks.grantCredit(
            context,
            creditGranted: 20,
            name: 'Initial Free Messages',
          );
        }

        await action_blocks.checkVersion(context);

        // Review prompt now happens after loadAgents() completes
        // Sync is handled during sign-in and write-through updates.
        // Keep startup lightweight and non-blocking.
      } catch (e) {
        debugPrint('Error during page initialization: $e');
        if (mounted) safeSetState(() {});
      }
    });
  }

  @override
  void dispose() {
    routeObserver.unsubscribe(this);
    WidgetsBinding.instance.removeObserver(this);
    _scrollController.removeListener(_handleScroll);
    _scrollController.dispose();

    _model.dispose();

    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    // The mobile OS may suspend the WS socket while backgrounded; force a
    // reconnect + fresh fetch on resume so new instances and status updates
    // surface immediately instead of waiting for the polling fallback.
    if (state == AppLifecycleState.resumed && mounted && _model.isRouteVisible) {
      _model.forceWsReconnect();
    }
  }

  @override
  void didUpdateWidget(HomeWidget oldWidget) {
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
  }

  @override
  void didPushNext() {
    _model.isRouteVisible = false;
  }

  Future<void> _maybePromptForSessionReview() async {
    if (!mounted) {
      return;
    }
    await review_prompts.maybePromptForSessionReview(
      context: context,
      totalSessionCount: _model.agentInstances.length,
    );
  }

  void _showHomeSnackBar(String message) {
    if (!mounted) {
      return;
    }
    SessionActions.showSnack(context, message, waitTime: 1500);
  }

  /// Opens the New Session flow (shared by the app-bar + button and the
  /// getting-started checklist's "Start a session" step).
  Future<void> _startNewSessionFlow() async {
    logFirebaseEvent('HOME_PAGE_add_button_ON_TAP');
    HapticFeedback.mediumImpact();
    final result = await context.pushNamed(
      NewSessionWidget.routeName,
      extra: <String, dynamic>{
        kTransitionInfoKey: const TransitionInfo(
          hasTransition: true,
          transitionType: PageTransitionType.rightToLeft,
          duration: Duration(milliseconds: 300),
        ),
      },
    );

    // Handle result from StartSession
    if (result != null) {
      if (result is Map && result['status'] == 'success') {
        // Reload agents first
        await _model.loadAgents();
        await _maybePromptForSessionReview();
        if (mounted) setState(() {});

        // Navigate to AgentChat with the new instance
        final instanceId = result['instanceId'];
        final instanceData = result['instanceData'];

        if (instanceId != null && mounted) {
          await context.pushNamed(
            AgentChatWidget.routeName,
            pathParameters: {
              'instanceId': instanceId.toString(),
            },
            extra: <String, dynamic>{
              'instanceData': instanceData,
              'hasInitialPrompt': result['hasInitialPrompt'] == true,
              kTransitionInfoKey: const TransitionInfo(
                hasTransition: true,
                transitionType: PageTransitionType.rightToLeft,
              ),
            },
          );
          // Reload agents again after returning from chat in case of changes
          if (mounted) {
            await _model.loadAgents();
            await _maybePromptForSessionReview();
            setState(() {});
          }
        }
      } else if (result == 'success') {
        // Legacy support for old flow
        await _model.loadAgents();
        if (mounted) setState(() {});
      }
    }
  }

  /// Opens the most-recent session's chat (checklist "Send a message" step).
  /// Falls back to the New Session flow if there are somehow no sessions.
  Future<void> _openLatestSession() async {
    final sessions = _model.getFilteredSessions();
    if (sessions.isEmpty) {
      await _startNewSessionFlow();
      return;
    }
    final inst = Map<String, dynamic>.from(sessions.first as Map);
    await context.pushNamed(
      AgentChatWidget.routeName,
      pathParameters: {'instanceId': inst['id'].toString()},
      extra: <String, dynamic>{
        'instanceData': inst,
        kTransitionInfoKey: const TransitionInfo(
          hasTransition: true,
          transitionType: PageTransitionType.rightToLeft,
        ),
      },
    );
    if (mounted) {
      await _model.loadAgents();
      setState(() {});
    }
  }

  String? _parseProjectName(dynamic project) {
    if (project == null || project.toString().isEmpty) {
      return null;
    }

    final projectPath = project.toString().trim();
    // Remove trailing slash if present
    final cleanPath = projectPath.endsWith('/')
        ? projectPath.substring(0, projectPath.length - 1)
        : projectPath;

    // Split by slash and get the last segment
    final segments = cleanPath.split('/');
    if (segments.isNotEmpty) {
      final lastSegment = segments.last;
      if (lastSegment.isNotEmpty) {
        return lastSegment;
      }
    }

    return null;
  }

  List<Widget> _buildGroupedSessions() {
    final groupedSessions = _model.getGroupedSessions();
    final widgets = <Widget>[];
    final groupBy = _model.selectedGroupBy;
    final useLargeHeader = groupBy == 'Project' || groupBy == 'Status';

    for (final entry in groupedSessions.entries) {
      final isCollapsed = _collapsedGroups[entry.key] ?? false;

      widgets.add(
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            setState(() {
              _collapsedGroups[entry.key] = !isCollapsed;
            });
          },
          child: Padding(
            padding: EdgeInsets.fromLTRB(6.0, 6.0, 0.0, 8.0),
            child: Row(
              children: [
                Text(
                  localizedFilterLabel(entry.key),
                  style: FlutterFlowTheme.of(context).titleMedium.override(
                        fontSize: useLargeHeader ? 17.0 : 16.0,
                        color: FlutterFlowTheme.of(context).secondaryText,
                      ),
                ),
                const SizedBox(width: 4.0),
                AnimatedRotation(
                  turns: isCollapsed ? -0.25 : 0.0,
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeInOut,
                  child: Icon(
                    Icons.expand_more_rounded,
                    color: FlutterFlowTheme.of(context).secondaryText,
                    size: useLargeHeader ? 20.0 : 18.0,
                  ),
                ),
              ],
            ),
          ),
        ),
      );

      widgets.add(
        ClipRect(
          child: AnimatedAlign(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            heightFactor: isCollapsed ? 0.0 : 1.0,
            child: Column(
              children: [
                for (final session in entry.value)
                  _buildSessionCard(session, session['status'] ?? 'UNKNOWN',
                      groupBy: groupBy),
              ],
            ),
          ),
        ),
      );
    }

    return widgets;
  }

  @override
  Widget build(BuildContext context) {
    DebugFlutterFlowModelContext.maybeOf(context)
        ?.parentModelCallback
        ?.call(_model);
    context.watch<FFAppState>();
    final isLoggedIn = loggedIn;

    return Builder(
      builder: (context) => GestureDetector(
        onTap: () {
          FocusScope.of(context).unfocus();
          FocusManager.instance.primaryFocus?.unfocus();
        },
        child: Scaffold(
          key: scaffoldKey,
          backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
          appBar: AppBar(
            backgroundColor: FlutterFlowTheme.of(context).secondaryBackground,
            automaticallyImplyLeading: false,
            title: Row(
              mainAxisSize: MainAxisSize.max,
              children: [
                // Image.asset(
                //   'assets/images/logo-text.png',
                //   height: 35.0,
                //   fit: BoxFit.contain,
                // ),
                Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(8.0, 0.0, 0.0, 0.0),
                  child: Text(
                    'Vicoa',
                    style: FlutterFlowTheme.of(context).headlineMedium.override(
                          font: GoogleFonts.outfit(
                            fontWeight: FontWeight.w500,
                          ),
                          // Must be a direct arg: override() does
                          // font.copyWith(fontSize: fontSize ?? this.fontSize),
                          // so a size set inside jetBrainsMono() gets clobbered
                          // by headlineMedium's size.
                          fontSize: 26.0,
                        ),
                  ),
                ),
              ],
            ),
            actions: [
              Padding(
                padding: EdgeInsetsDirectional.fromSTEB(1.0, 0.0, 16.0, 0.0),
                child: Row(
                  mainAxisSize: MainAxisSize.max,
                  children: [
                    // if (!functions.isActiveSubscription(
                    //     FFAppState().user.subscriptionStatus))
                    //   InkWell(
                    //     splashColor: Colors.transparent,
                    //     focusColor: Colors.transparent,
                    //     hoverColor: Colors.transparent,
                    //     highlightColor: Colors.transparent,
                    //     onTap: () async {
                    //       logFirebaseEvent(
                    //           'HOME_PAGE_Container_q2e1m9x6_ON_TAP');
                    //       HapticFeedback.lightImpact();
                    //       await actions.registerSuperWallEvent(
                    //         context,
                    //         'upgrade_button',
                    //         '',
                    //         true,
                    //       );
                    //     },
                    //     child: Container(
                    //       width: 100.0,
                    //       height: 40.0,
                    //       decoration: BoxDecoration(
                    //         color: FlutterFlowTheme.of(context).primaryBackground,
                    //         borderRadius: BorderRadius.circular(10.0),
                    //       ),
                    //       child: Padding(
                    //         padding: EdgeInsetsDirectional.fromSTEB(
                    //             8.0, 0.0, 8.0, 0.0),
                    //         child: Row(
                    //           mainAxisSize: MainAxisSize.max,
                    //           children: [
                    //             Icon(
                    //               Icons.bolt_rounded,
                    //               color: FFAppState().credit.balance == 0
                    //                   ? Colors.yellow.shade600
                    //                   : FlutterFlowTheme.of(context).secondaryText,
                    //               size: 20.0,
                    //             ),
                    //             Align(
                    //               alignment: AlignmentDirectional(0.0, 0.0),
                    //               child: Text(
                    //                 'Upgrade',
                    //                 textAlign: TextAlign.center,
                    //                 style: FlutterFlowTheme.of(context)
                    //                     .bodyMedium
                    //                     .override(
                    //                       font: GoogleFonts.sourceSans3(
                    //                         fontWeight: FontWeight.w500,
                    //                         fontStyle:
                    //                             FlutterFlowTheme.of(context)
                    //                                 .bodyMedium
                    //                                 .fontStyle,
                    //                       ),
                    //                       color: FlutterFlowTheme.of(context).secondaryText,
                    //                       fontSize: 14.0,
                    //                       letterSpacing: 0.0,
                    //                       fontWeight: FontWeight.w500,
                    //                       fontStyle:
                    //                           FlutterFlowTheme.of(context)
                    //                               .bodyMedium
                    //                               .fontStyle,
                    //                     ),
                    //               ),
                    //             ),
                    //           ],
                    //         ),
                    //       ),
                    //     ),
                    //   ),
                    // SizedBox(width: 8.0),
                    FlutterFlowIconButton(
                      borderRadius: 10.0,
                      borderWidth: 0,
                      buttonSize: 40.0,
                      fillColor: Colors.transparent,
                      icon: Icon(
                        Icons.search_rounded,
                        color: FlutterFlowTheme.of(context).primaryText,
                        size: 24.0,
                      ),
                      onPressed: () async {
                        logFirebaseEvent('HOME_PAGE_search_ICN_ON_TAP');
                        HapticFeedback.lightImpact();
                        await context.pushNamed(
                          SearchWidget.routeName,
                          extra: <String, dynamic>{
                            // Seed the empty-query "Recent" list + 404 fallback
                            // from the already-loaded sessions.
                            'recentSessions': _model.agentInstances,
                            kTransitionInfoKey: const TransitionInfo(
                              hasTransition: true,
                              transitionType: PageTransitionType.fade,
                              duration: Duration(milliseconds: 200),
                            ),
                          },
                        );
                      },
                    ),
                    if (FFAppState().setting.showHomeFilterIcon)
                      SizedBox(
                        key: _filterButtonKey,
                        child: FlutterFlowIconButton(
                          borderRadius: 10.0,
                          borderWidth: 0,
                          buttonSize: 40.0,
                          fillColor: Colors.transparent,
                          icon: Icon(
                            Icons.filter_list_rounded,
                            color: FlutterFlowTheme.of(context).primaryText,
                            size: 22.0,
                          ),
                          onPressed: () async {
                            logFirebaseEvent('HOME_PAGE_filter_ICN_ON_TAP');
                            HapticFeedback.lightImpact();
                            await showAgentFiltersPanel(
                              context: context,
                              model: _model,
                              onStateChanged: () {
                                if (mounted) setState(() {});
                              },
                              anchorKey: _filterButtonKey,
                            );
                          },
                        ),
                      ),
                    if (FFAppState().setting.showHomeWebPreviewIcon)
                      FlutterFlowIconButton(
                        borderRadius: 10.0,
                        borderWidth: 0,
                        buttonSize: 40.0,
                        fillColor: Colors.transparent,
                        icon: Icon(
                          Icons.language_rounded,
                          color: FlutterFlowTheme.of(context).primaryText,
                          size: 22.0,
                        ),
                        onPressed: () async {
                          logFirebaseEvent('HOME_PAGE_web_preview_ICN_ON_TAP');
                          HapticFeedback.lightImpact();
                          context.pushNamed(
                            WebPreviewWidget.routeName,
                            extra: <String, dynamic>{
                              kTransitionInfoKey: TransitionInfo(
                                hasTransition: true,
                                transitionType: PageTransitionType.bottomToTop,
                              ),
                            },
                          );
                        },
                      ),
                                          FlutterFlowIconButton(
                      borderRadius: 10.0,
                      borderWidth: 0,
                      buttonSize: 40.0,
                      fillColor: Colors.transparent,
                      icon: Icon(
                        Icons.person_rounded,
                        color: FlutterFlowTheme.of(context).primaryText,
                        size: 24.0,
                      ),
                      onPressed: () async {
                        logFirebaseEvent('HOME_PAGE_person_rounded_ICN_ON_TAP');
                        HapticFeedback.lightImpact();

                        await showModalBottomSheet(
                          isScrollControlled: true,
                          backgroundColor: Colors.transparent,
                          enableDrag: true,
                          context: context,
                          builder: (context) {
                            return FractionallySizedBox(
                              heightFactor: 0.92,
                              child: ClipRRect(
                                borderRadius: BorderRadius.vertical(
                                  top: Radius.circular(24.0),
                                ),
                                child: ProfileWidget(),
                              ),
                            );
                          },
                        ).then((value) => safeSetState(() {}));
                      },
                    ),
                    FlutterFlowIconButton(
                      borderRadius: 10.0,
                      borderWidth: 0,
                      buttonSize: 40.0,
                      fillColor: Colors.transparent,
                      icon: Icon(
                        Icons.add_rounded,
                        color: FlutterFlowTheme.of(context).primaryText,
                        size: 24.0,
                      ),
                      onPressed: _startNewSessionFlow,
                    ),
                  ],
                ),
              ),
            ],
            centerTitle: true,
            elevation: 0.0,
          ),
          body: RefreshIndicator(
            onRefresh: () async {
              await _model.loadAgents(forceRefresh: true);
              await _maybePromptForSessionReview();
            },
            child: SingleChildScrollView(
              controller: _scrollController,
              physics: AlwaysScrollableScrollPhysics(),
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  minHeight: MediaQuery.of(context).size.height -
                      kToolbarHeight -
                      MediaQuery.of(context).padding.top,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.max,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(height: 8.0),

                    // Suppress the reconnecting banner when the louder
                    // ErrorBannerWidget below is already on screen — they'd
                    // otherwise stack on a full network outage.
                    // if (isLoggedIn && _model.realtimeDegraded && !_model.hasError)
                    //   const RealtimeStatusBannerWidget(),

                    // Status indicator when showing cached data with errors
                    if (isLoggedIn &&
                        _model.hasError &&
                        _model.errorType != functions.ErrorType.none &&
                        _model.loadingState == LoadingState.loaded)
                      ErrorBannerWidget(
                        errorType: _model.errorType,
                        errorMessage: _model.errorMessage,
                        onRetry: () async {
                          await _model.loadAgents(forceRefresh: true);
                          setState(() {});
                        },
                      ),

                    if (!isLoggedIn ||
                        (_model.hasError &&
                            _model.loadingState == LoadingState.error))
                      ErrorStateDisplayWidget(
                        errorType: _model.errorType,
                        errorMessage: _model.errorMessage,
                        onRetry: () async {
                          logFirebaseEvent('HOME_PAGE_RETRY_LOADING');
                          await _model.loadAgents(forceRefresh: true);
                          setState(() {});
                        },
                        onSignInAgain: () async {
                          logFirebaseEvent('HOME_PAGE_LOGOUT_AND_LOGIN');
                          GoRouter.of(context).prepareAuthEvent();
                          await actions.signOutAndClearLocalData();
                          GoRouter.of(context).clearRedirectLocation();

                          // Navigate to sign up page in login mode
                          context.goNamed(
                            AuthOptionsWidget.routeName,
                            queryParameters: {'mode': 'login'},
                          );
                        },
                      )
                    else if (_model.loadingState == LoadingState.initial ||
                        _model.loadingState == LoadingState.loading)
                      Container(
                        height: 200.0,
                        child: Center(
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(
                              FlutterFlowTheme.of(context).primary,
                            ),
                          ),
                        ),
                      )
                    else if (_model.getFilteredSessions().isEmpty &&
                        _model.agentInstances.isNotEmpty &&
                        _model.loadingState == LoadingState.loaded &&
                        !_model.hasError)
                      EmptyFilterStateWidget(
                        statusLabel: _model.selectedTab == 'All' ? '' : localizedFilterLabel(_model.selectedTab),
                      )
                    else if (_model.getFilteredSessions().isEmpty &&
                        _model.loadingState == LoadingState.loaded &&
                        !_model.hasError)
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Brand-new user (no real sessions yet): offer a
                          // tappable sample chat that introduces the product.
                          if (_model.agentInstances.isEmpty) ...[
                            Padding(
                              padding: const EdgeInsetsDirectional.fromSTEB(
                                  16.0, 8.0, 16.0, 0.0),
                              child: WelcomeDemoCard(
                                onReturn: () {
                                  if (mounted) setState(() {});
                                },
                              ),
                            ),
                          ],
                          // Getting-started checklist, below the welcome demo:
                          // drives the phone→desktop "connect a computer" step.
                          Padding(
                            padding: const EdgeInsetsDirectional.fromSTEB(
                                16.0, 12.0, 16.0, 0.0),
                            child: GettingStartedChecklist(
                              sessionCount: 0,
                              onStartSession: _startNewSessionFlow,
                              onStateChanged: () {
                                if (mounted) setState(() {});
                              },
                            ),
                          ),
                        ],
                      )
                    else
                      // Sessions Grid — bottom padding clears the floating
                      // tab bar so the last card can scroll above it.
                      Padding(
                        padding: EdgeInsets.fromLTRB(16.0, 0.0, 16.0,
                            floatingTabBarBottomInset(context)),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Keeps nudging progress (e.g. "send a message")
                            // until the user finishes onboarding, then hides.
                            Padding(
                              padding:
                                  const EdgeInsets.only(top: 8.0, bottom: 8.0),
                              child: GettingStartedChecklist(
                                sessionCount: _model.agentInstances.length,
                                onStartSession: _startNewSessionFlow,
                                onOpenLatestSession: _openLatestSession,
                                onStateChanged: () {
                                  if (mounted) setState(() {});
                                },
                              ),
                            ),
                            ..._buildGroupedSessions(),
                            if (_model.isLoadingMore)
                              Padding(
                                padding: EdgeInsets.only(top: 8.0, bottom: 12.0),
                                child: Center(
                                  child: SizedBox(
                                    width: 24.0,
                                    height: 24.0,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2.0,
                                      valueColor: AlwaysStoppedAnimation<Color>(
                                        FlutterFlowTheme.of(context).primary,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSessionCard(
      Map<String, dynamic> instance, String status, {String groupBy = 'Time'}) {
    return SessionCard(
      key: Key(instance['id']),
      instance: instance,
      status: status,
      groupBy: groupBy,
      onAction: _handleSessionAction,
      onRemoveInstance: (id) {
        _model.removeInstance(id);
        setState(() {});
      },
      onReload: () async {
        await _model.loadAgents();
        if (mounted) setState(() {});
      },
      onSnackBar: _showHomeSnackBar,
      onLongPressMenu: _showSessionMenu,
    );
  }

  Future<void> _showSessionMenu(
      Map<String, dynamic> instance, Offset globalPosition) async {
    final overlayBox =
        Overlay.of(context).context.findRenderObject() as RenderBox?;
    if (overlayBox == null) return;

    const double menuWidth = 140.0;
    const double estimatedMenuHeight = 220.0;
    const double screenPadding = 16.0;
    const double verticalGap = -16.0;

    final overlaySize = overlayBox.size;
    double right = overlaySize.width - globalPosition.dx;
    if (right < screenPadding) right = screenPadding;
    if (right > overlaySize.width - menuWidth - screenPadding) {
      right = overlaySize.width - menuWidth - screenPadding;
    }

    double top = globalPosition.dy + verticalGap;
    if (top + estimatedMenuHeight > overlaySize.height - screenPadding) {
      top = globalPosition.dy - estimatedMenuHeight - verticalGap;
    }
    if (top < screenPadding) top = screenPadding;

    final status = (instance['status']?.toString() ?? '').toUpperCase();
    final showCloseOption = !['CLOSED', 'COMPLETED'].contains(status);

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
              top: top,
              right: right,
              width: menuWidth,
              child: Material(
                color: Colors.transparent,
                child: ChatOptionsMenu(
                  showShareOption: false,
                  showCloseOption: showCloseOption,
                  isPinned: instance['pinned_at'] != null,
                  onPin: () {
                    Navigator.of(dialogContext).pop();
                    _handlePinToggle(instance);
                  },
                  onInfo: () {
                    Navigator.of(dialogContext).pop();
                    _showSessionInfoFor(instance);
                  },
                  onShare: () => Navigator.of(dialogContext).pop(),
                  onRename: () {
                    Navigator.of(dialogContext).pop();
                    _showRenameDialogFor(instance);
                  },
                  onClose: () {
                    Navigator.of(dialogContext).pop();
                    _handleSessionAction(instance, 'complete');
                  },
                  onDelete: () {
                    Navigator.of(dialogContext).pop();
                    _handleSessionAction(instance, 'delete');
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
  }

  Future<void> _showSessionInfoFor(Map<String, dynamic> instance) async {
    await SessionActions.showSessionInfo(
      context,
      instanceId: instance['id'] as String,
      instanceData: instance,
      firebaseEventName: 'HOME_PAGE_session_info_open',
      onTitleChanged: (newName) {
        instance['name'] = newName;
        if (mounted) setState(() {});
      },
    );
    await _model.loadAgents();
    if (mounted) setState(() {});
  }

  Future<void> _showRenameDialogFor(Map<String, dynamic> instance) async {
    await SessionActions.renameSession(
      context,
      instanceId: instance['id'] as String,
      currentName: instance['name']?.toString() ?? '',
      firebaseEventName: 'HOME_PAGE_session_rename',
      onSuccess: (newName) async {
        instance['name'] = newName;
        if (mounted) setState(() {});
        _showHomeSnackBar(AppLocalizations.of(context).homeSessionRenamed);
      },
      onFailure: () async {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(AppLocalizations.of(context).homeRenameFailed),
            backgroundColor: Colors.red,
          ));
        }
      },
    );
  }

  Future<void> _handleSessionAction(
      Map<String, dynamic> instance, String action) async {
    final instanceId = instance['id'];

    if (action == 'complete') {
      await SessionActions.closeSession(
        context,
        instanceId: instanceId,
        firebaseEventName: 'HOME_PAGE_session_complete',
        onSuccess: () async {
          await _model.loadAgents();
          if (mounted) setState(() {});
          _showHomeSnackBar(AppLocalizations.of(context).homeSessionClosed);
        },
        onFailure: () async {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(AppLocalizations.of(context).homeCloseFailed),
              backgroundColor: Colors.red,
            ));
          }
        },
      );
    } else if (action == 'delete') {
      await SessionActions.deleteSession(
        context,
        instanceId: instanceId,
        firebaseEventName: 'HOME_PAGE_session_swipe_delete',
        onBeforeApi: () {
          // Optimistic removal so the item disappears immediately
          _model.removeInstance(instanceId);
          setState(() {});
        },
        onSuccess: () async {
          _showHomeSnackBar(AppLocalizations.of(context).homeSessionDeleted);
        },
        onFailure: () async {
          // Rollback the optimistic removal
          await _model.loadAgents(forceRefresh: true);
          if (mounted) {
            setState(() {});
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(AppLocalizations.of(context).homeDeleteFailed),
              backgroundColor: Colors.red,
            ));
          }
        },
      );
    }
  }

  Future<void> _handlePinToggle(Map<String, dynamic> instance) async {
    final instanceId = instance['id'] as String;
    final wasPinned = instance['pinned_at'] != null;
    final nowIso = DateTime.now().toUtc().toIso8601String();

    setState(() {
      instance['pinned_at'] = wasPinned ? null : nowIso;
    });

    final ok = await SessionActions.togglePin(
      instanceId: instanceId,
      pinned: !wasPinned,
    );

    if (!mounted) return;
    if (!ok) {
      setState(() {
        instance['pinned_at'] = wasPinned ? nowIso : null;
      });
      _showHomeSnackBar(
        wasPinned
            ? AppLocalizations.of(context).homeUnpinFailed
            : AppLocalizations.of(context).homePinFailed,
      );
    }
  }
}

