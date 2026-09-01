/**
 * Draft model for editing a repo's worktree setup/teardown config in a form,
 * ported from Paseo's `project-config-form.ts` (trimmed to the worktree hooks —
 * we have no scripts/metadata). The config file (`.vicoa/config.json` or root
 * `vicoa.json`) wraps the hooks under a `"worktree"` key; each hook is a single
 * command string OR an array of them.
 *
 * The draft is text (one command per line) plus the hook's ORIGINAL kind, so a
 * round-trip preserves whether the author wrote a string or an array and never
 * clobbers unrelated keys in the file (`applyDraftToConfig` merges into a base).
 */

export type LifecycleKind = 'string' | 'array' | 'missing';

export interface WorktreeConfigDraft {
  setupText: string;
  setupKind: LifecycleKind;
  teardownText: string;
  teardownKind: LifecycleKind;
}

interface LifecycleProjection {
  text: string;
  kind: LifecycleKind;
}

function projectLifecycle(value: unknown): LifecycleProjection {
  if (typeof value === 'string') {
    return { text: value, kind: 'string' };
  }
  if (Array.isArray(value)) {
    const lines = value.filter((entry): entry is string => typeof entry === 'string');
    return { text: lines.join('\n'), kind: 'array' };
  }
  return { text: '', kind: 'missing' };
}

function lifecycleFromText(text: string, kind: LifecycleKind): string | string[] | undefined {
  const lines = text.split('\n').filter((line) => line.trim().length > 0);
  if (lines.length === 0) return undefined;
  if (kind === 'string') return lines.join('\n');
  if (kind === 'array') return lines;
  // 'missing' — pick the tidiest shape for a freshly-authored hook.
  return lines.length === 1 ? lines[0] : lines;
}

/** Read the `{worktree:{setup,teardown}}` shape out of a parsed config object. */
export function configToDraft(config: unknown): WorktreeConfigDraft {
  const worktree =
    config && typeof config === 'object' && 'worktree' in config
      ? (config as { worktree?: unknown }).worktree
      : undefined;
  const wt = worktree && typeof worktree === 'object' ? (worktree as Record<string, unknown>) : {};
  const setup = projectLifecycle(wt.setup);
  const teardown = projectLifecycle(wt.teardown);
  return {
    setupText: setup.text,
    setupKind: setup.kind,
    teardownText: teardown.text,
    teardownKind: teardown.kind,
  };
}

/**
 * Merge the draft back into `base` (the parsed file, or null/undefined for a new
 * one), touching ONLY `worktree.setup`/`worktree.teardown` — every other key in
 * the file is preserved. An empty hook is deleted; an empty `worktree` object is
 * dropped too.
 */
export function applyDraftToConfig(draft: WorktreeConfigDraft, base: unknown): Record<string, unknown> {
  const baseObj = base && typeof base === 'object' ? (base as Record<string, unknown>) : {};
  const baseWorktree =
    baseObj.worktree && typeof baseObj.worktree === 'object'
      ? (baseObj.worktree as Record<string, unknown>)
      : {};

  const nextWorktree: Record<string, unknown> = { ...baseWorktree };
  const nextSetup = lifecycleFromText(draft.setupText, draft.setupKind);
  if (nextSetup === undefined) delete nextWorktree.setup;
  else nextWorktree.setup = nextSetup;
  const nextTeardown = lifecycleFromText(draft.teardownText, draft.teardownKind);
  if (nextTeardown === undefined) delete nextWorktree.teardown;
  else nextWorktree.teardown = nextTeardown;

  const result: Record<string, unknown> = { ...baseObj };
  if (Object.keys(nextWorktree).length === 0) delete result.worktree;
  else result.worktree = nextWorktree;
  return result;
}

/** True when the draft carries no setup and no teardown commands. */
export function isDraftEmpty(draft: WorktreeConfigDraft): boolean {
  return (
    draft.setupText.split('\n').every((l) => l.trim().length === 0) &&
    draft.teardownText.split('\n').every((l) => l.trim().length === 0)
  );
}
