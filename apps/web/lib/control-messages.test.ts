import { describe, expect, it } from 'vitest';
import {
  buildAskUserQuestionCancelPersistMessage,
  buildAskUserQuestionControlMessage,
  buildAskUserQuestionSummaryMessage,
  type AskUserQuestionSubmitPayload,
} from '@/components/dashboard/ask-user-question-panel';
import {
  isActionRecord,
  isControlEnvelope,
  isInterruptControlMessage,
  isPersistOnlyMessage,
  parseControlCommand,
} from './control-messages';

const INTERRUPT = 'Stop current task. {"type":"control","setting":"interrupt"}';

// A real user message (session 49ed4485) that discussed the `session get`
// output and PASTED control tokens into the middle of its body. It must be
// treated as ordinary prose — not a control directive — or it gets swallowed
// (backend) / hidden (chat).
const PROSE_QUOTING_CONTROL =
  'Commit the changes.\n' +
  '  {"type":"control","action":"persist_only","value":"v1:eyJhIjoxfQ"}\n\n' +
  '  Submit answers. {"type":"control","setting":"ask_user_question","value":"submit:eyJhIjoxfQ"}\n\n' +
  'By default no.';

describe('isControlEnvelope', () => {
  it('is true when the control token trails the message', () => {
    expect(isControlEnvelope(INTERRUPT)).toBe(true);
    expect(isControlEnvelope('Q: color\nA: red\n{"type":"control","action":"persist_only","value":"v1:x"}')).toBe(true);
    // Multiple contiguous trailing tokens.
    expect(isControlEnvelope('Stop. {"type":"control","setting":"model","value":"x"} {"type":"control","setting":"interrupt"}')).toBe(true);
  });

  it('is false when the message merely quotes control JSON amid prose', () => {
    expect(isControlEnvelope(PROSE_QUOTING_CONTROL)).toBe(false);
    expect(isControlEnvelope('hello {"type":"control","setting":"thinking","value":"on"} bye')).toBe(false);
  });

  it('is false when there is no control token', () => {
    expect(isControlEnvelope('just chatting')).toBe(false);
    expect(isControlEnvelope('')).toBe(false);
  });
});

describe('isInterruptControlMessage', () => {
  it('matches the interrupt token the Stop button sends', () => {
    expect(isInterruptControlMessage(INTERRUPT)).toBe(true);
  });

  it('does not match other controls', () => {
    expect(
      isInterruptControlMessage('Switch to plan mode. {"type":"control","setting":"permission_mode","value":"plan"}')
    ).toBe(false);
    expect(
      isInterruptControlMessage('Use gpt-5.5. {"type":"control","setting":"model","value":"gpt-5.5"}')
    ).toBe(false);
  });

  it('does not match a plain message that merely mentions stopping', () => {
    expect(isInterruptControlMessage('please interrupt the task')).toBe(false);
    expect(isInterruptControlMessage('')).toBe(false);
  });

  it('tolerates whitespace and repeated scans (the regex is module-level /g)', () => {
    const spaced = 'Stop current task. { "type" : "control" , "setting" : "interrupt" }';
    expect(isInterruptControlMessage(spaced)).toBe(true);
    // Re-scanning the same string must not be affected by regex lastIndex.
    expect(isInterruptControlMessage(spaced)).toBe(true);
    expect(isInterruptControlMessage(INTERRUPT)).toBe(true);
  });

  it('finds the token alongside another control in one message', () => {
    const both = 'Stop. {"type":"control","setting":"model","value":"x"} {"type":"control","setting":"interrupt"}';
    expect(isInterruptControlMessage(both)).toBe(true);
  });

  it('does not match an interrupt token quoted in the middle of prose', () => {
    expect(
      isInterruptControlMessage('here is the token {"type":"control","setting":"interrupt"} and more text')
    ).toBe(false);
    expect(isInterruptControlMessage(PROSE_QUOTING_CONTROL)).toBe(false);
  });
});

// Built the way the dashboard's question panel builds them.
const ANSWER: AskUserQuestionSubmitPayload = {
  message_id: 'prompt-message-id',
  answers: [{ mode: 'option', option_index: 0, option_count: 2 }],
  display_answers: [{ question: 'Pick a color', header: 'Color', label: 'Red' }],
};
const SUMMARY = buildAskUserQuestionSummaryMessage(ANSWER);
const DECLINED = buildAskUserQuestionCancelPersistMessage();

describe('isPersistOnlyMessage', () => {
  it('matches the answer summary and the decline note', () => {
    expect(SUMMARY.startsWith('Q: Pick a color\nA: Red\n')).toBe(true);
    expect(isPersistOnlyMessage(SUMMARY)).toBe(true);
    expect(isPersistOnlyMessage(DECLINED)).toBe(true);
  });

  it('does not match the answer directive or other controls', () => {
    expect(isPersistOnlyMessage(buildAskUserQuestionControlMessage('submit', ANSWER))).toBe(false);
    expect(isPersistOnlyMessage(INTERRUPT)).toBe(false);
    expect(isPersistOnlyMessage('just chatting')).toBe(false);
    expect(isPersistOnlyMessage('')).toBe(false);
  });

  it('does not match a persist_only token quoted in the middle of prose', () => {
    expect(isPersistOnlyMessage(PROSE_QUOTING_CONTROL)).toBe(false);
    expect(
      isPersistOnlyMessage('what does {"type":"control","action":"persist_only"} mean here?')
    ).toBe(false);
  });
});

describe('isActionRecord', () => {
  it('covers a Stop, an answer and a decline', () => {
    expect(isActionRecord(INTERRUPT)).toBe(true);
    expect(isActionRecord(SUMMARY)).toBe(true);
    expect(isActionRecord(DECLINED)).toBe(true);
  });

  it('leaves ordinary messages and other controls out', () => {
    expect(isActionRecord('keep going')).toBe(false);
    expect(isActionRecord('Use gpt-5.5. {"type":"control","setting":"model","value":"gpt-5.5"}')).toBe(false);
    expect(isActionRecord(buildAskUserQuestionControlMessage('submit', ANSWER))).toBe(false);
    expect(isActionRecord(PROSE_QUOTING_CONTROL)).toBe(false);
  });
});

describe('parseControlCommand', () => {
  it('returns null for non-control JSON and garbage', () => {
    expect(parseControlCommand('{"type":"other"}')).toBeNull();
    expect(parseControlCommand('not json')).toBeNull();
  });

  it('parses a valueless control', () => {
    expect(parseControlCommand('{"type":"control","setting":"interrupt"}')).toEqual({
      type: 'control',
      setting: 'interrupt',
    });
  });
});
