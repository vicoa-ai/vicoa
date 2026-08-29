import { describe, expect, it } from 'vitest';
import { shouldShowStopButton, type StopButtonInput } from './chat-composer';

function input(overrides: Partial<StopButtonInput> = {}): StopButtonInput {
  return {
    canInterrupt: true,
    agentActive: true,
    hasComposerContent: false,
    disabled: false,
    ...overrides,
  };
}

describe('shouldShowStopButton', () => {
  it('shows Stop while a turn runs and the composer is empty', () => {
    expect(shouldShowStopButton(input())).toBe(true);
  });

  it('shows Send when the agent is idle', () => {
    expect(shouldShowStopButton(input({ agentActive: false }))).toBe(false);
  });

  it('falls back to Send as soon as the user types, so mid-turn queueing still works', () => {
    expect(shouldShowStopButton(input({ hasComposerContent: true }))).toBe(false);
  });

  it('never shows Stop when the session cannot be interrupted', () => {
    expect(shouldShowStopButton(input({ canInterrupt: false }))).toBe(false);
  });

  it('never shows Stop on a closed session', () => {
    expect(shouldShowStopButton(input({ disabled: true }))).toBe(false);
  });

  it('cannot lock the user out of sending on a stale ACTIVE status', () => {
    // The escape hatch: even if `agentActive` is wrong, one keystroke of
    // content restores the Send affordance.
    const stale = input({ agentActive: true });
    expect(shouldShowStopButton(stale)).toBe(true);
    expect(shouldShowStopButton({ ...stale, hasComposerContent: true })).toBe(false);
  });
});
