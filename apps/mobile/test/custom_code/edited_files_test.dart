// Spec for the pure helpers behind the edited-file chips
// (`lib/custom_code/utils/edited_files.dart`): which tools are edits, the
// `+N -M` stat, and which tool-row paths the viewer can open.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/edited_files.dart';

void main() {
  group('isFileEditToolName', () {
    test('matches the editing tools regardless of case or separators', () {
      for (final name in ['Edit', 'edit', 'Write', 'MultiEdit', 'multi_edit', 'Edited']) {
        expect(isFileEditToolName(name), isTrue, reason: name);
      }
    });

    test('rejects everything else, including tools that only read a file', () {
      for (final name in ['Read', 'Bash', 'Exec', 'Glob', 'Todos', '']) {
        expect(isFileEditToolName(name), isFalse, reason: name);
      }
    });
  });

  group('diff stats', () {
    test('parses a reported +N -M', () {
      expect(parseDiffStat('+3 -1'), const DiffStat(3, 1));
      expect(parseDiffStat(' +12 -0 '), const DiffStat(12, 0));
      expect(parseDiffStat('3 -1'), isNull);
      expect(parseDiffStat(null), isNull);
    });

    test('derives a stat from the fenced diff, ignoring file headers and '
        'anything outside the fence', () {
      const body = 'ignored +line\n'
          '```diff\n'
          '--- a/x\n'
          '+++ b/x\n'
          '-old\n'
          '+new\n'
          '+more\n'
          ' ctx\n'
          '```\n'
          '-not counted';
      expect(diffStatFromContent(body), const DiffStat(2, 1));
    });

    test('no fence, or a fence with no changes, is null', () {
      expect(diffStatFromContent('+a\n-b'), isNull);
      expect(diffStatFromContent('```\nplain\n```'), isNull);
    });

    test('stats add', () {
      expect(const DiffStat(1, 2) + const DiffStat(3, 4), const DiffStat(4, 6));
      expect(const DiffStat(4, 6).toString(), '+4 -6');
    });
  });

  group('workspaceRelativePath', () {
    test('a project-relative path (the root already stripped) opens as is', () {
      expect(workspaceRelativePath('lib/main.dart'), 'lib/main.dart');
      expect(workspaceRelativePath('README.md'), 'README.md');
    });

    test('drops ./ and folds . segments', () {
      expect(workspaceRelativePath('./lib/./main.dart'), 'lib/main.dart');
    });

    test('folds .. within the project', () {
      expect(workspaceRelativePath('lib/../test/a_test.dart'), 'test/a_test.dart');
    });

    test('a path that climbs out of the project is outside', () {
      expect(workspaceRelativePath('../other/x.dart'), isNull);
      expect(workspaceRelativePath('lib/../../x.dart'), isNull);
    });

    test('a still-rooted path lies outside the project (or the root is '
        'unknown) and cannot be opened', () {
      expect(workspaceRelativePath('/etc/hosts'), isNull);
      expect(workspaceRelativePath('~/notes.md'), isNull);
      expect(workspaceRelativePath(r'C:\src\x.dart'), isNull);
      expect(workspaceRelativePath(r'\\server\share'), isNull);
    });

    test('empty and root-only paths are nothing to open', () {
      expect(workspaceRelativePath(''), isNull);
      expect(workspaceRelativePath('.'), isNull);
      expect(workspaceRelativePath('./'), isNull);
    });

    test('backslash separators are normalised', () {
      expect(workspaceRelativePath(r'lib\main.dart'), 'lib/main.dart');
    });
  });
}
