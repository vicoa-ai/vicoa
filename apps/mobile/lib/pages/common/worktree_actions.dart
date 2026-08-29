import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_git.dart';
import '/custom_code/utils/worktree_selection.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/session_actions.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';

/// Shared worktree removal flow, used by the new-session picker, the worktrees
/// screen, and the post-session-end auto-offer. Mirrors [SessionActions]: it
/// owns the safety checks, confirm dialog, and snack messaging so every surface
/// behaves identically.
///
/// Safety model (`plans/todos/vicoa-app-worktree.md` §5.5 / §8): the daemon is
/// a dumb executor with no session knowledge, so the app enforces the
/// active-session gate; the branch is always kept by the daemon, so a removed
/// worktree's commits stay recoverable.
class WorktreeActions {
  WorktreeActions._();

  static actions.VicoaWsClient get _ws => actions.VicoaWsClient.instance;

  /// Remove [worktree] with full safety:
  ///   1. refuse if another live session runs in it (the daemon can't know);
  ///   2. if the worktree is dirty, confirm with a force warning;
  ///   3. otherwise confirm normally, then remove (branch kept).
  /// [repoCwd] is any path within the repo (used to run the git command).
  /// Returns true iff the worktree was removed.
  static Future<bool> removeWorktree(
    BuildContext context, {
    required String machineId,
    required String repoCwd,
    required WorktreeInfo worktree,
    bool showSuccessSnack = true,
    String? homeDir,
  }) async {
    // 1. Active-session gate — never pull a worktree out from under a live run.
    final sessions = FFAppState().cachedAgentInstances;
    if (worktreeHasActiveSession(worktree.path, sessions, homeDir: homeDir)) {
      await SessionActions.showSnack(
        context,
        AppLocalizations.of(context).worktreeActionsActiveSession,
      );
      return false;
    }

    // 2. Dirty check (best-effort). Unknown status falls through as clean; the
    //    daemon refuses a dirty non-force remove and we surface that below.
    bool dirty = false;
    try {
      final status = await rpcGitStatus(
        call: _ws.callRpc,
        machineId: machineId,
        cwd: worktree.path,
      );
      dirty = !status.isClean;
    } catch (_) {
      // Couldn't read status — proceed and let the daemon be the backstop.
    }
    if (!context.mounted) return false;

    // 3. Confirm.
    final l10n = AppLocalizations.of(context);
    final branch = worktree.branch.isNotEmpty
        ? worktree.branch
        : l10n.worktreeActionsThisWorktree;
    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: l10n.worktreeActionsRemoveTitle,
              content: dirty
                  ? l10n.worktreeActionsRemoveDirtyContent(branch)
                  : l10n.worktreeActionsRemoveContent(branch),
            ),
          ),
        ) ??
        false;
    if (!confirmed || !context.mounted) return false;

    // 4. Remove.
    try {
      await rpcGitWorktreeRemove(
        call: _ws.callRpc,
        machineId: machineId,
        cwd: repoCwd,
        worktreePath: worktree.path,
        force: dirty,
      );
      if (showSuccessSnack && context.mounted) {
        await SessionActions.showSnack(
            context, AppLocalizations.of(context).worktreeActionsRemoved);
      }
      return true;
    } on GitOpsException catch (e) {
      if (context.mounted) {
        await SessionActions.showSnack(
          context,
          AppLocalizations.of(context).worktreeActionsRemoveFailedCode(e.code),
        );
      }
      return false;
    } catch (_) {
      if (context.mounted) {
        await SessionActions.showSnack(
            context, AppLocalizations.of(context).worktreeActionsRemoveFailed);
      }
      return false;
    }
  }

  /// After a session ends, offer to delete its worktree when it's a managed
  /// worktree, clean, and no other live session uses it (§5.5 auto-offer).
  /// Dirty / still-in-use / non-worktree → skip silently. [worktreePath] is the
  /// ended session's `project`.
  static Future<void> offerCleanupAfterSessionEnd(
    BuildContext context, {
    required String machineId,
    required String worktreePath,
  }) async {
    if (!isManagedWorktreePath(worktreePath)) return;

    // Don't offer if another live session shares the worktree.
    if (worktreeHasActiveSession(
      worktreePath,
      FFAppState().cachedAgentInstances,
    )) {
      return;
    }

    // Only auto-offer for a clean worktree; a dirty one is left for explicit
    // removal so we never silently risk uncommitted work.
    try {
      final status = await rpcGitStatus(
        call: _ws.callRpc,
        machineId: machineId,
        cwd: worktreePath,
      );
      if (!status.isClean) return;
    } catch (_) {
      return; // Couldn't confirm clean — don't offer.
    }
    if (!context.mounted) return;

    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: AppLocalizations.of(context).worktreeActionsCleanupTitle,
              content: AppLocalizations.of(context).worktreeActionsCleanupContent,
            ),
          ),
        ) ??
        false;
    if (!confirmed || !context.mounted) return;

    try {
      HapticFeedback.mediumImpact();
      await rpcGitWorktreeRemove(
        call: _ws.callRpc,
        machineId: machineId,
        cwd: worktreePath,
        worktreePath: worktreePath,
        force: false,
      );
      if (context.mounted) {
        await SessionActions.showSnack(
            context, AppLocalizations.of(context).worktreeActionsDeleted);
      }
    } catch (_) {
      // Best-effort cleanup; leave the worktree if it can't be removed.
    }
  }
}
