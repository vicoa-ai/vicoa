import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_util.dart';
import 'tasks_widget.dart' show TasksWidget;

/// State for the Tasks list. Fetches tasks + projects + labels over REST, holds
/// the local project filter and per-status collapse state, and owns the CRUD
/// calls. Tasks/projects/labels are dynamic maps (see `task_utils.dart`).
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
  void initState(BuildContext context) {}

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
    } catch (e) {
      debugPrint('Error loading tasks: $e');
      if (tasks.isEmpty) hasError = true;
    } finally {
      isLoading = false;
      _bump();
    }
  }

  List<dynamic> get filteredTasks {
    if (projectFilter == null) return tasks;
    return tasks
        .where((t) => tutils.taskProjectId(t) == projectFilter)
        .toList();
  }

  dynamic projectById(String? id) {
    if (id == null) return null;
    for (final p in projects) {
      if (tutils.projectId(p) == id) return p;
    }
    return null;
  }

  /// The non-deletable Inbox ("No project") project, if present.
  dynamic get inboxProject {
    for (final p in projects) {
      if (tutils.projectIsInbox(p)) return p;
    }
    return null;
  }

  Future<bool> createTask(Map<String, dynamic> values) async {
    final result = await actions.apiCreateTask(
      title: values['title'] as String,
      description: values['description'] as String?,
      projectId: values['project_id'] as String?,
      status: values['status'] as String?,
      priority: values['priority'] as String?,
      labelIds: (values['label_ids'] as List?)?.cast<String>(),
    );
    if (result != null) {
      await load();
      return true;
    }
    return false;
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
    _bump();
  }

  void setProjectFilter(String? projectId) {
    projectFilter = projectId;
    _bump();
  }

  void setDisplay({bool? status, bool? priority, bool? project, bool? labels}) {
    if (status != null) showStatus = status;
    if (priority != null) showPriority = priority;
    if (project != null) showProject = project;
    if (labels != null) showLabels = labels;
    _bump();
  }
}
