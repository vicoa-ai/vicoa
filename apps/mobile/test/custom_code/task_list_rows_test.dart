// The Tasks page lists status sections as one flat run of rows (header, then
// its cards) so it can build lazily and scroll to a just-created task by index.
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/task_utils.dart';

void main() {
  Map<String, dynamic> task(String id, String status, {double position = 0}) =>
      {'id': id, 'status': status, 'position': position};

  List<String> describe(List<TaskListRow> rows) => rows
      .map((r) => r.isHeader ? '#${r.status}(${r.count})' : taskId(r.task))
      .toList();

  group('flattenTaskRows', () {
    final tasks = [
      task('d1', 'done'),
      task('t2', 'todo', position: 2),
      task('t1', 'todo', position: 1),
      task('p1', 'in_progress'),
    ];

    test('puts each non-empty section in status order, header first', () {
      final rows = flattenTaskRows(groupTasksByStatus(tasks), {});
      expect(describe(rows),
          ['#todo(2)', 't1', 't2', '#in_progress(1)', 'p1', '#done(1)', 'd1']);
    });

    test('a folded section keeps its header and count but hides its tasks', () {
      final rows = flattenTaskRows(groupTasksByStatus(tasks), {'todo'});
      expect(describe(rows),
          ['#todo(2)', '#in_progress(1)', 'p1', '#done(1)', 'd1']);
      expect(rows.first.collapsed, isTrue);
      expect(rows[1].collapsed, isFalse);
    });

    test('has no rows without tasks', () {
      expect(flattenTaskRows(groupTasksByStatus([]), {}), isEmpty);
    });
  });

  group('indexOfTaskRow', () {
    final tasks = [task('t1', 'todo'), task('d1', 'done')];

    test('finds the task row, not the header', () {
      final rows = flattenTaskRows(groupTasksByStatus(tasks), {});
      expect(indexOfTaskRow(rows, 't1'), 1);
      expect(indexOfTaskRow(rows, 'd1'), 3);
    });

    test('is -1 for a task in a folded section or one that is not listed', () {
      final rows = flattenTaskRows(groupTasksByStatus(tasks), {'done'});
      expect(indexOfTaskRow(rows, 'd1'), -1);
      expect(indexOfTaskRow(rows, 'missing'), -1);
    });
  });
}
