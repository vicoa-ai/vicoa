// Spec for the collapsed tool-use run label + summary parsing
// (`lib/custom_code/widgets/tool_use_group.dart`). Mirrors the vicoa-web
// `describeToolRun` behaviour ported for the Flutter chat.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/widgets/subagent_group.dart';
import 'package:vicoa/custom_code/widgets/tool_use_group.dart';

/// Local stand-in for the chat page's `_collectToolRunIndices`/
/// `_isCollapseRunStart`, built entirely from public/pure pieces
/// (`computeSubagentGrouping` + `isCollapsibleToolUseMessage`) so the
/// cross-task fix — sub-agent-tagged messages must never join a tool-use run
/// — is exercised the same way the real page wires it, without needing
/// access to the page's private State methods.
List<List<int>> _toolRuns(List<Map<String, dynamic>> messages) {
  final subagents = computeSubagentGrouping(messages);
  bool collapsible(int i) {
    if (i < 0 || i >= messages.length) return false;
    final m = messages[i];
    final sender = m['sender_type']?.toString().toLowerCase() ?? '';
    final content = m['content']?.toString() ?? '';
    return isCollapsibleToolUseMessage(
      isUserOrHumanSender: sender == 'user' || sender == 'human',
      requiresUserInput: m['requires_user_input'] == true,
      hasAskUserQuestionPayload: false,
      isAskUserQuestionTool: isAskUserQuestionToolContent(content),
      isSubagentMessage: subagents.isSubagentMessage(i),
      isToolUseContent: content.trim().startsWith('Using tool:'),
      hasValidOptionsBlock: false,
    );
  }

  final runs = <List<int>>[];
  for (int i = 0; i < messages.length; i++) {
    if (!collapsible(i) || collapsible(i - 1)) continue;
    final run = <int>[];
    for (int j = i; collapsible(j); j++) {
      run.add(j);
    }
    runs.add(run);
  }
  return runs;
}

