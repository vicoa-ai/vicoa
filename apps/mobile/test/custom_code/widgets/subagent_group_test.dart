// Spec for the sub-agent (Task tool) message grouping logic
// (`lib/custom_code/widgets/subagent_group.dart`). Covers the metadata
// readers and, crucially, `computeSubagentGrouping`'s ANCHOR-AT-FIRST-
// OCCURRENCE bucketing by `tool_use_id` — deliberately different from
// `tool_use_group.dart`'s consecutive-run grouping because parallel
// sub-agents can interleave their child messages in chat order.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/widgets/subagent_group.dart';

Map<String, dynamic> _subagentMsg(
  String toolUseId, {
  String type = 'Explore',
  String? description,
}) =>
    {
      'sender_type': 'AGENT',
      'content': 'child of $toolUseId',
      'message_metadata': {
        'subagent': {
          'tool_use_id': toolUseId,
          'subagent_type': type,
          'description': description ?? '',
          'role': 'step',
        },
      },
    };

Map<String, dynamic> _plainMsg(String content) => {
      'sender_type': 'AGENT',
      'content': content,
    };

void main() {
  group('subagentToolUseIdOf', () {
    test('reads tool_use_id from message_metadata.subagent', () {
      expect(subagentToolUseIdOf(_subagentMsg('tu-1')), 'tu-1');
    });

    test('returns null for non-Map / missing / malformed metadata', () {
      expect(subagentToolUseIdOf('not a map'), isNull);
      expect(subagentToolUseIdOf(_plainMsg('hi')), isNull);
      expect(subagentToolUseIdOf({'message_metadata': 'not a map'}), isNull);
      expect(
        subagentToolUseIdOf({
          'message_metadata': {'subagent': 'not a map'}
        }),
        isNull,
      );
      expect(
        subagentToolUseIdOf({
          'message_metadata': {
            'subagent': {'tool_use_id': ''}
          }
        }),
        isNull,
      );
      expect(
        subagentToolUseIdOf({
          'message_metadata': {
            'subagent': {'tool_use_id': null}
          }
        }),
        isNull,
      );
    });
  });

  group('subagentTypeOf / subagentDescriptionOf', () {
    test('reads the type, defaulting to "agent" when absent/blank', () {
      expect(
        subagentTypeOf(_subagentMsg('tu-1', type: 'general-purpose')),
        'general-purpose',
      );
      expect(subagentTypeOf(_plainMsg('hi')), 'agent');
      expect(subagentTypeOf(_subagentMsg('tu-1', type: '  ')), 'agent');
    });

    test('reads the description, or null when absent/blank', () {
      expect(
        subagentDescriptionOf(_subagentMsg('tu-1', description: 'Find the bug')),
        'Find the bug',
      );
      expect(subagentDescriptionOf(_subagentMsg('tu-1')), isNull);
      expect(subagentDescriptionOf(_plainMsg('hi')), isNull);
    });
  });

  group('computeSubagentGrouping', () {
    test('(a) a single sub-agent collects all its messages at the first index', () {
      final messages = [
        _plainMsg('user says hi'),
        _subagentMsg('tu-1'),
        _subagentMsg('tu-1'),
        _subagentMsg('tu-1'),
        _plainMsg('agent wraps up'),
      ];
      final g = computeSubagentGrouping(messages);

      expect(g.isSubagentMessage(0), isFalse);
      expect(g.isSubagentMessage(1), isTrue);
      expect(g.isSubagentMessage(2), isTrue);
      expect(g.isSubagentMessage(3), isTrue);
      expect(g.isSubagentMessage(4), isFalse);

      // Only the first occurrence is the anchor.
      expect(g.isRunStart(1), isTrue);
      expect(g.isRunStart(2), isFalse);
      expect(g.isRunStart(3), isFalse);

      // Every member (anchor or not) resolves to the same full index list.
      expect(g.runIndices(1), [1, 2, 3]);
      expect(g.runIndices(2), [1, 2, 3]);
      expect(g.runIndices(3), [1, 2, 3]);
    });

    test(
        '(b) two PARALLEL interleaved sub-agents (A,B,A,B) each collect only '
        'their own indices, anchored at their own first occurrence', () {
      final messages = [
        _subagentMsg('A'), // 0: A's anchor
        _subagentMsg('B'), // 1: B's anchor
        _subagentMsg('A'), // 2
        _subagentMsg('B'), // 3
      ];
      final g = computeSubagentGrouping(messages);

      expect(g.isRunStart(0), isTrue); // A's first occurrence
      expect(g.isRunStart(1), isTrue); // B's first occurrence
      expect(g.isRunStart(2), isFalse); // A's second occurrence
      expect(g.isRunStart(3), isFalse); // B's second occurrence

      // A's indices are collected wherever they fall, skipping B's.
      expect(g.runIndices(0), [0, 2]);
      expect(g.runIndices(2), [0, 2]);
      // B's indices, likewise, skip A's.
      expect(g.runIndices(1), [1, 3]);
      expect(g.runIndices(3), [1, 3]);
    });

    test('(c) non-subagent messages are never collected into a group', () {
      final messages = [
        _plainMsg('hello'),
        _subagentMsg('tu-1'),
        _plainMsg('world'),
      ];
      final g = computeSubagentGrouping(messages);

      expect(g.isSubagentMessage(0), isFalse);
      expect(g.isSubagentMessage(2), isFalse);
      expect(g.isRunStart(0), isFalse);
      expect(g.isRunStart(2), isFalse);
      expect(g.runIndices(0), isEmpty);
      expect(g.runIndices(2), isEmpty);

      // The sole sub-agent message still groups correctly on its own.
      expect(g.isRunStart(1), isTrue);
      expect(g.runIndices(1), [1]);
    });

    test('out-of-range indices are handled safely', () {
      final g = computeSubagentGrouping([_subagentMsg('tu-1')]);
      expect(g.isSubagentMessage(-1), isFalse);
      expect(g.isSubagentMessage(5), isFalse);
      expect(g.isRunStart(-1), isFalse);
      expect(g.isRunStart(5), isFalse);
      expect(g.runIndices(5), isEmpty);
    });

    test(
        'an anchor whose OWN content is empty is still bucketed and stays '
        'the run start — grouping keys off message_metadata.subagent, never '
        'off `content`, so an anchor with a blank/stderr-only body (see the '
        'empty-anchor render fix in agent_chat_widget.dart) does not fall '
        'out of its group', () {
      final messages = [
        {..._subagentMsg('tu-1'), 'content': ''}, // 0: empty-content anchor
        _subagentMsg('tu-1'), // 1: real-content member
      ];
      final g = computeSubagentGrouping(messages);

      expect(g.isSubagentMessage(0), isTrue);
      expect(g.isRunStart(0), isTrue);
      expect(g.isRunStart(1), isFalse);
      expect(g.runIndices(0), [0, 1]);
      expect(g.runIndices(1), [0, 1]);
    });
  });

  group('visibleSubagentGroupContents', () {
    test('drops entries that sanitize down to empty/whitespace-only', () {
      expect(
        visibleSubagentGroupContents(['first', '', 'second', '   ', '\n']),
        ['first', 'second'],
      );
    });

    test('keeps everything when nothing sanitizes to empty', () {
      expect(
        visibleSubagentGroupContents(['a', 'b', 'c']),
        ['a', 'b', 'c'],
      );
    });

    test('returns empty when every entry sanitizes to empty', () {
      expect(visibleSubagentGroupContents(['', '  ', '\n\n']), isEmpty);
    });

    test('applies filterProjectRoot before checking emptiness', () {
      // A content string that becomes empty only after project-root
      // filtering should still be dropped.
      expect(
        visibleSubagentGroupContents(
          ['/Users/me/project/file.txt'],
          filterProjectRoot: (c) => c.replaceAll('/Users/me/project/file.txt', ''),
        ),
        isEmpty,
      );
    });

    test('applies codex **Status:** stripping for codex agents, matching '
        'sanitizeToolContent, and still drops the result if it becomes '
        'empty', () {
      expect(
        visibleSubagentGroupContents(
          ['**Status:** done'],
          agentTypeName: 'codex',
        ),
        isEmpty,
      );
    });
  });
}
