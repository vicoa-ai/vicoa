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
/// a dumb executor with no session knowledge, so the app finds the worktree's
/// live sessions, names them in the confirm and archives them before the folder
/// goes (as the web does); the branch is always kept by the daemon, so a
/// removed worktree's commits stay recoverable.
class WorktreeActions {
  WorktreeActions._();

  static actions.VicoaWsClient get _ws => actions.VicoaWsClient.instance;

  /// How long a failure stays on screen: it carries git's reason, which needs
  /// reading, unlike a success toast.
  static const int _errorSnackMs = 6000;

  /// The repo's main checkout for [cwd] (any folder of the repo, the worktree
  /// being removed included), or [cwd] when it can't be resolved. Older
  /// daemons run the remove's git from `cwd` after moving the worktree away,
  /// so a `cwd` inside that worktree (the Worktrees page opened from one of
  /// its sessions, or the post-session offer) failed with "cannot change to".
  static Future<String> _mainCheckout(String machineId, String cwd) async {
    try {
      final listing = await rpcGitWorktreeListing(
          call: _ws.callRpc, machineId: machineId, cwd: cwd);
      return listing.mainPath ?? cwd;
    } catch (_) {
      return cwd;
    }
  }

  /// Remove [worktree] with full safety:
  ///   1. find the live sessions running in it (the daemon can't know);
  ///   2. confirm, warning that those sessions get archived and, if the
  ///      worktree is dirty, that the remove is forced;
  ///   3. archive the sessions, then remove (branch kept).
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
    // 1. Live sessions in the worktree: archived after the confirm, so a
    //    session is never left running in a folder that's gone.
    final sessionIds = worktreeActiveSessionIds(
        worktree.path, FFAppState().cachedAgentInstances,
        homeDir: homeDir);

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
    var content = dirty
        ? l10n.worktreeActionsRemoveDirtyContent(branch)
        : l10n.worktreeActionsRemoveContent(branch);
    if (sessionIds.isNotEmpty) {
      content = '$content\n\n${l10n.worktreeActionsRemoveSessionsNote(sessionIds.length)}';
    }
    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: l10n.worktreeActionsRemoveTitle,
              content: content,
            ),
          ),
        ) ??
        false;
    if (!confirmed || !context.mounted) return false;

    // 4. Archive its sessions, all at once (the web's archive: status
    //    COMPLETED). If any fails, stop: the folder stays until they're gone.
    if (sessionIds.isNotEmpty) {
      final results = await Future.wait(sessionIds.map(
          (id) => actions.apiUpdateInstanceStatus(id, 'COMPLETED')));
      _markArchivedInCache([
        for (var i = 0; i < sessionIds.length; i++)
          if (results[i]) sessionIds[i],
      ]);
      if (results.contains(false)) {
        if (context.mounted) {
          await SessionActions.showSnack(
              context, AppLocalizations.of(context).worktreeActionsArchiveFailed,
              waitTime: _errorSnackMs);
        }
        return false;
      }
      if (!context.mounted) return false;
    }

    // 5. Remove.
    try {
      await rpcGitWorktreeRemove(
        call: _ws.callRpc,
        machineId: machineId,
        cwd: await _mainCheckout(machineId, repoCwd),
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
          waitTime: _errorSnackMs,
        );
      }
      return false;
    } catch (_) {
      if (context.mounted) {
        await SessionActions.showSnack(
            context, AppLocalizations.of(context).worktreeActionsRemoveFailed,
            waitTime: _errorSnackMs);
      }
      return false;
    }
  }

  /// Mark [ids] closed in the shared session cache right away, so the worktree
  /// screens (and a retry after a failed remove) stop counting them as live
  /// before the home list next reloads from the server.
  static void _markArchivedInCache(List<String> ids) {
    if (ids.isEmpty) return;
    final archived = ids.toSet();
    final app = FFAppState();
    app.cachedAgentInstances = [
      for (final s in app.cachedAgentInstances)
        if (s is Map<String, dynamic> && archived.contains(s['id']))
          {...s, 'status': 'COMPLETED'}
        else
          s,
    ];
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
        cwd: await _mainCheckout(machineId, worktreePath),
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
