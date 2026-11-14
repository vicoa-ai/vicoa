import 'dart:async' show unawaited;

import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_util.dart';
import '/pages/common/filter_panel.dart' show filterByProject;
import 'tasks_widget.dart' show TasksWidget;

/// State for the Tasks list. Fetches tasks + projects + labels over REST, holds
/// the local project filter, card display options and per-status collapse
/// state (all three remembered across launches in `UserPreferences`), and owns
/// the CRUD calls. Tasks/projects/labels are dynamic maps (see `task_utils.dart`).
class TasksModel extends FlutterFlowModel<TasksWidget> {
  List<dynamic> tasks = [];
  List<dynamic> projects = [];
  List<dynamic> labels = [];
  bool isLoading = false;
  bool hasError = false;

  /// null → all projects; otherwise a project id.
  String? projectFilter;

  /// Which card properties to show (Display section of the header filter).
  /// Status is off by default since the section grouping already conveys it.
  bool showStatus = false;
  bool showPriority = true;
  bool showProject = true;
  bool showLabels = true;

  /// Statuses whose section is collapsed in the list.
  final Set<String> collapsed = {};

  VoidCallback? _notify;
  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  @override
  void initState(BuildContext context) => restoreSavedView();

  /// Opens the list the way it was left: project filter, display options and
  /// folded sections, as saved in `UserPreferences`.
  void restoreSavedView() {
    final prefs = FFAppState().userPreferences;
    projectFilter = prefs.tasksProjectFilter;
    showStatus = prefs.tasksShowStatus;
    showPriority = prefs.tasksShowPriority;
    showProject = prefs.tasksShowProject;
    showLabels = prefs.tasksShowLabels;
    collapsed
      ..clear()
      ..addAll(prefs.tasksCollapsedStatuses);
  }

  void _saveCollapsed() {
    FFAppState().updateUserPreferences((p) => p..tasksCollapsedStatuses = collapsed.toList());
  }

  @override
  void dispose() {}

  Future<void> load() async {
    isLoading = tasks.isEmpty; // spinner only on first load
    hasError = false;
    _bump();
    try {
      final results = await Future.wait([
        actions.apiGetTasks(),
        actions.apiGetProjects(),
        actions.apiGetTaskLabels(),
      ]);
      tasks = results[0];
      projects = results[1];
      labels = results[2];
      dropMissingProjectFilter();
    } catch (e) {
      debugPrint('Error loading tasks: $e');
      if (tasks.isEmpty) hasError = true;
    } finally {
      isLoading = false;
      _bump();
    }
  }

  /// A remembered project filter can outlive its project (deleted, archived,
  /// another account signed in), which would leave the list empty for no
  /// visible reason: fall back to all projects. An empty project list may be a
  /// failed fetch (`apiGetProjects` returns [] on error), so it proves nothing.
  @visibleForTesting
  void dropMissingProjectFilter() {
    final filter = projectFilter;
    if (filter == null || filter == tutils.kNoProjectFilter || projects.isEmpty) return;
    if (projectById(filter) == null) setProjectFilter(null);
  }

  List<dynamic> get filteredTasks =>
      filterByProject(tasks, projectFilter, tutils.taskProjectId);

  dynamic projectById(String? id) {
    if (id == null) return null;
    for (final p in projects) {
      if (tutils.projectId(p) == id) return p;
    }
    return null;
  }

  /// Creates the task and returns it as the server sent it, or null when the
  /// request failed. The POST answers with the full task, in the same shape as
  /// a list row, so it goes into the list right away; the tasks reload runs
  /// alongside instead of being waited on.
  Future<dynamic> createTask(Map<String, dynamic> values) async {
    final created = await actions.apiCreateTask(
      title: values['title'] as String,
      description: values['description'] as String?,
      projectId: values['project_id'] as String?,
      status: values['status'] as String?,
      priority: values['priority'] as String?,
      labelIds: (values['label_ids'] as List?)?.cast<String>(),
    );
    if (created == null) return null;
    tasks = [...tasks, created];
    _bump();
    unawaited(_refreshTasksAfterCreate(created));
    return created;
  }

  /// Replaces the list with the server's copy after [createTask]. Only tasks
  /// are fetched: creating one changes neither projects nor labels.
  /// `apiGetTasks` returns [] on error, and a task was just created, so an
  /// empty answer is a failed fetch: keep what is on screen. A copy without
  /// the new task (a lagging read) gets it added back.
  Future<void> _refreshTasksAfterCreate(dynamic created) async {
    final fresh = await actions.apiGetTasks();
    if (fresh.isEmpty) return;
    final id = tutils.taskId(created);
    tasks = fresh.any((t) => tutils.taskId(t) == id)
        ? fresh
        : [...fresh, created];
    _bump();
  }

  Future<bool> updateTask(String id, Map<String, dynamic> updates) async {
    final result = await actions.apiUpdateTask(id, updates);
    if (result != null) {
      await load();
      return true;
    }
    return false;
  }

  Future<void> deleteTask(String id) async {
    // Optimistically drop it — the 204 delete can report false through the
    // shared request helper even on success — then reconcile with a reload.
    tasks = tasks.where((t) => tutils.taskId(t) != id).toList();
    _bump();
    await actions.apiDeleteTask(id);
    await load();
  }

  void toggleCollapsed(String status) {
    if (!collapsed.remove(status)) collapsed.add(status);
    _saveCollapsed();
    _bump();
  }

  /// Unfolds a section, e.g. so a task just created inside it is on screen.
  void expandSection(String status) {
    if (!collapsed.remove(status)) return;
    _saveCollapsed();
    _bump();
  }

  void setProjectFilter(String? projectId) {
    projectFilter = projectId;
    FFAppState().updateUserPreferences((p) => p..tasksProjectFilter = projectId);
    _bump();
  }

  void setDisplay({bool? status, bool? priority, bool? project, bool? labels}) {
    if (status != null) showStatus = status;
    if (priority != null) showPriority = priority;
    if (project != null) showProject = project;
    if (labels != null) showLabels = labels;
    FFAppState().updateUserPreferences((p) => p
      ..tasksShowStatus = showStatus
      ..tasksShowPriority = showPriority
      ..tasksShowProject = showProject
      ..tasksShowLabels = showLabels);
    _bump();
  }
}