void main() {
  group('isCollapsibleToolUseMessage', () {
    bool base({
      bool isUserOrHumanSender = false,
      bool requiresUserInput = false,
      bool hasAskUserQuestionPayload = false,
      bool isAskUserQuestionTool = false,
      bool isSubagentMessage = false,
      bool isToolUseContent = true,
      bool hasValidOptionsBlock = false,
    }) =>
        isCollapsibleToolUseMessage(
          isUserOrHumanSender: isUserOrHumanSender,
          requiresUserInput: requiresUserInput,
          hasAskUserQuestionPayload: hasAskUserQuestionPayload,
          isAskUserQuestionTool: isAskUserQuestionTool,
          isSubagentMessage: isSubagentMessage,
          isToolUseContent: isToolUseContent,
          hasValidOptionsBlock: hasValidOptionsBlock,
        );

    test('a plain agent tool-use message is collapsible', () {
      expect(base(), isTrue);
    });

    test('sub-agent-tagged messages are never collapsible, even when every '
        'other flag says "tool use" — they are owned by SubagentGroup, not '
        'the tool-use run collapser (the cross-task fix)', () {
      expect(base(isSubagentMessage: true), isFalse);
    });

    test('user/human senders are excluded', () {
      expect(base(isUserOrHumanSender: true), isFalse);
    });

    test('requires_user_input messages are excluded', () {
      expect(base(requiresUserInput: true), isFalse);
    });

    test('AskUserQuestion-carrying messages are excluded', () {
      expect(base(hasAskUserQuestionPayload: true), isFalse);
    });

    test('an AskUserQuestion tool use is excluded even with no payload — the '
        'announcement message has no metadata, so the payload check alone '
        'would let it fold into a run', () {
      expect(
        base(isAskUserQuestionTool: true, hasAskUserQuestionPayload: false),
        isFalse,
      );
    });

    test('non-tool-use content is excluded', () {
      expect(base(isToolUseContent: false), isFalse);
    });

    test('a valid [OPTIONS] block is excluded', () {
      expect(base(hasValidOptionsBlock: true), isFalse);
    });
  });

  group('tool-use run collection with sub-agent messages mixed in', () {
    Map<String, dynamic> tool(String label) =>
        {'sender_type': 'AGENT', 'content': 'Using tool: **Bash** - `$label`'};
    Map<String, dynamic> subagentTool(String toolUseId, String label) => {
          'sender_type': 'AGENT',
          'content': 'Using tool: **Bash** - `$label`',
          'message_metadata': {
            'subagent': {'tool_use_id': toolUseId, 'subagent_type': 'Explore'},
          },
        };

    test('a normal consecutive tool-use run still collapses as one run', () {
      final messages = [tool('a'), tool('b'), tool('c')];
      expect(_toolRuns(messages), [
        [0, 1, 2]
      ]);
    });

    test(
        'sub-agent-tagged tool messages interrupting a normal run are '
        'excluded from any tool run — the run stops before them and resumes '
        'after, instead of swallowing the sub-agent content', () {
      final messages = [
        tool('a'), // 0: normal run
        tool('b'), // 1: normal run
        subagentTool('tu-1', 'c'), // 2: sub-agent — must be excluded
        subagentTool('tu-1', 'd'), // 3: sub-agent — must be excluded
        tool('e'), // 4: normal run resumes
      ];
      final runs = _toolRuns(messages);
      expect(runs, [
        [0, 1],
        [4],
      ]);
      // Sub-agent indices never appear in any collected run.
      for (final run in runs) {
        expect(run.contains(2), isFalse);
        expect(run.contains(3), isFalse);
      }
    });

    test(
        'a sub-agent run whose FIRST child opens with a tool call is fully '
        'excluded from tool-run collapsing — this is the exact duplication '
        'scenario from the bug report (leading tool-formatted child getting '
        'absorbed into a consecutive tool-use group as well as rendering '
        'inside its SubagentGroup anchor)', () {
      final messages = [
        subagentTool('tu-1', 'grep'), // 0: sub-agent anchor, opens with a tool
        subagentTool('tu-1', 'read'), // 1: sub-agent child
        tool('after'), // 2: unrelated, normal tool use
      ];
      final runs = _toolRuns(messages);
      expect(runs, [
        [2]
      ]);
    });
  });

  group('AskUserQuestion is never grouped', () {
    Map<String, dynamic> tool(String label) =>
        {'sender_type': 'AGENT', 'content': 'Using tool: **Bash** - `$label`'};
    Map<String, dynamic> ask(String question) => {
          'sender_type': 'AGENT',
          'content': 'Using tool: **AskUserQuestion** - $question',
        };

    test('the tool name is recognised regardless of case or separators', () {
      expect(isAskUserQuestionToolContent(
          'Using tool: **AskUserQuestion** - Which one?'), isTrue);
      expect(isAskUserQuestionToolContent(
          'Using tool: askUserQuestion - Which one?'), isTrue);
      expect(isAskUserQuestionToolContent(
          'Using tool: **ask_user_question** - Which one?'), isTrue);
    });

    test('other tools are unaffected', () {
      expect(isAskUserQuestionToolContent('Using tool: **Bash** - `ls`'), isFalse);
      expect(isAskUserQuestionToolContent('Just some prose.'), isFalse);
    });

    test(
        'an AskUserQuestion splits the run rather than being folded into it — '
        'the question stays readable in place instead of collapsing behind a '
        'summary header', () {
      final messages = [
        tool('a'), // 0: run
        tool('b'), // 1: run
        ask('What next?'), // 2: standalone — must be excluded
        tool('c'), // 3: run resumes
      ];
      final runs = _toolRuns(messages);
      expect(runs, [
        [0, 1],
        [3],
      ]);
      for (final run in runs) {
        expect(run.contains(2), isFalse);
      }
    });

    test('back-to-back AskUserQuestions never merge into a run', () {
      final messages = [ask('First?'), ask('Second?')];
      expect(_toolRuns(messages), isEmpty);
    });
  });

  ToolUseSummary sum(String content) => summarizeToolMessage(content);

  group('describeToolRun', () {
    test('counts commands + distinct files, sentence-cased (first word only)',
        () {
      final tools = [
        sum('Using tool: **Bash** - `ls`'),
        sum('Using tool: **Edit** - `a.ts`'),
        sum('Using tool: **Bash** - `pwd`'),
        sum('Using tool: **Edit** - `b.ts`'),
        sum('Using tool: **Read** - `c.ts`'),
      ];
      expect(
        describeToolRun(tools),
        'Run 2 commands, edit 2 files, read a file',
      );
    });

    test('repeated edits to one file count as a single file', () {
      final tools = [
        sum('Using tool: **Edit** - `lib/main.dart`'),
        sum('Using tool: **Edit** - `lib/main.dart`'),
      ];
      expect(describeToolRun(tools), 'Edit a file');
    });

    test('a single shell command reads "Run a command"', () {
      expect(
        describeToolRun([sum('Using tool: **Bash** - `ls -la`')]),
        'Run a command',
      );
    });

    test('edits carrying an inline diff still count as grouped files', () {
      // Regression for the grouping inconsistency: an Edit whose message
      // includes a fenced diff must still summarize like a bare Edit, so a run
      // of them groups into one label instead of fragmenting.
      final tools = [
        sum('Using tool: **Edit** - `lib/a.dart`\n```diff\n- old\n+ new\n```'),
        sum('Using tool: **Edit** - `lib/b.dart`\n```diff\n- x\n+ y\n```'),
      ];
      expect(describeToolRun(tools), 'Edit 2 files');
      expect(tools.every((t) => t.hasDetail), isTrue);
    });

    test('falls back to "N tool uses" when nothing parses', () {
      final tools = [sum('Using tool: '), sum('Using tool: ')];
      expect(describeToolRun(tools), '2 tool uses');
    });
  });

  group('summarizeToolMessage', () {
    test('extracts the basename for a file tool', () {
      final s = sum('Using tool: **Edit** - `lib/pages/home.dart`');
      expect(s.name, 'Edit');
      expect(s.fileName, 'home.dart');
      expect(s.isFile, isTrue);
      expect(s.isShell, isFalse);
    });

    test('treats a shell command (with spaces) as non-file', () {
      final s = sum('Using tool: **Bash** - `ls -la`');
      expect(s.name, 'Bash');
      expect(s.isShell, isTrue);
      expect(s.fileName, isNull);
    });
  });
}
