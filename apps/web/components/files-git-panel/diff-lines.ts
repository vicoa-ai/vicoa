import type { DiffHunk } from './rpc';

/** One run of characters within a changed line. `changed` segments are the
 *  words/chars that actually differ from the paired line; they get the brighter
 *  intra-line highlight, while `changed: false` runs sit on the plain line tint.
 *  Only set on add/remove rows that `alignHunk` paired to a counterpart. */
export interface DiffSegment {
  text: string;
  changed: boolean;
}

export interface DiffRow {
  kind: 'add' | 'remove' | 'context';
  content: string;
  oldNo: number | null;
  newNo: number | null;
  /** Word-level breakdown for intra-line highlighting; absent = whole line. */
  segments?: DiffSegment[];
}

export function hunkToRows(hunk: DiffHunk): DiffRow[] {
  const rows: DiffRow[] = [];
  let oldNo = hunk.old_start;
  let newNo = hunk.new_start;
  for (const line of hunk.lines) {
    if (line.type === 'context') {
      rows.push({ kind: 'context', content: line.content, oldNo, newNo });
      oldNo += 1;
      newNo += 1;
    } else if (line.type === 'add') {
      rows.push({ kind: 'add', content: line.content, oldNo: null, newNo });
      newNo += 1;
    } else {
      rows.push({ kind: 'remove', content: line.content, oldNo, newNo: null });
      oldNo += 1;
    }
  }
  return rows;
}
