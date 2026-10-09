// The Tasks and Automations pages share one project filter: null = all,
// `kNoProjectFilter` = filed nowhere, otherwise a project id. Automations are
// matched on the `project_id` the server derives from their folder.
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/automation_utils.dart';
import 'package:vicoa/custom_code/utils/task_utils.dart';
import 'package:vicoa/pages/common/filter_panel.dart';

void main() {
  final automations = [
    {'id': 'a1', 'project_id': 'p1'},
    {'id': 'a2', 'project_id': null},
    {'id': 'a3', 'project_id': 'p2'},
    {'id': 'a4'}, // an older backend that doesn't send the field
  ];
  List<String> ids(List<dynamic> rows) => rows.map((r) => r['id'] as String).toList();

  group('filterByProject', () {
    test('null keeps everything', () {
      expect(ids(filterByProject(automations, null, automationProjectId)), ['a1', 'a2', 'a3', 'a4']);
    });

    test('a project id keeps that project only', () {
      expect(ids(filterByProject(automations, 'p2', automationProjectId)), ['a3']);
    });

    test('No project keeps the unfiled ones', () {
      expect(ids(filterByProject(automations, kNoProjectFilter, automationProjectId)), ['a2', 'a4']);
    });
  });

  group('taskIdentifier', () {
    test('is the rendered key', () {
      expect(taskIdentifier({'identifier': 'VIC-42'}), 'VIC-42');
    });

    test('is null for a task without one', () {
      expect(taskIdentifier({'identifier': null}), isNull);
      expect(taskIdentifier({'identifier': ''}), isNull);
      expect(taskIdentifier(<String, dynamic>{}), isNull);
    });
  });
}
