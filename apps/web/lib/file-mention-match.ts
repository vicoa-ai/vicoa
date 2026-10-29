import type { FileMention } from '@/lib/backend-api';

// The `@` file picker's matching, shared by every surface that offers it (the
// textarea composers and the task description editor) so a query ranks the
// same files everywhere.

/** Index entries for folders carry a trailing "/" (see the daemon's
 * `scan_project_files`); everything else is a file. */
export function isFolderPath(path: string): boolean {
  return path.endsWith('/');
}

// Cap fuzzy-match scan cost on huge repos. Browsing 20k file paths through
// `fuzzyMatch` per keystroke pegs the main thread; the panel only shows 50
// results anyway, so scanning the most-relevant 5k is plenty.
export const MENTION_SEARCH_CAP = 5000;

/** How many rows the panel lists. */
export const MENTION_RESULT_LIMIT = 50;

export function fuzzyMatch(search: string, target: string): number {
  const searchLower = search.toLowerCase();
  const targetLower = target.toLowerCase();

  let searchIndex = 0;
  let score = 0;
  let consecutiveMatches = 0;

  for (let i = 0; i < targetLower.length && searchIndex < searchLower.length; i++) {
    if (targetLower[i] === searchLower[searchIndex]) {
      searchIndex++;
      consecutiveMatches++;
      score += 1 + consecutiveMatches;
      if (i > 0 && targetLower[i - 1] === '/') score += 5;
      if (i === 0) score += 10;
    } else {
      consecutiveMatches = 0;
    }
  }

  if (searchIndex < searchLower.length) return 0;
  score -= target.length * 0.1;
  return score;
}

/** The capped slice of the index a query scans. Recompute it when the file
 * list changes, not per keystroke. */
export function searchableFileMentions(files: FileMention[]): FileMention[] {
  return files.length > MENTION_SEARCH_CAP ? files.slice(0, MENTION_SEARCH_CAP) : files;
}

/** The rows for `query`: the first files for an empty query, otherwise the
 * best fuzzy matches, best first. */
export function matchFileMentions(searchable: FileMention[], query: string): FileMention[] {
  if (query === '') return searchable.slice(0, MENTION_RESULT_LIMIT);
  return searchable
    .map((file) => ({ file, score: fuzzyMatch(query, file.path) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, MENTION_RESULT_LIMIT)
    .map(({ file }) => file);
}
