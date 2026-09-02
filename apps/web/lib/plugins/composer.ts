/**
 * The narrowed handle a plugin gets into the composer. Deliberately small: it
 * exposes intent-level operations (insert text, open an existing picker) rather
 * than internal composer state, so a UI refactor can't break plugins and a
 * plugin can't reach into the draft machinery. Tier 1 behaviors are applied
 * through `applyComposerBehavior`.
 */

import { folderPathToMention } from '@/lib/chat-drop';
import type { ComposerActionBehavior } from './types';

/** Existing composer pickers a plugin action may open. */
export type ComposerPanel = 'mention' | 'commands' | 'files' | 'folder';

export interface ComposerContext {
  instanceId: string | null;
  machineId: string | null;
  /** The session's working directory (project root), for path-relative mentions. */
  cwd: string | null;
  agentType: string;
  /** Insert literal text at the cursor. */
  insertText(text: string): void;
  /** Open one of the built-in composer pickers. */
  openPanel(panel: ComposerPanel): void;
}

/** Run a Tier 1 composer action against the live composer context. */
export function applyComposerBehavior(
  behavior: ComposerActionBehavior,
  ctx: ComposerContext,
): void {
  switch (behavior.type) {
    case 'insert-text':
      ctx.insertText(behavior.text);
      return;
    case 'insert-path-ref':
      ctx.insertText(`@${folderPathToMention(behavior.path, ctx.cwd)}`);
      return;
    case 'panel': {
      const map: Record<string, ComposerPanel> = {
        mention: 'mention',
        commands: 'commands',
        files: 'files',
        folder: 'folder',
      };
      const panel = map[behavior.panelId];
      if (panel) ctx.openPanel(panel);
      return;
    }
  }
}
