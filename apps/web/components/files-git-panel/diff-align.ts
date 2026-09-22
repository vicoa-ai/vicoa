import type { DiffRow, DiffSegment } from './diff-lines';

/** A visual row in split view: a removed line on the left beside its paired
 *  added line on the right. Either side is `null` for a pure insertion/deletion
 *  (a blank cell shows opposite it). Context rows fill both sides. */
export interface SplitPair {
  left: DiffRow | null;
  right: DiffRow | null;
}

/** `alignHunk` output: the same hunk in the two orders the viewer renders.
 *  - `unified` keeps git's order (a region's removes, then its adds); the rows
 *    of a region that reads as an edit carry word-level `segments`.
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
// Region-wide token diff budget (removed tokens × added tokens, after the
// common head and tail are trimmed). Past it the region falls back to the
// per-pair word diff, which is bounded per line.
const MAX_REGION_CELLS = 4_000_000;

// Only pair two lines for the split layout when they're at least this similar;
// below it they're laid out as an independent delete + insert.
const PAIR_THRESHOLD = 0.5;

// An unchanged island this short (non-whitespace chars) between two changed
// runs is swallowed into the change, so `call(foo, bar)` → `call(baz, qux)`
// boxes `foo, bar` as one edit rather than two words around a surviving comma.
const ISLAND_MAX_CHARS = 2;

// Below this share of surviving text (non-whitespace chars that match, over the
// smaller side) a region is a rewrite, not an edit: the line tint alone reads
// better than boxes sprayed around the few tokens that happen to coincide.
const MIN_COVERAGE = 0.3;

// Split into alnum words, whitespace runs, and single other chars (so each
// punctuation mark — and each CJK char — is its own token for fine highlights).
const TOKEN_RE = /[A-Za-z0-9_]+|\s+|[^A-Za-z0-9_\s]/g;

export function tokenize(s: string): string[] {
  return s.match(TOKEN_RE) ?? [];
}

// A token is a whitespace run iff it starts with whitespace (see TOKEN_RE).
const WS_START = /^\s/;

function nonWsLength(token: string): number {
  return WS_START.test(token) ? 0 : token.length;
}

/** How well two tokens match for the region diff: 2 for identical, 1 for two
 *  whitespace runs where one crosses a line break, 0 otherwise. Re-wrapped
 *  prose turns a space into newline+indent (and back) on every line after the
 *  edit; that is not a change worth boxing, but it is a weaker match than the
 *  exact one so the LCS never trades a real line break for a plain space. A
 *  run that stays on its line must match exactly, so an added space is
 *  highlighted. */
