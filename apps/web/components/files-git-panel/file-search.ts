/**
 * Filename search over the project file index (the same list the @-mention
 * autocomplete uses). A fuzzy, subsequence matcher (VS Code / fzf style): the
 * query's characters must appear in order but may have gaps, so `apphead`
 * finds `app-header.tsx`. Scoring rewards contiguous runs, word/segment
 * boundaries (after `/ - _ .` or a camelCase hump), and matches inside the
 * basename — with a strong bump when the basename starts with the query — so a
 * short prefix hit still beats a scattered path-wide one. Case-insensitive;
 * ties break on shorter path then alphabetically.
 */

const DEFAULT_CAP = 200;

// Point values, tuned so a basename prefix reliably outranks a substring match
// which outranks a scattered subsequence — matching the old ranking's intent
// while adding gap tolerance on top.
const MATCH_BASE = 1;
const CONSECUTIVE_BONUS = 8;
const BOUNDARY_BONUS = 10;
const BASENAME_BONUS = 12;
const PREFIX_BONUS = 40;
// Flat bump for any basename hit, so a file matched on its name always outranks
// one matched only by a scattered hit across its directory path.
const BASENAME_MATCH_BONUS = 30;
// Mild length penalty so shorter paths win otherwise-equal matches.
const LENGTH_PENALTY = 0.1;

export interface FileMatch {
  path: string;
  score: number;
  /** Indices into `path` that the query matched, ascending. */
  positions: number[];
}

function basenameStart(path: string): number {
  return path.lastIndexOf('/') + 1; // 0 when there is no slash
}

function isBoundary(text: string, i: number): boolean {
  if (i === 0) return true;
  const prev = text[i - 1];
  if (prev === '/' || prev === '-' || prev === '_' || prev === '.' || prev === ' ') return true;
  // camelCase hump: a lowercase/digit immediately before an uppercase letter.
  return /[a-z0-9]/.test(prev) && /[A-Z]/.test(text[i]);
}

/**
 * Greedy leftmost subsequence match of `query` (already lowercased) in `text`,
 * scored. Returns null when `text` doesn't contain the query as a subsequence.
 * Every matched char earns the basename bonus, so callers run this over the
 * basename first (where all chars count as basename) before the full path.
 */
function fuzzyMatch(text: string, query: string): { score: number; positions: number[] } | null {
  const lower = text.toLowerCase();
  const positions: number[] = [];
  let qi = 0;
  let score = 0;
  let prevIdx = -2;
  for (let i = 0; i < text.length && qi < query.length; i++) {
    if (lower[i] !== query[qi]) continue;
    let pts = MATCH_BASE;
    if (i === prevIdx + 1) pts += CONSECUTIVE_BONUS;
    if (isBoundary(text, i)) pts += BOUNDARY_BONUS;
    score += pts;
    positions.push(i);
    prevIdx = i;
    qi++;
  }
  if (qi < query.length) return null;
  return { score, positions };
}

/** Ranked fuzzy matches with the matched character positions, for highlighting. */
export function rankFileMatches(paths: string[], query: string, cap = DEFAULT_CAP): FileMatch[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const out: FileMatch[] = [];
  for (const path of paths) {
    const baseStart = basenameStart(path);
    const base = path.slice(baseStart);
    // Prefer matching the basename: it anchors the hit on the file's own name
    // (and its positions) rather than a coincidental run across the directory.
    const baseMatch = fuzzyMatch(base, q);
    let score: number;
    let positions: number[];
    if (baseMatch) {
      score = baseMatch.score + BASENAME_BONUS * baseMatch.positions.length + BASENAME_MATCH_BONUS;
      if (base.toLowerCase().startsWith(q)) score += PREFIX_BONUS;
      positions = baseMatch.positions.map((p) => p + baseStart);
    } else {
      const pathMatch = fuzzyMatch(path, q);
      if (!pathMatch) continue;
      score = pathMatch.score;
      positions = pathMatch.positions;
    }
    score -= path.length * LENGTH_PENALTY;
    out.push({ path, score, positions });
  }
  out.sort(
    (a, b) =>
      b.score - a.score || a.path.length - b.path.length || a.path.localeCompare(b.path),
  );
  return out.slice(0, cap);
}

export function searchFileNames(paths: string[], query: string, cap = DEFAULT_CAP): string[] {
  return rankFileMatches(paths, query, cap).map((m) => m.path);
}
