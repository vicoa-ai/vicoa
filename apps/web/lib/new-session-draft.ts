// Draft cache for the new-session prompt, so an unsent message survives
// navigating away and reopening the page. One global draft (not keyed by
// machine/directory); cleared on successful submit. Mirrors the localStorage
// guards in lib/agent-catalog.ts.

const DRAFT_KEY = 'vicoa:new-session-prompt-draft';

export function loadPromptDraft(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem(DRAFT_KEY) ?? '';
  } catch {
    return '';
  }
}

export function savePromptDraft(text: string): void {
  if (typeof window === 'undefined') return;
  try {
    if (text) window.localStorage.setItem(DRAFT_KEY, text);
    else window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore quota errors */
  }
}

export function clearPromptDraft(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore */
  }
}
