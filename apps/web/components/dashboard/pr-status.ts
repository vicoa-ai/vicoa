import {
  GitBranch,
  GitMerge,
  GitPullRequest,
  GitPullRequestClosed,
  GitPullRequestDraft,
  type LucideIcon,
} from 'lucide-react';

/** A branch's pull request, as returned by the daemon's `github-pr-list`. */
export interface PrInfo {
  number: number;
  title: string;
  state: PrState;
  url: string;
  checks: PrChecks;
}

export type PrState = 'open' | 'draft' | 'merged' | 'closed';
export type PrChecks = 'pass' | 'fail' | 'pending' | 'none';

/**
 * GitHub's own state colors (Primer `fgColor-open` / `-done` / `-closed` /
 * `-muted`), hard-coded rather than mapped onto our theme tokens.
 *
 * These four colors *are* the vocabulary — a developer reads purple as "merged"
 * before reading any label, and only because it is the same purple GitHub uses.
 * Re-tinting them to our palette would keep the shape and throw away the
 * meaning, so this is the one place where matching another product beats
 * matching ourselves.
 *
 * Values live in globals.css as --pr-open/-merged/-closed/-draft/-pending.
 */
const PR_PRESENTATION: Record<
  PrState,
  { icon: LucideIcon; className: string; label: string }
> = {
  open: {
    icon: GitPullRequest,
    className: 'text-pr-open',
    label: 'Open',
  },
  merged: {
    icon: GitMerge,
    className: 'text-pr-merged',
    label: 'Merged',
  },
  closed: {
    icon: GitPullRequestClosed,
    className: 'text-pr-closed',
    label: 'Closed',
  },
  // A draft is deliberately as quiet as having no PR at all: opening one is not
  // yet a claim that the branch is done, so it should not pull the eye.
  draft: {
    icon: GitPullRequestDraft,
    className: 'text-pr-draft',
    label: 'Draft',
  },
};

/** Icon + color for a branch row — the plain branch icon when there is no PR. */
export function prPresentation(pr: PrInfo | null | undefined): {
  icon: LucideIcon;
  className: string;
  label: string | null;
} {
  if (!pr) {
    return { icon: GitBranch, className: 'text-muted-foreground/50', label: null };
  }
  return PR_PRESENTATION[pr.state];
}

/**
 * Check-rollup dot color, or null when there is nothing to say.
 *
 * Suppressed once a PR is merged or closed: a red dot on a merged PR reports on
 * a run that no longer decides anything, and reads as a problem that needs
 * attention.
 */
export function checksDotClassName(pr: PrInfo): string | null {
  if (pr.state === 'merged' || pr.state === 'closed') return null;
  switch (pr.checks) {
    case 'pass':
      return 'bg-pr-open';
    case 'fail':
      return 'bg-pr-closed';
    case 'pending':
      return 'bg-pr-pending';
    case 'none':
      return null;
  }
}

/** "Checks passed" / "Checks failing" / "Checks running", or null when absent. */
export function checksLabel(pr: PrInfo): string | null {
  if (pr.state === 'merged' || pr.state === 'closed') return null;
  switch (pr.checks) {
    case 'pass':
      return 'Checks passed';
    case 'fail':
      return 'Checks failing';
    case 'pending':
      return 'Checks running';
    case 'none':
      return null;
  }
}
