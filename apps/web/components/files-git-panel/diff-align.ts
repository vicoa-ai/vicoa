import type { DiffRow, DiffSegment } from './diff-lines';

/** A visual row in split view: a removed line on the left beside its paired
 *  added line on the right. Either side is `null` for a pure insertion/deletion
 *  (a blank cell shows opposite it). Context rows fill both sides. */
export interface SplitPair {
  left: DiffRow | null;
  right: DiffRow | null;
}

/** `alignHunk` output: the same hunk in the two orders the viewer renders.
 *  - `unified` keeps git's order (a region's removes, then its adds) but tags
 *    paired add/remove rows with word-level `segments`.
 *  - `split` places each paired remove/add on one row so counterparts sit
 *    side by side, with blanks for unmatched inserts/deletes. */
export interface AlignedHunk {
  unified: DiffRow[];
  split: SplitPair[];
}

// Guardrails so a pathological block (a minified line, a giant rewrite) can't
// turn the O(m·n) alignment or O(len²) word diff into a UI stall. Past these we
// fall back to cheaper index pairing / whole-line highlighting.
const MAX_ALIGN_CELLS = 2500; // removes × adds before we stop similarity-aligning
const MAX_WORD_TOKENS = 400; // per-line tokens before we skip the word diff

// Only pair two lines for intra-line highlighting when they're at least this
// similar; below it they're treated as an independent delete + insert so we
// don't "highlight" two unrelated lines as a near-total rewrite.
const PAIR_THRESHOLD = 0.5;

// Split into alnum words, whitespace runs, and single other chars (so each
// punctuation mark — and each CJK char — is its own token for fine highlights).
const TOKEN_RE = /[A-Za-z0-9_]+|\s+|[^A-Za-z0-9_\s]/g;

export function tokenize(s: string): string[] {
  return s.match(TOKEN_RE) ?? [];
}

function multiset(tokens: string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const t of tokens) counts.set(t, (counts.get(t) ?? 0) + 1);
  return counts;
}

/** Dice-style token overlap in [0,1]: 2·|shared tokens| / (|a| + |b|). Uses
 *  bag-of-tokens intersection (cheap, order-free) — good enough to decide which
 *  lines to pair; the ordered LCS is only run on the pairs we keep. */
function similarity(
  aLen: number,
  bLen: number,
  aSet: Map<string, number>,
  bSet: Map<string, number>,
): number {
  if (aLen === 0 && bLen === 0) return 1;
  if (aLen === 0 || bLen === 0) return 0;
  const [small, large] = aSet.size <= bSet.size ? [aSet, bSet] : [bSet, aSet];
  let shared = 0;
  for (const [tok, c] of small) {
    const c2 = large.get(tok);
    if (c2) shared += Math.min(c, c2);
  }
  return (2 * shared) / (aLen + bLen);
}

type AlignOp = { r: DiffRow | null; a: DiffRow | null };

/** Pair by position, extra lines on either side left unmatched. */
function sequentialPairs(removes: DiffRow[], adds: DiffRow[]): AlignOp[] {
  const ops: AlignOp[] = [];
  const shared = Math.min(removes.length, adds.length);
  for (let k = 0; k < shared; k++) ops.push({ r: removes[k], a: adds[k] });
  for (let k = shared; k < removes.length; k++) ops.push({ r: removes[k], a: null });
  for (let k = shared; k < adds.length; k++) ops.push({ r: null, a: adds[k] });
  return ops;
}

/** Align one change region (its removes and adds) into an ordered op list,
 *  matching corresponding lines even when a line was inserted or removed in the
 *  middle of the block. Order-preserving Needleman–Wunsch: diagonal scores
 *  `similarity − PAIR_THRESHOLD` (so a pair is only taken when it clears the
 *  bar) and gaps are free. */
