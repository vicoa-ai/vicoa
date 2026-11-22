/**
 * Pure helpers behind the session summary card (the panel the header's
 * summary toggle opens: project, folder, branch, computer, task, automation).
 */

import type { GitStatusResult } from '@/components/files-git-panel/rpc';

/** The card's width, in px. */
export const SUMMARY_CARD_WIDTH = 300;

/** The docked card's column: a 24 gap before the card, the card, a 12 edge after it. */
export const SUMMARY_COLUMN_GAP = 24;
export const SUMMARY_COLUMN_EDGE = 12;
export const SUMMARY_COLUMN_WIDTH = SUMMARY_COLUMN_GAP + SUMMARY_CARD_WIDTH + SUMMARY_COLUMN_EDGE;

/**
 * How far the chat steps in from the left while the card is docked: as far
 * as the card's gap on the right, so the transcript stays centred between the
 * sidebar and the card.
 */
export const SUMMARY_CHAT_INSET = SUMMARY_COLUMN_GAP;

/** Everything the docked card takes from the session column's width. */
export const SUMMARY_DOCK_RESERVE = SUMMARY_COLUMN_WIDTH + SUMMARY_CHAT_INSET;

/**
 * The narrowest the transcript may get beside a docked card (row width,
 * padding included). Below it the card stops taking a column of its own and
 * opens over the chat instead, like a menu.
 */
export const SUMMARY_MIN_DOCKED_CHAT = 760;

/** Whether a session column this wide has room for the card beside the chat. */
export function canDockSummary(columnWidth: number): boolean {
  return columnWidth >= SUMMARY_MIN_DOCKED_CHAT + SUMMARY_DOCK_RESERVE;
}

/**
 * A folder path short enough for one line of the card: the home directory as
 * `~`, and a long path cut in the middle so both ends stay readable, since the
 * start says where the work lives and the end which checkout it is (every
 * worktree of a repo ends in the repo's name).
 *
 *   ~/vicoa/workspaces/vicoa-worktrees/task-x/vicoa → ~/vicoa/…/task-x/vicoa
 */
export function compactPath(path: string, homeDir?: string | null): string {
  const sep = path.includes('\\') && !path.includes('/') ? '\\' : '/';
  const trim = (p: string) => (p.length > 1 ? p.replace(/[\\/]+$/, '') : p);
  let shown = trim(path);
  const home = homeDir ? trim(homeDir) : null;
  if (home && home !== sep) {
    if (shown === home) shown = '~';
    else if (shown.startsWith(home + sep)) shown = `~${shown.slice(home.length)}`;
  }
  const parts = shown.split(sep);
  // Head (root + first folder) and the last two folders; anything shorter
  // than that plus one elided folder is shown whole.
  if (parts.length <= 5) return shown;
  return [...parts.slice(0, 2), '…', ...parts.slice(-2)].join(sep);
}

/** Lines added and removed across every uncommitted change in a status. */
export function changeTotals(status: Pick<GitStatusResult, 'staged' | 'unstaged' | 'untracked'>): {
  additions: number;
  deletions: number;
} {
  let additions = 0;
  let deletions = 0;
  for (const entry of [...status.staged, ...status.unstaged, ...status.untracked]) {
    additions += entry.additions || 0;
    deletions += entry.deletions || 0;
  }
  return { additions, deletions };
}
