import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '/components/floating_tab_bar.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/agent_chat/agent_chat_widget.dart';
import '/pages/common/session_actions.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import '/pages/main_tabs/main_tabs_controller.dart';
import '/pages/new_session/new_session_widget.dart';
import 'task_card.dart';
import 'task_detail_sheet.dart';
import 'task_edit_sheet.dart';
import 'task_filter_panel.dart';
import 'task_glyphs.dart';
import 'task_l10n.dart';
import 'tasks_model.dart';
export 'tasks_model.dart';

/// The human task backlog, ported from the web dashboard. A list grouped by
/// status (collapsible sections), with create/edit via a bottom sheet and a
/// "Start session" bridge that hands a task to the New Session flow. Entry
/// point: the checklist icon in the Home header.
class TasksWidget extends StatefulWidget {
  const TasksWidget({super.key});

  static String routeName = 'Tasks';
  static String routePath = '/tasks';

  @override
  State<TasksWidget> createState() => _TasksWidgetState();
}

class _TasksWidgetState extends State<TasksWidget> {
  late TasksModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final GlobalKey _filterButtonKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => TasksModel());
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'Tasks'});
    MainTabsController.instance.openTaskId.addListener(_onOpenTaskRequested);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      await _model.load();
      // Handle a search "open task" that arrived before this tab first built.
      _consumePendingOpenTask();
    });
  }

  @override
  void dispose() {
    MainTabsController.instance.openTaskId.removeListener(_onOpenTaskRequested);
    _model.dispose();
    super.dispose();
  }

  void _onOpenTaskRequested() => _consumePendingOpenTask();

  bool _openingPendingTask = false;

  /// Opens the task the search page routed to, loading the list first if this
  /// tab hasn't fetched yet. Clears the request up front so it fires once.
  Future<void> _consumePendingOpenTask() async {
    final id = MainTabsController.instance.openTaskId.value;
    if (id == null || id.isEmpty || _openingPendingTask || !mounted) return;
    _openingPendingTask = true;
    MainTabsController.instance.openTaskId.value = null;
    try {
      if (_model.tasks.isEmpty) await _model.load();
      if (!mounted) return;
      final task = _model.tasks.firstWhere(
        (t) => tutils.taskId(t) == id,
        orElse: () => null,
      );
      if (task != null) await _openTask(task);
    } finally {
      _openingPendingTask = false;
    }
  }

  // --- actions ---------------------------------------------------------------

  /// Opens a task's detail sheet. Tapping the parent breadcrumb or a sub-task
  /// row navigates to that task — handled as a flat loop (each sheet is popped
  /// before the next opens) rather than recursion, so no re-entrant sheet
  /// presentation can build up regardless of how deep you drill.
  Future<void> _openTask(dynamic task) async {
    var current = task;
    while (true) {
      if (!mounted) return;
      final id = tutils.taskId(current);
      final parentId = tutils.taskParentId(current);
      final parentTask = parentId == null
          ? null
          : _model.tasks.firstWhere(
              (t) => tutils.taskId(t) == parentId,
              orElse: () => null,
            );
      final subtasks =
          _model.tasks.where((t) => tutils.taskParentId(t) == id).toList();
      final action = await showTaskDetailSheet(
        context: context,
        task: current,
        project: _model.projectById(tutils.taskProjectId(current)),
        parentTask: parentTask,
        subtasks: subtasks,
      );
      if (!mounted || action == null) return;
      if (action.startsWith('open:')) {
        final target = _model.tasks.firstWhere(
          (t) => tutils.taskId(t) == action.substring(5),
          orElse: () => null,
        );
        if (target == null) return;
        current = target;
        continue;
      }
      switch (action) {
        case 'start':
          await _startSession(current);
          break;
        case 'edit':
          await _editTask(current);
          break;
        case 'delete':
          await _confirmDelete(current);
          break;
      }
      return;
    }
  }

  /// Where a newly-created task lands: the active project filter if one is set,
  /// otherwise the Inbox.
  String? _defaultProjectId() {
    if (_model.projectFilter != null) return _model.projectFilter;
    final inbox = _model.inboxProject;
    return inbox != null ? tutils.projectId(inbox) : null;
  }

  Future<void> _createTask() async {
    HapticFeedback.lightImpact();
    final values = await showTaskEditSheet(
      context: context,
      task: null,
      projects: _model.projects,
      labels: _model.labels,
      defaultProjectId: _defaultProjectId(),
    );
    if (!mounted || values == null) return;
    final ok = await _model.createTask(values);
    if (!ok && mounted) {
      await SessionActions.showSnack(
          context, AppLocalizations.of(context).tasksSaveFailed);
    }
  }

  Future<void> _editTask(dynamic task) async {
    final values = await showTaskEditSheet(
      context: context,
      task: task,
      projects: _model.projects,
      labels: _model.labels,
    );
    if (!mounted || values == null) return;
    final ok = await _model.updateTask(tutils.taskId(task), values);
    if (!ok && mounted) {
      await SessionActions.showSnack(
          context, AppLocalizations.of(context).tasksSaveFailed);
    }
  }

  Future<void> _confirmDelete(dynamic task) async {
    final l10n = AppLocalizations.of(context);
    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: l10n.tasksDeleteConfirmTitle,
              content: l10n.tasksDeleteConfirmBody,
            ),
          ),
        ) ??
        false;
    if (!confirmed || !mounted) return;
    HapticFeedback.mediumImpact();
    await _model.deleteTask(tutils.taskId(task));
    if (mounted) {
      await SessionActions.showSnack(context, l10n.tasksTaskDeleted);
    }
  }

  /// Hand the task to the existing New Session flow. The New Session page links
  /// the spawned instance back to the task (sets `task_id` and advances the task
  /// to in_progress) before returning its success map — mirror Home's handling
  /// and open the chat.
  Future<void> _startSession(dynamic task) async {
    // Seed the first prompt with the task content plus its backlog/todo
    // sub-tasks as a checklist, and advance those sub-tasks to in_progress on
    // spawn — mirrors the web start-session flow.
    final subtasks = _model.tasks
        .where((t) =>
            tutils.taskParentId(t) == tutils.taskId(task) &&
            (tutils.taskStatus(t) == 'backlog' ||
                tutils.taskStatus(t) == 'todo'))
        .toList();
    final result = await context.pushNamed(
      NewSessionWidget.routeName,
      extra: <String, dynamic>{
        'taskContext': {
          'taskId': tutils.taskId(task),
          'initialPrompt': tutils.composeTaskPrompt(task, subtasks: subtasks),
          'subtaskIds': subtasks.map((s) => tutils.taskId(s)).toList(),
        },
      },
    );
    if (!mounted) return;
    if (result is Map && result['status'] == 'success') {
      await _model.load(); // reflect status → in_progress
      final instanceId = result['instanceId'];
      final instanceData = result['instanceData'];
      if (instanceId != null && mounted) {
        await context.pushNamed(
          AgentChatWidget.routeName,
          pathParameters: {'instanceId': instanceId.toString()},
          extra: <String, dynamic>{
            'instanceData': instanceData,
            'hasInitialPrompt': result['hasInitialPrompt'] == true,
          },
        );
        if (mounted) await _model.load();
      }
    }
  }

  /// Anchored filter/display dropdown under the header icon — see
  /// `task_filter_panel.dart` (styled like the Home agent-filters panel, with
  /// a "Project" filter section and a multi-select "Display" section).
  Future<void> _showFilterMenu() async {
    HapticFeedback.lightImpact();
    await showTaskFilterPanel(
      context: context,
      model: _model,
      onStateChanged: () {
        if (mounted) setState(() {});
      },
      anchorKey: _filterButtonKey,
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
        // Rendered as a tab inside the main shell — no back button.
        automaticallyImplyLeading: false,
        title: Text(
          l10n.tasksTitle,
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
                      color: _model.projectFilter != null
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
                  onPressed: _createTask,
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
    if (_model.isLoading && _model.tasks.isEmpty) {
      return Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
        ),
      );
    }
    if (_model.hasError && _model.tasks.isEmpty) {
      return _MessageState(
        icon: Icons.cloud_off_rounded,
        title: l10n.tasksCouldNotLoad,
        subtitle: l10n.tasksPullToRefresh,
        onRetry: () => _model.load(),
      );
    }
    final visible = _model.filteredTasks;
    if (visible.isEmpty) {
      return _MessageState(
        icon: Icons.checklist_rounded,
        title: l10n.tasksNoTasksTitle,
        subtitle: l10n.tasksNoTasksSubtitle,
        onRetry: () => _model.load(),
        cta: l10n.tasksNewTask,
        onCta: _createTask,
      );
    }

    final grouped = tutils.groupTasksByStatus(visible);
    final children = <Widget>[];
    for (final status in tutils.kTaskStatusOrder) {
      final items = grouped[status] ?? const [];
      if (items.isEmpty) continue;
      final collapsed = _model.collapsed.contains(status);
      children.add(_buildSectionHeader(theme, l10n, status, items.length,
          collapsed));
      if (!collapsed) {
        for (final t in items) {
          children.add(TaskCard(
            task: t,
            project: _model.projectById(tutils.taskProjectId(t)),
            showStatus: _model.showStatus,
            showPriority: _model.showPriority,
            showProject: _model.showProject,
            showLabels: _model.showLabels,
            onTap: () => _openTask(t),
          ));
        }
      }
    }

    return RefreshIndicator(
      color: theme.primary,
      onRefresh: () => _model.load(),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(
            top: 4.0, bottom: floatingTabBarBottomInset(context)),
        children: children,
      ),
    );
  }

  Widget _buildSectionHeader(FlutterFlowTheme theme, AppLocalizations l10n,
      String status, int count, bool collapsed) {
    return InkWell(
      onTap: () {
        HapticFeedback.selectionClick();
        _model.toggleCollapsed(status);
      },
      child: Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 6.0),
        child: Row(
          children: [
            AnimatedRotation(
              turns: collapsed ? -0.25 : 0.0,
              duration: const Duration(milliseconds: 150),
              child: Icon(Icons.keyboard_arrow_down_rounded,
                  color: theme.secondaryText, size: 20.0),
            ),
            const SizedBox(width: 6.0),
            TaskStatusIcon(status: status, size: 14.0),
            const SizedBox(width: 8.0),
            Text(
              taskStatusLabel(l10n, status),
              style: theme.titleSmall.override(
                font: GoogleFonts.sourceSans3(),
                color: theme.primaryText,
                letterSpacing: 0.0,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(width: 8.0),
            Text(
              '$count',
              style: theme.labelMedium.override(
                font: GoogleFonts.sourceSans3(),
                color: theme.secondaryText,
                letterSpacing: 0.0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Full-screen loading/empty/error state, wrapped in a scrollable so pull-to-
/// refresh works even when the list is empty (matches the Machines page).
class _MessageState extends StatelessWidget {
  const _MessageState({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onRetry,
    this.cta,
    this.onCta,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Future<void> Function() onRetry;

  /// Optional call-to-action button under the subtitle (e.g. "New task").
  final String? cta;
  final VoidCallback? onCta;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return RefreshIndicator(
      color: theme.primary,
      onRefresh: onRetry,
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
                    if (cta != null && onCta != null) ...[
                      const SizedBox(height: 20.0),
                      TextButton.icon(
                        onPressed: onCta,
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
                          cta!,
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
