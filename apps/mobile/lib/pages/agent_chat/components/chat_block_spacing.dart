// Vertical spacing between the bordered blocks of the agent chat transcript —
// a tool-use row, a collapsed tool-use run (`ToolUseGroup`), a sub-agent group
// (`SubagentGroup`), an AskUserQuestion prompt. Pure so the rules are
// unit-testable; `_buildMessage` in `agent_chat_widget.dart` is the sole caller.
//
// There are two gap sizes, not one:
//
//  - [kChatBlockGapBordered] between two bordered blocks sitting next to each
//    other (in either order — tool row, run, or sub-agent group).
//  - [kChatBlockGap] between a bordered block and plain content next to it
//    (agent/user text, or the start/end of the list).
//
// What differs beyond the size is WHO owns the gap:
//
//  - Ordinary blocks (tool rows/runs, AskUserQuestion prompts) own their gap
//    BELOW themselves; the block beneath, following a bordered block, adds
//    nothing. One gap between them, never two stacked.
//  - A sub-agent group owns its gap on BOTH sides itself, and its neighbours
//    yield. The group can't rely on its neighbours to provide it: it renders
//    once, at its anchor index, and draws every message sharing its
//    `tool_use_id`; the other indices render nothing but stay in the list. So
//    the block "directly above" the anchor can be one of those hidden
//    children, and keying the top gap off it (the ordinary rule) collapsed
//    the gap to nearly zero. Owning both sides makes the gap robust
//    regardless of what the hidden neighbour happens to be — it just has to
//    pick the right SIZE itself too, by checking whether its own neighbour is
//    bordered or plain content.
//
// Neighbour-awareness therefore has to be resolved against what is VISIBLE,
// not against `messages[i ± 1]`. `_followsBorderedBlock` /
// `_precedesSubagentGroup` / `_precedesBorderedBlock` in the chat widget do
// that walking, skipping every index that renders nothing at its position —
// a sub-agent group's hidden non-anchor members, and a collapsed tool-use
// run's hidden continuation rows alike. Get that walk wrong (stop on a hidden
// index instead of skipping it) and a block wrongly concludes it isn't
// adjacent to another bordered block, silently downgrading a wide gap to a
// narrow one.

import 'package:flutter/material.dart';

/// The gap between a bordered block and plain content (text, or the ends of
/// the list) next to it.
const double kChatBlockGap = 6.0;

/// The gap between two bordered blocks (tool row/run, sub-agent group)
/// sitting next to each other, in either order.
const double kChatBlockGapBordered = 12.0;

/// Slightly wider than [kChatBlockGapBordered], after a tool use with a fused
/// trailing code block — the code block reads as a heavier separator, so the
/// next group gets more air. Only ever follows another bordered block (a
/// trailing code block can only belong to a tool-use message), so it's
/// compared against the bordered gap, not the plain-content one.
const double kChatBlockGapAfterCodeBlock = 14.0;

/// Top margin for a bordered block, given what renders above it.
///
/// - [followsBorderedBlock]: the block above is a tool row/run/sub-agent group,
///   which already contributes the gap between them, so this block adds nothing.
/// - [startsNewToolGroup]: this block opens a new bordered box rather than
///   continuing the run above it (a continuing row must sit flush, at 0).
/// - [followsFusedCodeBlock]: the block above ends in a fused code block.
double chatBlockTopMargin({
  required bool followsBorderedBlock,
  required bool startsNewToolGroup,
  required bool followsFusedCodeBlock,
}) {
  if (followsFusedCodeBlock) return kChatBlockGapAfterCodeBlock;
  if (followsBorderedBlock) return 0.0;
  return startsNewToolGroup ? kChatBlockGap : 0.0;
}

/// Bottom margin for an ordinary block: zero when a sub-agent group comes
/// next — that group owns its own gap above itself, so the block above must
/// yield or the two would stack. Otherwise, the wide bordered gap when
/// another bordered block follows, the narrow plain-content gap otherwise.
double chatBlockBottomMargin({
  required bool endsToolGroup,
  required bool precedesSubagentGroup,
  required bool precedesBorderedBlock,
}) {
  if (precedesSubagentGroup) return 0.0;
  if (!endsToolGroup) return 0.0;
  return precedesBorderedBlock ? kChatBlockGapBordered : kChatBlockGap;
}

/// Margin for a collapsed tool-use run — always its own box, never a
/// continuation of the run above it.
EdgeInsetsDirectional chatBlockMargin({
  required bool followsBorderedBlock,
  required bool precedesSubagentGroup,
  required bool precedesBorderedBlock,
  double horizontal = 16.0,
}) =>
    EdgeInsetsDirectional.fromSTEB(
      horizontal,
      chatBlockTopMargin(
        followsBorderedBlock: followsBorderedBlock,
        startsNewToolGroup: true,
        followsFusedCodeBlock: false,
      ),
      horizontal,
      chatBlockBottomMargin(
        endsToolGroup: true,
        precedesSubagentGroup: precedesSubagentGroup,
        precedesBorderedBlock: precedesBorderedBlock,
      ),
    );

/// Margin for a sub-agent group: applied entirely here (both sides) so the
/// gap is robust regardless of the (possibly hidden) neighbour above — see
/// the file header. Each side independently picks the wide bordered gap or
/// the narrow plain-content gap based on what's actually next to it.
///
/// The bottom drops to 0 when another sub-agent group follows — that group
/// owns the same gap above itself, and two stacked would double it. Parallel
/// sub-agents put their anchors back to back, so this is a real case.
EdgeInsetsDirectional subagentBlockMargin({
  required bool followsBorderedBlock,
  required bool precedesSubagentGroup,
  required bool precedesBorderedBlock,
  double horizontal = 16.0,
}) =>
    EdgeInsetsDirectional.fromSTEB(
      horizontal,
      followsBorderedBlock ? kChatBlockGapBordered : kChatBlockGap,
      horizontal,
      precedesSubagentGroup
          ? 0.0
          : (precedesBorderedBlock ? kChatBlockGapBordered : kChatBlockGap),
    );
