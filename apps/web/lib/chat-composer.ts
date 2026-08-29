/** Pure rules for the chat composer's primary button.
 *
 * Lives outside `components/chat-input.tsx` so it can be unit-tested — the
 * vitest setup runs in the `node` environment and cannot render components.
 */

export interface StopButtonInput {
  /** An interrupt handler is wired (i.e. this session can be stopped at all). */
  canInterrupt: boolean;
  /** A turn is running right now. */
  agentActive: boolean;
  /** Composer holds something sendable — typed text or a finished upload. */
  hasComposerContent: boolean;
  /** Session is closed / input is switched off entirely. */
  disabled: boolean;
}

/** Should the primary button render as Stop rather than Send?
 *
 * The composer-empty condition is deliberate and load-bearing:
 *
 * * Vicoa lets the user queue follow-ups mid-turn (the queued-messages bar),
 *   so hijacking the button whenever the agent is busy would remove a feature.
 * * It also means a stale `ACTIVE` status can never lock the user out of
 *   sending — typing one character brings Send back.
 */
export function shouldShowStopButton({
  canInterrupt,
  agentActive,
  hasComposerContent,
  disabled,
}: StopButtonInput): boolean {
  return canInterrupt && agentActive && !hasComposerContent && !disabled;
}
