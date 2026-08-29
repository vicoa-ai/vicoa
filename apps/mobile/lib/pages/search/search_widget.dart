import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/agent_chat/agent_chat_widget.dart';
import '/pages/main_tabs/main_tabs_controller.dart';
import 'search_model.dart';
import 'search_result_rows.dart';
export 'search_model.dart';

/// Full-screen workspace search — the mobile counterpart of vicoa-web's ⌘K
/// palette. Reached from the Home header's search icon; searches sessions,
/// tasks, and automations through `GET /api/v1/search`, showing recent sessions
/// while the query is empty. Results route back into the app: a session opens
/// the chat, a task/automation switches to its tab and opens the item's sheet.
class SearchWidget extends StatefulWidget {
  const SearchWidget({super.key, this.recentSessions});

  /// Sessions already loaded on Home, passed via `extra`. Powers the empty
  /// "Recent" list and the session-only fallback when the endpoint is missing.
  final List<dynamic>? recentSessions;

  static String routeName = 'Search';
  static String routePath = '/search';

  @override
  State<SearchWidget> createState() => _SearchWidgetState();
}

class _SearchWidgetState extends State<SearchWidget> {
  late SearchModel _model;

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => SearchModel());
    _model.recentSessions = widget.recentSessions ?? const [];
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'Search'});
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  // --- navigation ------------------------------------------------------------

  void _openSession(String id) {
    if (id.isEmpty) return;
    HapticFeedback.selectionClick();
    // Chat is a normal pushed route; it stacks above search so a back gesture
    // returns to the (still-typed) query.
    context.pushNamed(
      AgentChatWidget.routeName,
      pathParameters: {'instanceId': id},
      extra: <String, dynamic>{
        kTransitionInfoKey: const TransitionInfo(
          hasTransition: true,
          transitionType: PageTransitionType.rightToLeft,
        ),
      },
    );
  }

  void _openTask(String id) {
    if (id.isEmpty) return;
    HapticFeedback.selectionClick();
    // Tasks/automations open a sheet over their live tab, so pop back to the
    // shell first, then let the bridge switch tabs and open the item.
    context.pop();
    WidgetsBinding.instance.addPostFrameCallback(
        (_) => MainTabsController.instance.showTask(id));
  }

  void _openAutomation(String id) {
    if (id.isEmpty) return;
    HapticFeedback.selectionClick();
    context.pop();
    WidgetsBinding.instance.addPostFrameCallback(
        (_) => MainTabsController.instance.showAutomation(id));
  }

  // --- view ------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
        elevation: 0.0,
        titleSpacing: 0.0,
        leading: Align(
          alignment: const AlignmentDirectional(1.0, 0.0),
          child: FlutterFlowIconButton(
            borderRadius: 10.0,
            borderWidth: 0,
            buttonSize: 40.0,
            fillColor: Colors.transparent,
            icon: Icon(Icons.chevron_left_rounded,
                color: theme.secondaryText, size: 26.0),
            onPressed: () => context.safePop(),
          ),
        ),
        title: TextField(
          controller: _model.queryController,
          focusNode: _model.queryFocus,
          autofocus: true,
          onChanged: _model.onQueryChanged,
          textInputAction: TextInputAction.search,
          cursorColor: theme.primary,
          style: theme.bodyLarge.override(
            font: GoogleFonts.sourceSans3(),
            letterSpacing: 0.0,
          ),
          decoration: InputDecoration(
            isCollapsed: true,
            border: InputBorder.none,
            hintText: l10n.searchHint,
            hintStyle: theme.bodyLarge.override(
              font: GoogleFonts.sourceSans3(),
              letterSpacing: 0.0,
              color: theme.secondaryText.withValues(alpha: 0.6),
            ),
          ),
        ),
        actions: [
          if (_model.query.isNotEmpty)
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 8.0, 0.0),
              child: FlutterFlowIconButton(
                borderRadius: 10.0,
                borderWidth: 0,
                buttonSize: 40.0,
                fillColor: Colors.transparent,
                icon: Icon(Icons.close_rounded,
                    color: theme.secondaryText, size: 22.0),
                onPressed: () {
                  _model.queryController.clear();
                  _model.clear();
                  _model.queryFocus.requestFocus();
                },
              ),
            ),
        ],
      ),
      // bottom: false so results scroll under the home indicator instead of
      // leaving a blank inset strip; the list pads its own bottom for clearance.
      body: SafeArea(
        bottom: false,
        child: _buildBody(context, theme, l10n),
      ),
    );
  }

  Widget _buildBody(
      BuildContext context, FlutterFlowTheme theme, AppLocalizations l10n) {
    if (!_model.hasQuery) {
      final recents = _model.recentSessions;
      if (recents.isEmpty) {
        return _centeredMessage(theme, l10n.searchPrompt);
      }
      return ListView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        padding: const EdgeInsets.fromLTRB(16.0, 4.0, 16.0, 24.0),
        children: [
          _groupHeader(theme, l10n.searchRecent),
          for (final s in recents.take(8))
            SearchSessionRow(
              session: Map<String, dynamic>.from(s as Map),
              onTap: () => _openSession((s)['id']?.toString() ?? ''),
            ),
        ],
      );
    }

    switch (_model.status) {
      case SearchStatus.loading:
        return Center(
          child: SizedBox(
            width: 26.0,
            height: 26.0,
            child: CircularProgressIndicator(
              strokeWidth: 2.5,
              valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
            ),
          ),
        );
      case SearchStatus.error:
        return _centeredMessage(
          theme,
          _model.errorKind == SearchErrorKind.timeout
              ? l10n.searchTimeout
              : l10n.searchFailed,
        );
      case SearchStatus.idle:
      case SearchStatus.loaded:
        if (_model.hasNoResults) {
          return _centeredMessage(theme, l10n.searchNoResults);
        }
        return _buildResults(theme, l10n);
    }
  }

  Widget _buildResults(FlutterFlowTheme theme, AppLocalizations l10n) {
    return ListView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      padding: const EdgeInsets.fromLTRB(16.0, 4.0, 16.0, 24.0),
      children: [
        if (_model.sessions.isNotEmpty) ...[
          _groupHeader(theme, l10n.searchSessions),
          for (final s in _model.sessions)
            SearchSessionRow(
              session: Map<String, dynamic>.from(s as Map),
              onTap: () => _openSession((s)['id']?.toString() ?? ''),
            ),
        ],
        if (_model.tasks.isNotEmpty) ...[
          _groupHeader(theme, l10n.tabTasks),
          for (final t in _model.tasks)
            SearchTaskRow(
              task: Map<String, dynamic>.from(t as Map),
              onTap: () => _openTask((t)['id']?.toString() ?? ''),
            ),
        ],
        if (_model.automations.isNotEmpty) ...[
          _groupHeader(theme, l10n.tabAutomations),
          for (final a in _model.automations)
            SearchAutomationRow(
              automation: Map<String, dynamic>.from(a as Map),
              onTap: () => _openAutomation((a)['id']?.toString() ?? ''),
            ),
        ],
        if (_model.serverUnavailable)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(6.0, 16.0, 6.0, 0.0),
            child: Text(
              l10n.searchSessionsOnly,
              style: theme.bodySmall.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
                color: theme.secondaryText,
              ),
            ),
          ),
      ],
    );
  }

  Widget _groupHeader(FlutterFlowTheme theme, String label) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(6.0, 14.0, 6.0, 4.0),
      child: Text(
        label,
        style: theme.bodySmall.override(
          font: GoogleFonts.sourceSans3(),
          fontSize: 13.0,
          letterSpacing: 0.0,
          fontWeight: FontWeight.w600,
          color: theme.secondaryText,
        ),
      ),
    );
  }

  Widget _centeredMessage(FlutterFlowTheme theme, String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40.0),
        child: Text(
          message,
          textAlign: TextAlign.center,
          style: theme.bodyMedium.override(
            font: GoogleFonts.sourceSans3(),
            letterSpacing: 0.0,
            color: theme.secondaryText,
          ),
        ),
      ),
    );
  }
}
