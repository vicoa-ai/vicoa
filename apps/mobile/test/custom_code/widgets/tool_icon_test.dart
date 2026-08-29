// Spec for the tool-use leading icon mapping
// (`lib/custom_code/widgets/tool_icon.dart`). Mirrors vicoa-web's
// `iconForToolName` / `TOOL_RANK` (components/dashboard/tool-use-display.tsx).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/widgets/tool_icon.dart';

void main() {
  group('iconForToolName', () {
    test('shell tools get the terminal glyph', () {
      expect(iconForToolName('Bash'), Icons.terminal);
      expect(iconForToolName('Exec'), Icons.terminal);
    });

    test('write-shaped tools get the pencil glyph', () {
      expect(iconForToolName('Edit'), Icons.edit_outlined);
      expect(iconForToolName('Edited'), Icons.edit_outlined);
      expect(iconForToolName('Write'), Icons.edit_outlined);
      expect(iconForToolName('MultiEdit'), Icons.edit_outlined);
    });

    test('is case- and separator-insensitive', () {
      expect(iconForToolName('bash'), Icons.terminal);
      expect(iconForToolName('to do write'), iconForToolName('TodoWrite'));
    });

    test('Task and any tool name containing "agent" get the bot glyph', () {
      expect(iconForToolName('Task'), Icons.smart_toy_outlined);
      expect(iconForToolName('Subagent'), Icons.smart_toy_outlined);
    });

    test('search-shaped tools get the search glyph', () {
      expect(iconForToolName('Grep'), Icons.search);
      expect(iconForToolName('Glob'), Icons.search);
      expect(iconForToolName('Search'), Icons.search);
    });

    test('web tools get the globe glyph', () {
      expect(iconForToolName('WebFetch'), Icons.public);
      expect(iconForToolName('WebSearch'), Icons.public);
    });

    test('unknown tools fall back to the wrench glyph', () {
      expect(iconForToolName('NotebookEdit'), Icons.build_outlined);
      expect(iconForToolName('SomeCustomTool'), Icons.build_outlined);
    });
  });

  group('isAgentToolName', () {
    test('matches Task and any name containing "agent"', () {
      expect(isAgentToolName('Task'), true);
      expect(isAgentToolName('Subagent'), true);
      expect(isAgentToolName('Agent'), true);
      expect(isAgentToolName('Bash'), false);
    });
  });

  group('representativeToolName', () {
    test('Task/Agent outranks every other tool in a run', () {
      expect(representativeToolName(['Bash', 'Task', 'Edit']), 'Task');
    });

    test('an edit outranks a read, which outranks a search', () {
      expect(representativeToolName(['Read', 'Edit']), 'Edit');
      expect(representativeToolName(['Search', 'Read']), 'Read');
    });

    test('a shell command outranks a todo list', () {
      expect(representativeToolName(['Todos', 'Bash']), 'Bash');
    });

    test('empty and unranked names are skipped or sort last', () {
      expect(representativeToolName(['', 'Bash']), 'Bash');
      expect(representativeToolName(['UnknownTool', 'Read']), 'Read');
    });

    test('an empty run has no representative', () {
      expect(representativeToolName([]), '');
    });
  });
}