function alignRegion(removes: DiffRow[], adds: DiffRow[]): AlignOp[] {
  const m = removes.length;
  const n = adds.length;
  if (m === 0) return adds.map((a) => ({ r: null, a }));
  if (n === 0) return removes.map((r) => ({ r, a: null }));
  // A lone remove + lone add is the everyday single-line edit: always pair it
  // so it renders side by side and gets a word diff, even if barely similar.
  if (m === 1 && n === 1) return [{ r: removes[0], a: adds[0] }];
  if (m * n > MAX_ALIGN_CELLS) return sequentialPairs(removes, adds);

  const rTok = removes.map((r) => tokenize(r.content));
  const aTok = adds.map((a) => tokenize(a.content));
  const rSet = rTok.map(multiset);
  const aSet = aTok.map(multiset);

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const diag =
        dp[i - 1][j - 1] +
        (similarity(rTok[i - 1].length, aTok[j - 1].length, rSet[i - 1], aSet[j - 1]) -
          PAIR_THRESHOLD);
      dp[i][j] = Math.max(diag, dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const ops: AlignOp[] = [];
  let i = m;
  let j = n;
  while (i > 0 && j > 0) {
    const diag =
      dp[i - 1][j - 1] +
      (similarity(rTok[i - 1].length, aTok[j - 1].length, rSet[i - 1], aSet[j - 1]) -
        PAIR_THRESHOLD);
    if (dp[i][j] === diag) {
      ops.push({ r: removes[i - 1], a: adds[j - 1] });
      i--;
      j--;
    } else if (dp[i][j] === dp[i - 1][j]) {
      ops.push({ r: removes[i - 1], a: null });
      i--;
    } else {
      ops.push({ r: null, a: adds[j - 1] });
      j--;
    }
  }
  while (i > 0) ops.push({ r: removes[--i], a: null });
  while (j > 0) ops.push({ r: null, a: adds[--j] });
  ops.reverse();
  return ops;
}

function toSegments(tokens: string[], changed: boolean[]): DiffSegment[] {
  const segments: DiffSegment[] = [];
  for (let k = 0; k < tokens.length; k++) {
    const last = segments[segments.length - 1];
    if (last && last.changed === changed[k]) last.text += tokens[k];
    else segments.push({ text: tokens[k], changed: changed[k] });
  }
  return segments;
}

/** Token-level LCS between two lines → per-side segments, where the tokens NOT
 *  on the common subsequence are marked `changed`. Returns `null` when the two
 *  lines share nothing (word highlighting adds no signal — render whole-line)
 *  or when a line is too long to diff cheaply. */
export function wordDiff(a: string, b: string): [DiffSegment[], DiffSegment[]] | null {
  const at = tokenize(a);
  const bt = tokenize(b);
  if (at.length > MAX_WORD_TOKENS || bt.length > MAX_WORD_TOKENS) return null;
  const m = at.length;
  const n = bt.length;
  if (m === 0 || n === 0) return null;

  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        at[i - 1] === bt[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  if (dp[m][n] === 0) return null; // no shared tokens

  const aChanged = new Array<boolean>(m).fill(true);
  const bChanged = new Array<boolean>(n).fill(true);
  let i = m;
  let j = n;
  while (i > 0 && j > 0) {
    if (at[i - 1] === bt[j - 1]) {
      aChanged[i - 1] = false;
      bChanged[j - 1] = false;
      i--;
      j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }
  return [toSegments(at, aChanged), toSegments(bt, bChanged)];
}

/** Re-group a hunk's rows so the viewer can show fine-grained changes: pair
 *  each removed line with the added line it became (word-highlighting the
 *  changed spans) and lay unpaired lines against a blank counterpart. */
export function alignHunk(rows: DiffRow[]): AlignedHunk {
  const unified: DiffRow[] = [];
  const split: SplitPair[] = [];

  let i = 0;
  while (i < rows.length) {
    const row = rows[i];
    if (row.kind === 'context') {
      unified.push(row);
      split.push({ left: row, right: row });
      i++;
      continue;
    }

    // Consume the whole change region (consecutive non-context rows).
    let j = i;
    while (j < rows.length && rows[j].kind !== 'context') j++;
    const region = rows.slice(i, j);
    const removes = region.filter((r) => r.kind === 'remove');
    const adds = region.filter((r) => r.kind === 'add');
    const ops = alignRegion(removes, adds);

    // Attach word-level segments to the pairs that partially overlap.
    const enriched = new Map<DiffRow, DiffRow>();
    for (const op of ops) {
      if (!op.r || !op.a) continue;
      const wd = wordDiff(op.r.content, op.a.content);
      if (!wd) continue;
      enriched.set(op.r, { ...op.r, segments: wd[0] });
      enriched.set(op.a, { ...op.a, segments: wd[1] });
    }
    const pick = (r: DiffRow) => enriched.get(r) ?? r;

    // Unified: keep git's original region order (removes then adds).
    for (const r of region) unified.push(pick(r));
    // Split: one visual row per op, counterparts side by side.
    for (const op of ops) {
      split.push({ left: op.r ? pick(op.r) : null, right: op.a ? pick(op.a) : null });
    }
    i = j;
  }

  return { unified, split };
}
