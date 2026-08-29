import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '/components/floating_tab_bar.dart';
import '/custom_code/utils/automation_utils.dart' as autils;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/agent_chat/agent_chat_widget.dart';
import '/pages/common/session_actions.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import '/pages/main_tabs/main_tabs_controller.dart';
import '/pages/tasks/task_pickers.dart'
    show showAnchoredSingleSelect, PickerOption;
import 'automation_card.dart';
import 'automation_edit_sheet.dart';
import 'automations_model.dart';
export 'automations_model.dart';

/// Scheduled agent runs, ported from the web dashboard's Automation tab. A
/// filterable list (All / Active / Paused) with pause/resume, run-now, and a
/// bottom-sheet editor. The server computes all fire times; this page only
/// edits the stored schedule. Rendered as a tab inside the main shell.
class AutomationsWidget extends StatefulWidget {
  const AutomationsWidget({super.key});

  static String routeName = 'Automations';
  static String routePath = '/automations';

  @override
  State<AutomationsWidget> createState() => _AutomationsWidgetState();
}

class _AutomationsWidgetState extends State<AutomationsWidget> {
  late AutomationsModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final GlobalKey _filterButtonKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => AutomationsModel());
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'Automations'});
    MainTabsController.instance.openAutomationId
        .addListener(_onOpenAutomationRequested);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      await _model.load();
      // Handle a search "open automation" that arrived before first build.
      _consumePendingOpenAutomation();
    });
  }

  @override
  void dispose() {
    MainTabsController.instance.openAutomationId
        .removeListener(_onOpenAutomationRequested);
    _model.dispose();
    super.dispose();
  }

  void _onOpenAutomationRequested() => _consumePendingOpenAutomation();

  bool _openingPendingAutomation = false;

  /// Opens the automation the search page routed to, loading the list first if
  /// this tab hasn't fetched yet. Clears the request up front so it fires once.
  Future<void> _consumePendingOpenAutomation() async {
    final id = MainTabsController.instance.openAutomationId.value;
    if (id == null || id.isEmpty || _openingPendingAutomation || !mounted) {
      return;
    }
    _openingPendingAutomation = true;
    MainTabsController.instance.openAutomationId.value = null;
    try {
      if (_model.automations.isEmpty) await _model.load();
      if (!mounted) return;
      final automation = _model.automations.firstWhere(
        (a) => autils.automationId(a) == id,
        orElse: () => null,
      );
      if (automation != null) await _edit(automation);
    } finally {
      _openingPendingAutomation = false;
    }
  }

  // --- actions ---------------------------------------------------------------

  Future<void> _create() async {
    HapticFeedback.lightImpact();
    final catalog = _model.agentCatalog;
    if (catalog == null) return;
    final body = await showAutomationEditSheet(
      context: context,
      automation: null,
      machines: _model.machines,
      catalog: catalog,
    );
    if (!mounted || body == null) return;
    final created = await _model.createAutomation({...body, 'enabled': true});
    if (created == null && mounted) {
      await SessionActions.showSnack(
          context, AppLocalizations.of(context).automationsSaveFailed);
    }
  }

  Future<void> _edit(dynamic automation) async {
    final catalog = _model.agentCatalog;
    if (catalog == null) return;
    final body = await showAutomationEditSheet(
      context: context,
      automation: automation,
      machines: _model.machines,
      catalog: catalog,
      onOpenInstance: _openInstance,
    );
    if (!mounted || body == null) return;
    final updated = await _model.updateAutomation(
        autils.automationId(automation), body);
    if (updated == null && mounted) {
      await SessionActions.showSnack(
          context, AppLocalizations.of(context).automationsSaveFailed);
    }
  }

  Future<void> _openInstance(String instanceId) async {
    await context.pushNamed(
      AgentChatWidget.routeName,
      pathParameters: {'instanceId': instanceId},
    );
  }

  Future<void> _confirmDelete(dynamic automation) async {
    final l10n = AppLocalizations.of(context);
    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: l10n.automationsDeleteConfirmTitle,
              content: l10n.automationsDeleteConfirmBody,
            ),
          ),
        ) ??
        false;
    if (!confirmed || !mounted) return;
    HapticFeedback.mediumImpact();
    final ok = await _model.deleteAutomation(autils.automationId(automation));
    if (mounted) {
      await SessionActions.showSnack(
          context, ok ? l10n.automationsDeleted : l10n.automationsSaveFailed);
    }
  }

  Future<void> _runNow(dynamic automation) async {
    HapticFeedback.mediumImpact();
    final l10n = AppLocalizations.of(context);
    final result = await _model.runNow(automation);
    if (!mounted) return;
    switch (result['status']) {
      case 'fired':
        await SessionActions.showSnack(context, l10n.automationsRunStarted);
        final instanceId = result['instanceId']?.toString();
        if (instanceId != null && mounted) await _openInstance(instanceId);
        break;
      case 'missed_offline':
        await SessionActions.showSnack(context, l10n.automationsMachineOffline);
        break;
      default:
        await SessionActions.showSnack(context, l10n.automationsRunFailed);
    }
  }

  /// Anchored filter dropdown under the header icon (styled like the Tasks
  /// filter): All / Active / Paused.
  Future<void> _showFilterMenu() async {
    HapticFeedback.lightImpact();
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    Icon leading(IconData icon) =>
        Icon(icon, size: 16.0, color: theme.secondaryText);
    final picked = await showAnchoredSingleSelect<String>(
      context: context,
      anchorKey: _filterButtonKey,
      selected: _model.filter,
      alignRight: true,
      width: 180.0,
      options: [
        PickerOption(
          value: 'all',
          leading: leading(Icons.all_inclusive_rounded),
          label: l10n.automationsFilterAll,
        ),
        PickerOption(
          value: 'active',
          leading: leading(Icons.circle_outlined),
          label: l10n.automationsFilterActive,
        ),
        PickerOption(
          value: 'paused',
          leading: leading(Icons.pause_circle_outline_rounded),
          label: l10n.automationsFilterPaused,
        ),
      ],
    );
    if (picked != null) _model.setFilter(picked);
  }

  /// ⋯ action sheet: Run now / Pause·Resume / Delete.
  Future<void> _showActions(dynamic automation) async {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final enabled = autils.automationEnabled(automation);
    final action = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        decoration: BoxDecoration(
          color: theme.secondaryBackground,
          borderRadius:
              const BorderRadius.vertical(top: Radius.circular(24.0)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                margin: const EdgeInsets.only(top: 12.0, bottom: 8.0),
                width: 40.0,
                height: 4.0,
                decoration: BoxDecoration(
                  color: theme.alternate,
                  borderRadius: BorderRadius.circular(2.0),
                ),
              ),
              _actionRow(ctx, Icons.play_arrow_rounded,
                  l10n.automationsRunNow, 'run'),
              _actionRow(
                ctx,
                enabled
                    ? Icons.pause_rounded
                    : Icons.play_circle_outline_rounded,
                enabled ? l10n.automationsPause : l10n.automationsResume,
                'toggle',
              ),
              _actionRow(ctx, Icons.delete_outline_rounded,
                  l10n.automationsDelete, 'delete',
                  color: theme.error),
              const SizedBox(height: 8.0),
            ],
          ),
        ),
      ),
    );
    if (!mounted || action == null) return;
    switch (action) {
      case 'run':
        await _runNow(automation);
        break;
      case 'toggle':
        await _model.toggleEnabled(automation);
        break;
      case 'delete':
        await _confirmDelete(automation);
        break;
    }
  }

  Widget _actionRow(
      BuildContext sheetContext, IconData icon, String label, String value,
      {Color? color}) {
    final theme = FlutterFlowTheme.of(sheetContext);
    return InkWell(
      onTap: () {
        HapticFeedback.lightImpact();
        Navigator.pop(sheetContext, value);
      },
      child: Padding(
        padding:
            const EdgeInsets.symmetric(horizontal: 24.0, vertical: 14.0),
        child: Row(
          children: [
            Icon(icon, size: 22.0, color: color ?? theme.primaryText),
            const SizedBox(width: 14.0),
            Text(
              label,
              style: theme.bodyLarge.override(
                font: GoogleFonts.sourceSans3(),
                fontSize: 16.0,
                letterSpacing: 0.0,
                color: color ?? theme.primaryText,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // --- build -----------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      key: scaffoldKey,
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
        title: Text(
          l10n.automationsTitle,
          style: theme.titleLarge.override(
            font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500),
            letterSpacing: 0.0,
            fontWeight: FontWeight.w500,
          ),
        ),
        titleSpacing: 24.0,
        centerTitle: false,
        elevation: 0.0,
        actions: [
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 8.0, 0.0),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  key: _filterButtonKey,
                  child: FlutterFlowIconButton(
                    borderRadius: 10.0,
                    borderWidth: 0.0,
                    buttonSize: 40.0,
                    fillColor: Colors.transparent,
                    icon: Icon(
                      Icons.filter_list_rounded,
                      color: _model.filter != 'all'
                          ? theme.primary
                          : theme.primaryText,
                      size: 22.0,
                    ),
                    onPressed: _showFilterMenu,
                  ),
                ),
                FlutterFlowIconButton(
                  borderRadius: 10.0,
                  borderWidth: 0.0,
                  buttonSize: 40.0,
                  fillColor: Colors.transparent,
                  icon: Icon(Icons.add_rounded,
                      color: theme.primaryText, size: 24.0),
                  onPressed: _create,
                ),
              ],
            ),
          ),
        ],
      ),
      body: SafeArea(bottom: false, child: _buildBody(theme, l10n)),
    );
  }

  Widget _buildBody(FlutterFlowTheme theme, AppLocalizations l10n) {
    if (_model.isLoading && _model.automations.isEmpty) {
      return Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
        ),
      );
    }
    if (_model.hasError && _model.automations.isEmpty) {
      return _messageState(
        theme,
        icon: Icons.cloud_off_rounded,
        title: l10n.automationsCouldNotLoad,
        subtitle: l10n.automationsPullToRefresh,
      );
    }
    final visible = _model.filteredAutomations;
    if (visible.isEmpty) {
      return _messageState(
        theme,
        icon: Icons.schedule_rounded,
        title: l10n.automationsEmptyTitle,
        subtitle: l10n.automationsEmptySubtitle,
        // Only offer to create when a machine exists — an automation needs one
        // to run on. Without a computer connected, the button leads nowhere.
        cta: _model.automations.isEmpty && _model.machines.isNotEmpty
            ? l10n.automationsNew
            : null,
      );
    }
    return RefreshIndicator(
      color: theme.primary,
      onRefresh: () => _model.load(),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(
            top: 4.0, bottom: floatingTabBarBottomInset(context)),
        children: [
          for (final a in visible)
            AutomationCard(
              automation: a,
              isBusy: _model.busyId == autils.automationId(a),
              onTap: () => _edit(a),
              onToggleEnabled: () => _model.toggleEnabled(a),
              onShowActions: () => _showActions(a),
            ),
        ],
      ),
    );
  }

  /// Loading/empty/error state wrapped in a scrollable so pull-to-refresh
  /// still works when the list is empty (matches the Tasks page).
  Widget _messageState(
    FlutterFlowTheme theme, {
    required IconData icon,
    required String title,
    required String subtitle,
    String? cta,
  }) {
    return RefreshIndicator(
      color: theme.primary,
      onRefresh: () => _model.load(),
      child: LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Padding(
              padding: const EdgeInsets.all(32.0),
              child: Align(
                alignment: const Alignment(0.0, -0.35),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(icon, size: 56.0, color: theme.secondaryText),
                    const SizedBox(height: 16.0),
                    Text(
                      title,
                      textAlign: TextAlign.center,
                      style: theme.titleMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        letterSpacing: 0.0,
                      ),
                    ),
                    const SizedBox(height: 8.0),
                    Text(
                      subtitle,
                      textAlign: TextAlign.center,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.secondaryText,
                        letterSpacing: 0.0,
                      ),
                    ),
                    if (cta != null) ...[
                      const SizedBox(height: 20.0),
                      TextButton.icon(
                        onPressed: _create,
                        style: TextButton.styleFrom(
                          backgroundColor: theme.primary,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 18.0, vertical: 10.0),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                        ),
                        icon: const Icon(Icons.add_rounded, size: 20.0),
                        label: Text(
                          cta,
                          style: theme.bodyMedium.override(
                            font: GoogleFonts.sourceSans3(),
                            color: Colors.white,
                            letterSpacing: 0.0,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
