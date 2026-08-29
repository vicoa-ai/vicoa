import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/agent_chat/components/chat_block_spacing.dart';

/// Total gap between two stacked blocks: what the upper one puts below itself
/// plus what the lower one puts above itself.
double gapBetween(EdgeInsetsDirectional above, EdgeInsetsDirectional below) =>
    above.bottom + below.top;

/// An ordinary agent text block: no margins of its own, top or bottom.
const plainText = EdgeInsetsDirectional.zero;

/// A user message block, which keeps its own wider turn spacing.
const userMessage = EdgeInsetsDirectional.fromSTEB(48.0, 16.0, 16.0, 16.0);

/// A tool use / AskUserQuestion prompt rendered as a standalone bordered box:
/// its top/bottom come from the ordinary tool-use path in `_buildMessage`.
EdgeInsetsDirectional standaloneToolMargin({
  required bool followsBorderedBlock,
  bool precedesSubagentGroup = false,
  bool precedesBorderedBlock = false,
}) =>
    EdgeInsetsDirectional.fromSTEB(
      16.0,
      chatBlockTopMargin(
        followsBorderedBlock: followsBorderedBlock,
        startsNewToolGroup: true,
        followsFusedCodeBlock: false,
      ),
      16.0,
      chatBlockBottomMargin(
        endsToolGroup: true,
        precedesSubagentGroup: precedesSubagentGroup,
        precedesBorderedBlock: precedesBorderedBlock,
      ),
    );

