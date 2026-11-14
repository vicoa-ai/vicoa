// How a branch's pull request is drawn: which PR belongs to a checkout, and the
// icon + color for its state. The mobile twin of the web's
// `components/dashboard/pr-status.ts`.

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '/custom_code/actions/rpc_github.dart';
import '/l10n/app_localizations.dart';

/// The pull request of a checkout, from a repo's PRs keyed by head branch.
///
/// Three things can tie a PR to it, and the newest PR any of them finds wins:
/// - the local [branch], the usual case;
/// - its [upstream], the remote branch it pushes to. `git push -u origin
///   HEAD:other` opens the PR under `other` while the local branch keeps its
///   name, typically when a worktree whose PR merged is reused for new work;
/// - its [head] commit equal to a PR's, for the same push made without `-u`.
///   Holds until the next local commit, after which the names still apply.
///
/// Newest wins because a branch name can carry history: once a worktree's PR
/// merges, its new work may go up under another name, and the PR the local
/// name still finds is the finished one.
PrInfo? prForCheckout(
  Map<String, PrInfo> prs, {
  required String branch,
  String? upstream,
  String? head,
}) {
  final candidates = <PrInfo?>[
    if (branch.isNotEmpty) prs[branch],
    if (upstream != null && upstream.isNotEmpty) prs[upstream],
    if (head != null && head.isNotEmpty)
      ...prs.values.where((pr) => pr.head == head),
  ];
  PrInfo? best;
  for (final pr in candidates) {
    if (pr != null && (best == null || pr.number > best.number)) best = pr;
  }
  return best;
}

/// A worktree an agent made for itself (Claude Code's `.claude/worktrees/`),
/// which the user never works in: no reason to watch it for PRs.
bool isAgentScratchWorktree(String path) => path.contains('/.claude/worktrees/');

/// GitHub's own state colors (Primer `fgColor-open` / `-done` / `-closed` /
/// `-muted`), hard-coded rather than mapped onto our theme.
///
/// These colors *are* the vocabulary: a developer reads purple as "merged"
/// before reading any label, and only because it is the same purple GitHub
/// uses. Re-tinting them to our palette would keep the shape and throw away
/// the meaning. Same values as the web's `--pr-*` in `globals.css`.
abstract final class PrColors {
  static final _light = <PrState, Color>{
    PrState.open: const HSLColor.fromAHSL(1, 137, 0.66, 0.30).toColor(),
    PrState.merged: const HSLColor.fromAHSL(1, 261, 0.69, 0.59).toColor(),
    PrState.closed: const HSLColor.fromAHSL(1, 356, 0.72, 0.47).toColor(),
    PrState.draft: const HSLColor.fromAHSL(1, 211, 0.11, 0.39).toColor(),
  };
  static final _dark = <PrState, Color>{
    PrState.open: const HSLColor.fromAHSL(1, 128, 0.49, 0.49).toColor(),
    PrState.merged: const HSLColor.fromAHSL(1, 262, 0.89, 0.71).toColor(),
    PrState.closed: const HSLColor.fromAHSL(1, 3, 0.93, 0.63).toColor(),
    PrState.draft: const HSLColor.fromAHSL(1, 214, 0.08, 0.60).toColor(),
  };
  static final _pendingLight = const HSLColor.fromAHSL(1, 40, 1.0, 0.30).toColor();
  static final _pendingDark = const HSLColor.fromAHSL(1, 41, 0.72, 0.48).toColor();

  static Color state(PrState state, Brightness brightness) =>
      (brightness == Brightness.dark ? _dark : _light)[state]!;

  static Color pending(Brightness brightness) =>
      brightness == Brightness.dark ? _pendingDark : _pendingLight;
}

/// Branch glyph for a checkout: the plain branch icon with no PR, a PR icon
/// while one is open, draft or closed, the merge icon once merged. Same size
/// for every state, so a row doesn't jog when the PR data lands a beat after
/// the first paint; only the glyph and color change.
IconData prIcon(PrInfo? pr) => switch (pr?.state) {
      null => FontAwesomeIcons.codeBranch,
      PrState.merged => FontAwesomeIcons.codeMerge,
      _ => FontAwesomeIcons.codePullRequest,
    };

/// Color of [prIcon]: the PR state's color, or [noPr] with no PR.
Color prIconColor(PrInfo? pr, Brightness brightness, {required Color noPr}) =>
    pr == null ? noPr : PrColors.state(pr.state, brightness);

String prStateLabel(PrState state, AppLocalizations l10n) => switch (state) {
      PrState.open => l10n.prStateOpen,
      PrState.draft => l10n.prStateDraft,
      PrState.merged => l10n.prStateMerged,
      PrState.closed => l10n.prStateClosed,
    };

/// Whether the check rollup is worth showing. Not once a PR is merged or
/// closed: a red dot on a merged PR reports on a run that no longer decides
/// anything, and reads as a problem that needs attention.
bool _showsChecks(PrInfo pr) =>
    pr.state != PrState.merged && pr.state != PrState.closed && pr.checks != PrChecks.none;

/// Check-rollup dot color, or null when there is nothing to say.
Color? checksDotColor(PrInfo pr, Brightness brightness) {
  if (!_showsChecks(pr)) return null;
  return switch (pr.checks) {
    PrChecks.pass => PrColors.state(PrState.open, brightness),
    PrChecks.fail => PrColors.state(PrState.closed, brightness),
    PrChecks.pending => PrColors.pending(brightness),
    PrChecks.none => null,
  };
}

/// "Checks passed" / "Checks failing" / "Checks running", or null when absent.
String? checksLabel(PrInfo pr, AppLocalizations l10n) {
  if (!_showsChecks(pr)) return null;
  return switch (pr.checks) {
    PrChecks.pass => l10n.prChecksPassed,
    PrChecks.fail => l10n.prChecksFailing,
    PrChecks.pending => l10n.prChecksRunning,
    PrChecks.none => null,
  };
}
