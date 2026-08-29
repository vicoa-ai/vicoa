import type { SlashCommand } from '@/lib/constants/slash-commands';

/**
 * The text a chosen command inserts. Usually the command itself, but Codex
 * skills invoke with `$name`, so the entry's `insert` overrides when present.
 */
export function commandInsertText(command: SlashCommand): string {
  return command.insert ?? command.command;
}

/** Start of the word the caret sits in: just past the nearest preceding
 * whitespace, or 0 at the start of the input. Shared by detection + insertion so
 * both agree on where the "/command" word begins. */
function wordStartBefore(value: string, caret: number): number {
  const before = value.slice(0, Math.max(0, Math.min(caret, value.length)));
  const ws = Math.max(
    before.lastIndexOf(' '),
    before.lastIndexOf('\n'),
    before.lastIndexOf('\t'),
  );
  return ws + 1;
}

/**
 * Decide whether the "/"-command menu should be open for the current input and,
 * if so, what to filter by. Caret-aware and token-scoped so it behaves the same
 * whether the composer is empty or already holds a draft:
 *
 *  - the menu opens when the caret sits inside a "command word" — a run that
 *    starts with "/" at the very start of the input or right after whitespace;
 *  - `query` is that word's text after the "/", up to the next whitespace, so
 *    typing an argument (a space then more text) closes the menu, and a "/" in
 *    the middle of a word (e.g. a path like `src/app`) never opens it.
 *
 * Mirrors the mobile `filterSlashCommands`/`insertSlashCommand` pair and the
 * `@`-mention detection in `MentionTextarea`, which are caret + token based
 * rather than "does the whole string start with '/'".
 *
 *   ("", 0)             -> { active: false }
 *   ("/", 1)            -> { active: true,  query: '' }
 *   ("/rev", 4)         -> { active: true,  query: 'rev' }
 *   ("/review fix", 4)  -> { active: true,  query: 'rev' }   (caret inside the word)
 *   ("/review fix", 11) -> { active: false }                 (caret out in the arg)
 *   ("fix /rev", 8)     -> { active: true,  query: 'rev' }   (word-start "/")
 *   ("src/app", 7)      -> { active: false }                 (mid-word "/")
 */
export function detectSlashCommand(
  value: string,
  caret: number,
): { active: boolean; query: string } {
  const pos = Math.max(0, Math.min(caret, value.length));
  const wordStart = wordStartBefore(value, pos);
  if (value[wordStart] !== '/') return { active: false, query: '' };
  const afterSlash = value.slice(wordStart + 1);
  const wsAfter = afterSlash.search(/\s/);
  const query = wsAfter === -1 ? afterSlash : afterSlash.slice(0, wsAfter);
  // Only while the caret is still within the "/word" (not out in an argument).
  if (pos > wordStart + 1 + query.length) return { active: false, query: '' };
  return { active: true, query };
}

/** Case-insensitive match of the command name (sans leading "/") against a
 * `detectSlashCommand` query. Kept here so every surface filters identically. */
export function slashCommandMatches(command: SlashCommand, query: string): boolean {
  return command.command.toLowerCase().slice(1).startsWith(query.toLowerCase());
}

/**
 * Compute the new input value + caret position when a slash command is chosen
 * from the suggestion list.
 *
 * Replaces the "command word" the caret is in (the "/…" run `detectSlashCommand`
 * matched) with [command], preserves the surrounding draft, and parks the caret
 * just past the inserted command so the user can type an argument. Caret-aware
 * so it works mid-draft, mirroring the mobile `insertSlashCommand`. `command` is
 * the insert text (see `commandInsertText`), which may be `$name` for a Codex
 * skill.
 *
 *   ("/com", "/compact", 4)         -> "/compact "            (caret at end)
 *   ("/ fix the bug", "/review", 1) -> "/review fix the bug"  (caret after "/review")
 *   ("fix /rev now", "/review", 8)  -> "fix /review now"      (word replaced in place)
 */
export function applySlashCommandSelection(
  value: string,
  command: string,
  caret: number,
): { value: string; cursor: number } {
  const pos = Math.max(0, Math.min(caret, value.length));
  const wordStart = wordStartBefore(value, pos);
  // End of the command word: extend from the caret to the next whitespace.
  let wordEnd = pos;
  while (wordEnd < value.length && !/\s/.test(value[wordEnd])) wordEnd++;
  const head = value.slice(0, wordStart);
  const tail = value.slice(wordEnd);
  const needsSpace = tail === '' || !/^\s/.test(tail);
  const separator = needsSpace ? ' ' : '';
  const next = `${head}${command}${separator}${tail}`;
  const cursor = head.length + command.length + separator.length;
  return { value: next, cursor };
}