function matchScore(a: string, b: string): 0 | 1 | 2 {
  if (a === b) return 2;
  return WS_START.test(a) && WS_START.test(b) && (a.includes('\n') || b.includes('\n')) ? 1 : 0;
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
 *  or when a line is too long to diff cheaply. The fallback for regions too
 *  big for `regionWordDiff`, applied to each split pair on its own. */
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

/** Result of `regionWordDiff`: per-line segments for a region's removed and
 *  added lines, or why there are none. */
export type RegionDiff =
  | { kind: 'segments'; removes: DiffSegment[][]; adds: DiffSegment[][] }
  /** Too little text survives — plain line tint reads better than confetti. */
  | { kind: 'rewrite' }
  /** Past the token budget — the caller falls back to per-pair diffing. */
  | { kind: 'oversized' };

/** Split one side's token stream into per-line segments: a whitespace token
 *  that crosses a line break is cut at the `\n` (which belongs to no line) and
 *  its remainder starts the next line. Such a token is never boxed — the
 *  indentation of a wrapped line is not the edit — and neither is whitespace
 *  at either end of a box (the space after an inserted word), unless the box
 *  is nothing but whitespace, in which case that is the change. Lossless per
 *  line. */
function toRowSegments(tokens: string[], changed: boolean[], rowCount: number): DiffSegment[][] {
  const rows: DiffSegment[][] = Array.from({ length: rowCount }, () => []);
  let r = 0;
  for (let k = 0; k < tokens.length; k++) {
    const parts = tokens[k].split('\n');
    const isChanged = changed[k] && parts.length === 1;
    for (let p = 0; p < parts.length; p++) {
      if (p > 0) r++;
      if (!parts[p]) continue;
      const segs = rows[r];
      const last = segs[segs.length - 1];
      if (last && last.changed === isChanged) last.text += parts[p];
      else segs.push({ text: parts[p], changed: isChanged });
    }
  }
  return rows.map(trimBoxes);
}

/** Move whitespace at the ends of each changed segment into the neighbouring
 *  unchanged one (see `toRowSegments`). */
function trimBoxes(segs: DiffSegment[]): DiffSegment[] {
  const out: DiffSegment[] = [];
  const push = (text: string, changed: boolean) => {
    if (!text) return;
    const last = out[out.length - 1];
    if (last && last.changed === changed) last.text += text;
    else out.push({ text, changed });
  };
  for (const seg of segs) {
    if (!seg.changed || seg.text.trim() === '') {
      push(seg.text, seg.changed);
      continue;
    }
    const core = seg.text.trim();
    const lead = seg.text.length - seg.text.trimStart().length;
    push(seg.text.slice(0, lead), false);
    push(core, true);
    push(seg.text.slice(lead + core.length), false);
  }
  return out;
}

/** Token-level diff of a whole change region — every removed line against
 *  every added line as one text each — so an edit inside re-wrapped prose
 *  (or a block where a line was split or joined) highlights the words that
 *  actually changed instead of the reflow around them. Ordered LCS on tokens
 *  weighted by `matchScore`, then two cleanups: tiny unchanged islands between changes are
 *  absorbed (`ISLAND_MAX_CHARS`), and a region where too little survives
 *  (`MIN_COVERAGE`) gets no segments at all. */
export function regionWordDiff(removes: string[], adds: string[]): RegionDiff {
  const at = tokenize(removes.join('\n'));
  const bt = tokenize(adds.join('\n'));
  const m = at.length;
  const n = bt.length;

  // Trim the common head and tail first: most regions differ in the middle and
  // the quadratic DP only has to cover what's left.
  let head = 0;
  while (head < m && head < n && matchScore(at[head], bt[head]) > 0) head++;
  let tail = 0;
  while (
    tail < m - head &&
    tail < n - head &&
    matchScore(at[m - 1 - tail], bt[n - 1 - tail]) > 0
  ) {
    tail++;
  }
  const cm = m - head - tail;
  const cn = n - head - tail;
  if (cm * cn > MAX_REGION_CELLS) return { kind: 'oversized' };

  // Matched token pairs (aIdx, bIdx), ascending: head, LCS core, tail.
  const pairs: [number, number][] = [];
  for (let k = 0; k < head; k++) pairs.push([k, k]);
  if (cm > 0 && cn > 0) {
    // Weighted LCS (`matchScore` per pair). Scores are ≤ 2·min(cm, cn) ≤
    // 2·√MAX_REGION_CELLS, so 16 bits suffice.
    const dp: Uint16Array[] = Array.from({ length: cm + 1 }, () => new Uint16Array(cn + 1));
    for (let i = 1; i <= cm; i++) {
      const ai = at[head + i - 1];
      const prev = dp[i - 1];
      const cur = dp[i];
      for (let j = 1; j <= cn; j++) {
        const score = matchScore(ai, bt[head + j - 1]);
        let best = prev[j] >= cur[j - 1] ? prev[j] : cur[j - 1];
        if (score > 0 && prev[j - 1] + score > best) best = prev[j - 1] + score;
        cur[j] = best;
      }
    }
    const core: [number, number][] = [];
    let i = cm;
    let j = cn;
    while (i > 0 && j > 0) {
      const score = matchScore(at[head + i - 1], bt[head + j - 1]);
      if (score > 0 && dp[i][j] === dp[i - 1][j - 1] + score) {
        core.push([head + i - 1, head + j - 1]);
        i--;
        j--;
      } else if (dp[i - 1][j] >= dp[i][j - 1]) {
        i--;
      } else {
        j--;
      }
    }
    core.reverse();
    pairs.push(...core);
  }
  for (let k = tail; k > 0; k--) pairs.push([m - k, n - k]);

  const aChanged = new Array<boolean>(m).fill(true);
  const bChanged = new Array<boolean>(n).fill(true);
  for (const [i, j] of pairs) {
    aChanged[i] = false;
    bChanged[j] = false;
  }

  // Absorb short islands: a maximal run of consecutive pairs that has a change
  // on at least one side before it and after it, and too few real characters
  // to be worth a gap in the box. An island with a line break in it stays — a
  // box is never stretched across lines.
  let shared = 0;
  for (let s = 0; s < pairs.length; ) {
    let e = s;
    while (
      e + 1 < pairs.length &&
      pairs[e + 1][0] === pairs[e][0] + 1 &&
      pairs[e + 1][1] === pairs[e][1] + 1
    ) {
      e++;
    }
    let chars = 0;
    let breaks = false;
    for (let k = s; k <= e; k++) {
      const tok = at[pairs[k][0]];
      chars += nonWsLength(tok);
      if (tok.includes('\n')) breaks = true;
    }
    const [firstA, firstB] = pairs[s];
    const [lastA, lastB] = pairs[e];
    const interior = (firstA > 0 || firstB > 0) && (lastA < m - 1 || lastB < n - 1);
    if (interior && !breaks && chars <= ISLAND_MAX_CHARS) {
      for (let k = s; k <= e; k++) {
        aChanged[pairs[k][0]] = true;
        bChanged[pairs[k][1]] = true;
      }
    } else {
      shared += chars;
    }
    s = e + 1;
  }

  let aChars = 0;
  for (const t of at) aChars += nonWsLength(t);
  let bChars = 0;
  for (const t of bt) bChars += nonWsLength(t);
  const smaller = Math.min(aChars, bChars);
  if (smaller === 0 || shared < MIN_COVERAGE * smaller) return { kind: 'rewrite' };

  return {
    kind: 'segments',
    removes: toRowSegments(at, aChanged, removes.length),
    adds: toRowSegments(bt, bChanged, adds.length),
  };
}

/** Re-group a hunk's rows so the viewer can show fine-grained changes: word-
 *  highlight what changed across each region (`regionWordDiff`), and for the
 *  split layout pair each removed line with the added line it became, laying
 *  unpaired lines against a blank counterpart. */
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

    // Word-level segments. A pure insertion/deletion has nothing to compare;
    // an oversized region falls back to diffing each split pair on its own.
    const enriched = new Map<DiffRow, DiffRow>();
    if (removes.length > 0 && adds.length > 0) {
      const rd = regionWordDiff(
        removes.map((r) => r.content),
        adds.map((a) => a.content),
      );
      if (rd.kind === 'segments') {
        removes.forEach((r, k) => enriched.set(r, { ...r, segments: rd.removes[k] }));
        adds.forEach((a, k) => enriched.set(a, { ...a, segments: rd.adds[k] }));
      } else if (rd.kind === 'oversized') {
        for (const op of ops) {
          if (!op.r || !op.a) continue;
          const wd = wordDiff(op.r.content, op.a.content);
          if (!wd) continue;
          enriched.set(op.r, { ...op.r, segments: wd[0] });
          enriched.set(op.a, { ...op.a, segments: wd[1] });
        }
      }
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
