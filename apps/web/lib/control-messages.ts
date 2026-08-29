/** Parsing for the control tokens the dashboard appends to user messages.
 *
 * A control message is a human-readable sentence followed by a JSON token,
 * e.g. `Stop current task. {"type":"control","setting":"interrupt"}`. The
 * sentence is what the transcript renders; the token is what the agent
 * wrapper acts on.
 */

export const CONTROL_COMMAND_JSON_REGEX = /\{\s*"type"\s*:\s*"control"[^}]*\}/gi;

/** True only when `content` *is* a control directive, not prose that merely
 * quotes or pastes one.
 *
 * Every control message the dashboards emit is `<label> {json}` or
 * `<summary>\n{json}` — the control token is always the *trailing* content. So
 * from the first control token to the end of the string there must be nothing
 * but control tokens and whitespace.
 *
 * A normal user message that pastes/quotes control JSON (e.g. describing the
 * `session get` output) has free text after the token and fails this check, so
 * it is treated as ordinary input: shown in the transcript, kept in the queued
 * bar, and (backend-side) actually delivered to the agent instead of being
 * silently swallowed. `.search` ignores the regex's `g` flag and never touches
 * its `lastIndex`, so this stays stateless. */
export function isControlEnvelope(content: string): boolean {
  if (!content) return false;
  const idx = content.search(CONTROL_COMMAND_JSON_REGEX);
  if (idx < 0) return false;
  const residue = content.slice(idx).replace(CONTROL_COMMAND_JSON_REGEX, '');
  return residue.trim() === '';
}

export function parseControlCommand(value: string): { setting?: string; value?: string } | null {
  try {
    const parsed = JSON.parse(value);
    if (parsed?.type === 'control') {
      return parsed;
    }
  } catch {
    // Ignore malformed JSON snippets
  }
  return null;
}

/** True when the content carries a `setting: "interrupt"` control token.
 *
 * Interrupt is the one control that carries no `value`, so the generic
 * `extractControlSettingValue` (which requires a string value) can't answer
 * this. Used to keep a Stop visible in the transcript even though the server
 * stamps it `queued` for arriving mid-turn.
 */
export function isInterruptControlMessage(content: string): boolean {
  if (!isControlEnvelope(content)) return false;
  const matches = (content || '').match(CONTROL_COMMAND_JSON_REGEX) || [];
  return matches.some((match) => parseControlCommand(match)?.setting === 'interrupt');
}
