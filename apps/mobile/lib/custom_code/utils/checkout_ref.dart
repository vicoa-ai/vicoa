// How a git checkout's ref reads in the app: a branch by name; a checkout in
// the middle of a rebase by the branch it is rebasing (git detaches HEAD for a
// rebase, but the user is still on that branch); any other detached HEAD by
// its short commit. Mirrors `apps/web/lib/checkout-ref.ts`.

import '/l10n/app_localizations.dart';

/// Git's abbreviated commit, or `''` when the commit is unknown.
String shortSha(String head) {
  final trimmed = head.trim();
  return trimmed.length > 7 ? trimmed.substring(0, 7) : trimmed;
}

/// The label of a checkout. [branch] is empty when detached; [head] is its
/// commit (from `git status`, already short); [rebasingBranch] is the branch a
/// detached checkout is rebasing. [unknownCommit] is the label of a detached
/// HEAD whose commit an older daemon did not send.
String checkoutRefLabel(
  AppLocalizations l10n, {
  required String branch,
  required String head,
  required String rebasingBranch,
  required String unknownCommit,
}) {
  if (branch.isNotEmpty) return branch;
  if (rebasingBranch.isNotEmpty) return l10n.worktreesRebasing(rebasingBranch);
  final sha = shortSha(head);
  return sha.isEmpty ? unknownCommit : l10n.worktreesDetachedAt(sha);
}
