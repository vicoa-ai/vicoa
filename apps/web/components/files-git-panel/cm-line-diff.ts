import { Change, diff, type DiffConfig } from '@codemirror/merge';

/**
 * Line-anchored diff for the @codemirror/merge surfaces.
 *
 * The package diffs the two documents character by character, with a scan
 * budget (`scanLimit`, 500 by default) so a huge or very different pair can't
 * stall the UI. Past the budget it stops looking: everything between the
 * common head and tail becomes ONE change, and a 30 KB file with thirty small
 * edits renders as a single 400-line red block over a single green one.
 *
 * This does what VS Code does instead: diff by line first (each distinct line
 * encoded as one character, so the package's own Myers diff does the work —
 * cheap, since the edit distance is counted in lines), then refine each
 * changed run of lines with the character diff, whose budget now only has to
 * cover that run. Plugged in through `DiffConfig.override`, so it also serves
 * the incremental re-diff the merge view runs around every edit.
 */

// The package's default character budget, applied per changed run of lines.
const CHAR_SCAN_LIMIT = 500;
// Budget for the line diff: the depth in *lines* before it goes crude.
const LINE_SCAN_LIMIT = 20000;

// Line codes start above the control characters (10 = line break, which the
// package's normalizer treats specially) and skip the surrogate range so every
// code is a single, valid UTF-16 unit.
const FIRST_CODE = 0x100;
const SURROGATE_START = 0xd800;
const SURROGATE_END = 0xdfff;
const MAX_CODE = 0xffff;

interface Encoded {
  /** One code unit per line. */
  text: string;
  /** Character offset of each line's start, plus one past the string. */
  starts: number[];
}

/** Encode both strings' lines as single characters with a shared code table,
 *  or `null` when there are more distinct lines than codes. */
function encodeLines(a: string, b: string): [Encoded, Encoded] | null {
  const codes = new Map<string, number>();
  let next = FIRST_CODE;
  const encode = (s: string): Encoded | null => {
    const lines = s.split('\n');
    const chars: string[] = [];
    const starts: number[] = [];
    let pos = 0;
    for (const line of lines) {
      let code = codes.get(line);
      if (code === undefined) {
        if (next === SURROGATE_START) next = SURROGATE_END + 1;
        if (next > MAX_CODE) return null;
        code = next++;
        codes.set(line, code);
      }
      chars.push(String.fromCharCode(code));
      starts.push(pos);
      pos += line.length + 1;
    }
    starts.push(pos);
    return { text: chars.join(''), starts };
  };
  const ea = encode(a);
  const eb = ea && encode(b);
  return ea && eb ? [ea, eb] : null;
}

/** Character range of lines `[from, to)`. A run that reaches the end of the
 *  text takes the line break *before* it rather than the (missing) one after,
 *  so the text outside the change is the same on both sides. */
function lineRange(enc: Encoded, from: number, to: number, length: number): [number, number] {
  const lineCount = enc.starts.length - 1;
  if (to === lineCount && from > 0) return [enc.starts[from] - 1, length];
  return [enc.starts[from], Math.min(enc.starts[to], length)];
}

export function lineRefinedDiff(a: string, b: string): readonly Change[] {
  const encoded = encodeLines(a, b);
  if (!encoded) return diff(a, b, { scanLimit: CHAR_SCAN_LIMIT });
  const [ea, eb] = encoded;

  const out: Change[] = [];
  for (const lc of diff(ea.text, eb.text, { scanLimit: LINE_SCAN_LIMIT })) {
    const [fromA, toA] = lineRange(ea, lc.fromA, lc.toA, a.length);
    const [fromB, toB] = lineRange(eb, lc.fromB, lc.toB, b.length);
    if (fromA === toA || fromB === toB) {
      out.push(new Change(fromA, toA, fromB, toB));
      continue;
    }
    for (const ch of diff(a.slice(fromA, toA), b.slice(fromB, toB), { scanLimit: CHAR_SCAN_LIMIT })) {
      out.push(new Change(fromA + ch.fromA, fromA + ch.toA, fromB + ch.fromB, fromB + ch.toB));
    }
  }
  return out;
}

/** Pass as `diffConfig` to `MergeView` / `unifiedMergeView`. */
export const lineRefinedDiffConfig: DiffConfig = { override: lineRefinedDiff };
