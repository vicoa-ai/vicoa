import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import '/pages/common/worktree_actions.dart';
import '/pages/rename_dialog/rename_dialog_widget.dart';
import '/pages/session_info_sheet/session_info_sheet_widget.dart';
import '/pages/snack_bar/snack_bar_widget.dart';

/// Shared close/delete session dialogs used by both the home list and the chat
/// page. Each method handles confirm → loading → API call, then invokes the
/// appropriate callback so the caller can update its own state.
class SessionActions {
  SessionActions._();

  /// Shows a transient snack message using the shared [SnackBarWidget].
  /// Rendered as a modal route so it appears above bottom sheets and dialogs,
  /// unlike a native ScaffoldMessenger SnackBar.
  static Future<void> showSnack(
    BuildContext context,
    String message, {
    int waitTime = 2000,
  }) async {
    if (!context.mounted) return;
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.transparent,
      builder: (context) => Padding(
        padding: MediaQuery.viewInsetsOf(context),
        child: SnackBarWidget(content: message, waitTime: waitTime),
      ),
    );
  }

  static Future<void> closeSession(
    BuildContext context, {
    required String instanceId,
    required String firebaseEventName,
    /// Called immediately before the API call (e.g. optimistic UI updates).
    VoidCallback? onBeforeApi,
    /// Called when the API succeeds. Runs while [context] is still mounted.
    Future<void> Function()? onSuccess,
    /// Called when the API fails. Runs while [context] is still mounted.
    Future<void> Function()? onFailure,
  }) async {
    final shouldClose = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: AppLocalizations.of(context).sessionActionsCloseTitle,
              content: AppLocalizations.of(context).sessionActionsCloseContent,
            ),
          ),
        ) ??
        false;

    if (!shouldClose) return;

    logFirebaseEvent(firebaseEventName);
    HapticFeedback.mediumImpact();
    onBeforeApi?.call();

    if (!context.mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) =>
          _LoadingDialog(label: AppLocalizations.of(context).sessionActionsClosing),
    );

    final success =
        await actions.apiUpdateInstanceStatus(instanceId, 'COMPLETED');

    if (!context.mounted) return;
    if (Navigator.canPop(context)) Navigator.of(context).pop();

    if (success) {
      await onSuccess?.call();
    } else {
      await onFailure?.call();
    }
  }

  static Future<void> deleteSession(
    BuildContext context, {
    required String instanceId,
    required String firebaseEventName,
    VoidCallback? onBeforeApi,
    Future<void> Function()? onSuccess,
    Future<void> Function()? onFailure,
  }) async {
    // Capture the session's worktree context BEFORE the API removes it from the
    // cache, so we can offer to clean up its worktree once it's gone (§5.5).
    final instance = FFAppState().cachedAgentInstances.firstWhere(
          (i) => i is Map && i['id'] == instanceId,
          orElse: () => null,
        );
    final worktreeProject =
        (instance is Map ? instance['project'] : null)?.toString();
    final worktreeMachineId =
        (instance is Map ? instance['machine_id'] : null)?.toString();

    final shouldDelete = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: AppLocalizations.of(context).sessionActionsDeleteTitle,
              content: AppLocalizations.of(context).sessionActionsDeleteContent,
            ),
          ),
        ) ??
        false;

    if (!shouldDelete) return;

    logFirebaseEvent(firebaseEventName);
    HapticFeedback.mediumImpact();
    onBeforeApi?.call();

    if (!context.mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) =>
          _LoadingDialog(label: AppLocalizations.of(context).sessionActionsDeleting),
    );

    final success = await actions.apiDeleteAgentInstance(instanceId);

    if (!context.mounted) return;
    if (Navigator.canPop(context)) Navigator.of(context).pop();

    if (success) {
      await onSuccess?.call();
      // Offer to clean up the worktree this session ran in, if it was one.
      // No-op for ordinary directories (handled inside the helper).
      if (context.mounted &&
          worktreeProject != null &&
          worktreeProject.isNotEmpty &&
          worktreeMachineId != null &&
          worktreeMachineId.isNotEmpty) {
        await WorktreeActions.offerCleanupAfterSessionEnd(
          context,
          machineId: worktreeMachineId,
          worktreePath: worktreeProject,
        );
      }
    } else {
      await onFailure?.call();
    }
  }

  /// Opens the session info bottom sheet. The caller handles title-change
  /// side effects via [onTitleChanged].
  static Future<void> showSessionInfo(
    BuildContext context, {
    required String instanceId,
    required dynamic instanceData,
    required String firebaseEventName,
    ValueChanged<String>? onTitleChanged,
  }) async {
    logFirebaseEvent(firebaseEventName);
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: true,
      builder: (_) => SessionInfoSheetWidget(
        instanceId: instanceId,
        instanceData: instanceData,
        onTitleChanged: onTitleChanged,
      ),
    );
  }

  /// Toggle the pin state of a session. Returns true on success.
  /// Unlike [closeSession]/[deleteSession], no confirm + loading dialog —
  /// the caller is expected to flip state optimistically.
  static Future<bool> togglePin({
    required String instanceId,
    required bool pinned,
  }) async {
    final result = await actions.apiUpdateAgentInstance(
      instanceId,
      {'pinned': pinned},
    );
    return result is Map;
  }

  /// Prompts for a new session name, then PATCHes it. Mirrors [closeSession]
  /// shape: confirm → loading → API → success/failure callback.
  static Future<void> renameSession(
    BuildContext context, {
    required String instanceId,
    required String currentName,
    required String firebaseEventName,
    /// Receives the trimmed new name when the API call succeeds.
    Future<void> Function(String newName)? onSuccess,
    Future<void> Function()? onFailure,
  }) async {
    final newName = await showDialog<String>(
      context: context,
      barrierDismissible: true,
      builder: (_) => Dialog(
        backgroundColor: Colors.transparent,
        child: RenameDialogWidget(
          title: AppLocalizations.of(context).sessionActionsRenameTitle,
          initialValue: currentName,
          placeholder: AppLocalizations.of(context).sessionActionsRenamePlaceholder,
        ),
      ),
    );

    if (newName == null) return;
    final trimmed = newName.trim();
    if (trimmed.isEmpty || trimmed == currentName) return;

    logFirebaseEvent(firebaseEventName);

    if (!context.mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) =>
          _LoadingDialog(label: AppLocalizations.of(context).sessionActionsRenaming),
    );

    final success = await actions.apiUpdateInstanceName(instanceId, trimmed);

    if (!context.mounted) return;
    if (Navigator.canPop(context)) Navigator.of(context).pop();

    if (success) {
      await onSuccess?.call(trimmed);
    } else {
      await onFailure?.call();
    }
  }
}

// ---------------------------------------------------------------------------

class _LoadingDialog extends StatelessWidget {
  const _LoadingDialog({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: MediaQuery.sizeOf(context).width * 0.8,
        padding: const EdgeInsets.all(24.0),
        decoration: BoxDecoration(
          color: FlutterFlowTheme.of(context).secondaryBackground,
          borderRadius: BorderRadius.circular(24.0),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(
                FlutterFlowTheme.of(context).primary,
              ),
            ),
            const SizedBox(width: 16.0),
            Text(
              label,
              style: FlutterFlowTheme.of(context).bodyMedium.override(
                    color: FlutterFlowTheme.of(context).primaryText,
                    fontSize: 16.0,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}
