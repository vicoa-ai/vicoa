import type { KeyboardEvent } from 'react';

/**
 * Whether this keydown belongs to an IME (Chinese Pinyin, Japanese, Korean…)
 * rather than to the field. While a candidate window is open, Enter commits
 * the candidate and Escape cancels it; a handler that reads either as "submit"
 * or "close" fires mid-word. Check this first and return.
 *
 * keyCode 229 is the legacy signal for Safari, which reports the committing
 * keydown with `isComposing` already false.
 */
export function isImeComposing(e: KeyboardEvent): boolean {
  return e.nativeEvent.isComposing || e.keyCode === 229;
}