void main() {
  group('chatBlockTopMargin', () {
    test('a block below another bordered block adds no gap of its own', () {
      expect(
        chatBlockTopMargin(
          followsBorderedBlock: true,
          startsNewToolGroup: true,
          followsFusedCodeBlock: false,
        ),
        0.0,
      );
    });

    test('a new group after non-bordered content opens the narrow gap itself',
        () {
      expect(
        chatBlockTopMargin(
          followsBorderedBlock: false,
          startsNewToolGroup: true,
          followsFusedCodeBlock: false,
        ),
        kChatBlockGap,
      );
    });

    test('a row continuing the run above sits flush', () {
      expect(
        chatBlockTopMargin(
          followsBorderedBlock: false,
          startsNewToolGroup: false,
          followsFusedCodeBlock: false,
        ),
        0.0,
      );
    });

    test('a fused code block above wins over every other case', () {
      for (final follows in [true, false]) {
        for (final starts in [true, false]) {
          expect(
            chatBlockTopMargin(
              followsBorderedBlock: follows,
              startsNewToolGroup: starts,
              followsFusedCodeBlock: true,
            ),
            kChatBlockGapAfterCodeBlock,
          );
        }
      }
    });
  });

  group('chatBlockBottomMargin', () {
    test('a block that ends its group, followed by plain content, owns the narrow gap',
        () {
      expect(
        chatBlockBottomMargin(
          endsToolGroup: true,
          precedesSubagentGroup: false,
          precedesBorderedBlock: false,
        ),
        kChatBlockGap,
      );
    });

    test('a block that ends its group, followed by another bordered block, owns the wide gap',
        () {
      expect(
        chatBlockBottomMargin(
          endsToolGroup: true,
          precedesSubagentGroup: false,
          precedesBorderedBlock: true,
        ),
        kChatBlockGapBordered,
      );
    });

    test('a row mid-run sits flush against the next row, regardless of what follows',
        () {
      for (final precedesBordered in [true, false]) {
        expect(
          chatBlockBottomMargin(
            endsToolGroup: false,
            precedesSubagentGroup: false,
            precedesBorderedBlock: precedesBordered,
          ),
          0.0,
        );
      }
    });

    test('yields to a sub-agent group, which owns its own gap above, regardless of width',
        () {
      for (final precedesBordered in [true, false]) {
        expect(
          chatBlockBottomMargin(
            endsToolGroup: true,
            precedesSubagentGroup: true,
            precedesBorderedBlock: precedesBordered,
          ),
          0.0,
        );
      }
    });
  });

  group('ordinary blocks keep one gap between them', () {
    test('two collapsed runs separated by a non-collapsible row share the wide gap',
        () {
      final above = chatBlockMargin(
        followsBorderedBlock: false,
        precedesSubagentGroup: false,
        precedesBorderedBlock: true,
      );
      final below = chatBlockMargin(
        followsBorderedBlock: true,
        precedesSubagentGroup: false,
        precedesBorderedBlock: false,
      );
      expect(gapBetween(above, below), kChatBlockGapBordered);
    });

    test('a run after plain text opens the narrow gap itself', () {
      final run = chatBlockMargin(
        followsBorderedBlock: false,
        precedesSubagentGroup: false,
        precedesBorderedBlock: false,
      );
      expect(gapBetween(plainText, run), kChatBlockGap);
      expect(gapBetween(run, plainText), kChatBlockGap);
    });

    test('keeps the 16px horizontal inset of the transcript', () {
      final run = chatBlockMargin(
        followsBorderedBlock: true,
        precedesSubagentGroup: false,
        precedesBorderedBlock: false,
      );
      expect(run.start, 16.0);
      expect(run.end, 16.0);
      expect(
        subagentBlockMargin(
          followsBorderedBlock: true,
          precedesSubagentGroup: false,
          precedesBorderedBlock: false,
        ).start,
        16.0,
      );
    });
  });

  group('bordered blocks are spaced by the same wide gap regardless of order',
      () {
    // The exact request: A-C, C-A, B-C — whichever bordered block meets
    // whichever other bordered block, the gap is identical and wide. Against
    // plain content, every bordered block instead gets the narrower gap.

    test('a sub-agent group sits one wide gap below a tool use, robustly', () {
      // The tool above yields (precedesSubagentGroup); the group owns the gap
      // and picks the wide width itself via followsBorderedBlock.
      final toolAbove = standaloneToolMargin(
        followsBorderedBlock: false,
        precedesSubagentGroup: true,
      );
      final group = subagentBlockMargin(
        followsBorderedBlock: true,
        precedesSubagentGroup: false,
        precedesBorderedBlock: false,
      );
      expect(gapBetween(toolAbove, group), kChatBlockGapBordered);
    });

    test('a tool use sits one wide gap below a sub-agent group', () {
      final group = subagentBlockMargin(
        followsBorderedBlock: false,
        precedesSubagentGroup: false,
        precedesBorderedBlock: true,
      );
      final toolBelow = standaloneToolMargin(followsBorderedBlock: true);
      expect(gapBetween(group, toolBelow), kChatBlockGapBordered);
    });

    test('an AskUserQuestion sits one wide gap below a tool use', () {
      // AUQ is not a sub-agent group, so the tool above does NOT yield: it
      // owns the gap below (wide, since AUQ is bordered) and AUQ, following a
      // bordered block, adds no top.
      final toolAbove = standaloneToolMargin(
        followsBorderedBlock: false,
        precedesBorderedBlock: true,
      );
      final ask = standaloneToolMargin(followsBorderedBlock: true);
      expect(gapBetween(toolAbove, ask), kChatBlockGapBordered);
    });

    test('tool -> sub-agent equals tool -> AskUserQuestion equals tool -> tool',
        () {
      final toolBeforeGroup = standaloneToolMargin(
        followsBorderedBlock: false,
        precedesSubagentGroup: true,
      );
      final group = subagentBlockMargin(
        followsBorderedBlock: true,
        precedesSubagentGroup: false,
        precedesBorderedBlock: false,
      );

      final toolBeforeAsk = standaloneToolMargin(
        followsBorderedBlock: false,
        precedesBorderedBlock: true,
      );
      final ask = standaloneToolMargin(followsBorderedBlock: true);

      final toolBeforeTool = standaloneToolMargin(
        followsBorderedBlock: false,
        precedesBorderedBlock: true,
      );
      final tool = standaloneToolMargin(followsBorderedBlock: true);

      final gapToGroup = gapBetween(toolBeforeGroup, group);
      final gapToAsk = gapBetween(toolBeforeAsk, ask);
      final gapToTool = gapBetween(toolBeforeTool, tool);

      expect(gapToGroup, kChatBlockGapBordered);
      expect(gapToAsk, kChatBlockGapBordered);
      expect(gapToTool, kChatBlockGapBordered);
    });

    test('a sub-agent group gets the narrow gap above and below plain text',
        () {
      final group = subagentBlockMargin(
        followsBorderedBlock: false,
        precedesSubagentGroup: false,
        precedesBorderedBlock: false,
      );
      expect(gapBetween(plainText, group), kChatBlockGap);
      expect(gapBetween(group, plainText), kChatBlockGap);
    });

    test('back-to-back sub-agent groups keep a single wide gap, never doubled',
        () {
      // Parallel sub-agents put their anchors back to back: the first yields
      // its bottom, the second owns the gap above itself — wide, since its
      // neighbour is itself bordered.
      final first = subagentBlockMargin(
        followsBorderedBlock: false,
        precedesSubagentGroup: true,
        precedesBorderedBlock: false,
      );
      final second = subagentBlockMargin(
        followsBorderedBlock: true,
        precedesSubagentGroup: false,
        precedesBorderedBlock: false,
      );
      expect(gapBetween(first, second), kChatBlockGapBordered);
    });
  });
}
