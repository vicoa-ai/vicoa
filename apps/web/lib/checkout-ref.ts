/**
 * What a git checkout has checked out, as the app labels it.
 *
 * A branch is labelled by its name. A detached HEAD has no name, so it is
 * labelled by its short commit and tagged "detached". A checkout in the middle
 * of a rebase is detached too (git detaches HEAD while it rebases), but to the
 * user it is still on its branch, so it keeps the branch name and is tagged
 * "rebasing" instead.
 */
export type CheckoutRef =
  | { kind: 'branch'; branch: string }
  | { kind: 'rebasing'; branch: string; head: string }
  | { kind: 'detached'; head: string };

/** Git's abbreviated commit, or `""` when the commit is unknown. */
export function shortSha(head: string | null | undefined): string {
  return (head ?? '').trim().slice(0, 7);
}

/**
 * The ref of a checkout from what the daemon reports: `branch` empty means
 * detached, `head` is the commit (absent from an older daemon), and
 * `rebasingBranch` is the branch a detached checkout is rebasing.
 */
export function checkoutRefOf(input: {
  branch?: string | null;
  head?: string | null;
  rebasingBranch?: string | null;
}): CheckoutRef {
  const branch = (input.branch ?? '').trim();
  if (branch) return { kind: 'branch', branch };
  const head = shortSha(input.head);
  const rebasing = (input.rebasingBranch ?? '').trim();
  if (rebasing) return { kind: 'rebasing', branch: rebasing, head };
  return { kind: 'detached', head };
}

/**
 * The ref of a `git status` answer, which reports a detached HEAD differently:
 * `branch` carries the short commit and `detached_head` says it is not a name.
 */
export function checkoutRefOfStatus(status: {
  branch: string | null;
  detached_head?: boolean;
  rebasing_branch?: string;
}): CheckoutRef {
  return status.detached_head
    ? checkoutRefOf({ head: status.branch, rebasingBranch: status.rebasing_branch })
    : checkoutRefOf({ branch: status.branch });
}

/** The branch a checkout is on for the user, rebasing included; `""` when detached. */
export function checkoutRefBranch(ref: CheckoutRef): string {
  return ref.kind === 'detached' ? '' : ref.branch;
}

/** The text label: the branch, else the short commit, else git's own "HEAD". */
export function checkoutRefLabel(ref: CheckoutRef): string {
  if (ref.kind !== 'detached') return ref.branch;
  return ref.head || 'HEAD';
}

/** The tag shown beside the label, with its tooltip. None for a plain branch. */
export function checkoutRefTag(ref: CheckoutRef): { text: string; title: string } | null {
  switch (ref.kind) {
    case 'branch':
      return null;
    case 'rebasing':
      return {
        text: 'rebasing',
        title: ref.head
          ? `Rebasing ${ref.branch}. HEAD stays detached at ${ref.head} until the rebase finishes.`
          : `Rebasing ${ref.branch}. HEAD stays detached until the rebase finishes.`,
      };
    case 'detached':
      return {
        text: 'detached',
        title: `${ref.head ? `Detached HEAD at ${ref.head}` : 'Detached HEAD'}: this checkout is on a commit, not a branch. Commits made here belong to no branch until you create one.`,
      };
  }
}
