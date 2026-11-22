// Spec for the Tasks list opening the way it was left:
//   - the project and Relation to me filters, card display options and folded
//     sections are saved as they change and come back after a relaunch;
//   - a remembered relation value this build doesn't know is dropped;
//   - the relation filter narrows the list together with the project filter;
//   - unfolding a section (e.g. to show a task just created) is saved too;
//   - a saved filter whose project is gone falls back to all projects, but an
//     empty project list (maybe a failed fetch) and "No project" keep it;
//   - prefs saved before these settings existed load the old defaults.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:vicoa/app_state.dart';
import 'package:vicoa/custom_code/utils/task_relation.dart';
import 'package:vicoa/custom_code/utils/task_utils.dart' as tutils;
import 'package:vicoa/pages/tasks/tasks_model.dart';

/// Reloads the app state from what was written to disk, as a relaunch does.
Future<void> _relaunch() async {
  final saved = FFAppState().prefs.getString('ff_userPreferences');
  SharedPreferences.setMockInitialValues({if (saved != null) 'ff_userPreferences': saved});
  await FFAppState().initializePersistedState();
}

TasksModel _openTasks() => TasksModel()..restoreSavedView();

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await FFAppState().initializePersistedState();
  });

  test('filter, display options and folded sections survive a relaunch', () async {
    _openTasks()
      ..setProjectFilter('p-1')
      ..setDisplay(status: true, labels: false)
      ..toggleCollapsed('done')
      ..toggleCollapsed('cancelled');

    await _relaunch();
    final model = _openTasks();
    expect(model.projectFilter, 'p-1');
    expect([model.showStatus, model.showPriority, model.showProject, model.showLabels], [true, true, true, false]);
    expect(model.collapsed, {'done', 'cancelled'});
  });

  test('the Relation to me filter survives a relaunch', () async {
    _openTasks()
      ..toggleRelation(kTaskRelationWaiting)
      ..toggleRelation(kTaskRelationAssigned);

    await _relaunch();
    final model = _openTasks();
    expect(model.relationFilter, {kTaskRelationAssigned, kTaskRelationWaiting});
    expect(model.isFiltered, isTrue);

    model
      ..toggleRelation(kTaskRelationAssigned)
      ..toggleRelation(kTaskRelationWaiting);
    await _relaunch();
    expect(_openTasks().relationFilter, isEmpty);
    expect(_openTasks().isFiltered, isFalse);
  });

  test('a remembered relation this build does not know is dropped', () async {
    SharedPreferences.setMockInitialValues({
      'ff_userPreferences': jsonEncode({'tasksRelationFilter': ['mentioned', 'waiting']}),
    });
    await FFAppState().initializePersistedState();
    expect(_openTasks().relationFilter, {kTaskRelationWaiting});
  });

  test('the relation filter narrows the list together with the project filter', () {
    final model = _openTasks()
      ..viewerId = 'u-me'
      ..tasks = [
        {'id': 't1', 'project_id': 'p-1', 'assignee_type': 'user', 'assignee_id': 'u-me'},
        {'id': 't2', 'project_id': 'p-2', 'assignee_type': 'user', 'assignee_id': 'u-me'},
        {'id': 't3', 'project_id': 'p-1', 'assignee_type': 'agent', 'assignee_id': 'a-1'},
      ];
    List<String> ids() => model.filteredTasks.map(tutils.taskId).toList();

    expect(ids(), ['t1', 't2', 't3']);
    model.toggleRelation(kTaskRelationAssigned);
    expect(ids(), ['t1', 't2']);
    model.setProjectFilter('p-1');
    expect(ids(), ['t1']);
    model.clearRelationFilter();
    expect(ids(), ['t1', 't3']);
  });

  test('unfolding a section is saved', () async {
    _openTasks()
      ..toggleCollapsed('done')
      ..expandSection('done');

    await _relaunch();
    expect(_openTasks().collapsed, isEmpty);
  });

  test('a saved filter on a project that is gone falls back to all projects', () async {
    final model = _openTasks()..setProjectFilter('gone');
    model.projects = [{'id': 'p-1', 'name': 'One'}];
    model.dropMissingProjectFilter();
    expect(model.projectFilter, isNull);

    await _relaunch();
    expect(_openTasks().projectFilter, isNull);
  });

  test('an empty project list or the No project filter keeps the filter', () {
    final model = _openTasks()..setProjectFilter('p-1');
    model.dropMissingProjectFilter();
    expect(model.projectFilter, 'p-1');

    model
      ..projects = [{'id': 'p-1', 'name': 'One'}]
      ..setProjectFilter(tutils.kNoProjectFilter)
      ..dropMissingProjectFilter();
    expect(model.projectFilter, tutils.kNoProjectFilter);
  });

  test('prefs saved before these settings existed load the defaults', () async {
    SharedPreferences.setMockInitialValues({
      'ff_userPreferences': jsonEncode({'homeFilterGroupBy': 'Project'}),
    });
    await FFAppState().initializePersistedState();
    final model = _openTasks();
    expect(model.projectFilter, isNull);
    expect(model.relationFilter, isEmpty);
    expect([model.showStatus, model.showPriority, model.showProject, model.showLabels], [false, true, true, true]);
    expect(model.collapsed, isEmpty);
  });
}
