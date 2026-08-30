import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import '/pages/rename_dialog/rename_dialog_widget.dart';

/// Shared machine rename/remove flows, mirroring [SessionActions]: each method
/// handles confirm → loading → API call, then invokes the appropriate callback
/// so the caller can update its own state. Reuses the same dialog widgets as
/// session rename/delete so the UX is visually identical.
class MachineActions {
  MachineActions._();

  /// Prompts for a new machine name, then PATCHes it. On success the callback
  /// receives the updated machine summary map returned by the API.
  static Future<void> rename(
    BuildContext context, {
    required String machineId,
    required String currentName,
    required String firebaseEventName,
    Future<void> Function(dynamic updatedMachine)? onSuccess,
    Future<void> Function()? onFailure,
  }) async {
    final newName = await showDialog<String>(
      context: context,
      barrierDismissible: true,
      builder: (_) => Dialog(
        backgroundColor: Colors.transparent,
        child: RenameDialogWidget(
          title: AppLocalizations.of(context).machineActionsRenameTitle,
          initialValue: currentName,
          placeholder: AppLocalizations.of(context).machineActionsRenamePlaceholder,
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
          _LoadingDialog(label: AppLocalizations.of(context).machineActionsRenaming),
    );

    final result = await actions.apiRenameMachine(machineId, trimmed);

    if (!context.mounted) return;
    if (Navigator.canPop(context)) Navigator.of(context).pop();

    if (result != null) {
      await onSuccess?.call(result);
    } else {
      await onFailure?.call();
    }
  }

  /// Confirms, then hard-deletes (forgets) the machine. Copy spells out that
  /// the machine reappears if its daemon reconnects (machine-management D6).
  static Future<void> remove(
    BuildContext context, {
    required String machineId,
    required String firebaseEventName,
    VoidCallback? onBeforeApi,
    Future<void> Function()? onSuccess,
    Future<void> Function()? onFailure,
  }) async {
    final shouldRemove = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: AppLocalizations.of(context).machineActionsRemoveTitle,
              content: AppLocalizations.of(context).machineActionsRemoveContent,
            ),
          ),
        ) ??
        false;

    if (!shouldRemove) return;

    logFirebaseEvent(firebaseEventName);
    HapticFeedback.mediumImpact();
    onBeforeApi?.call();

    if (!context.mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) =>
          _LoadingDialog(label: AppLocalizations.of(context).machineActionsRemoving),
    );

    final success = await actions.apiRemoveMachine(machineId);

    if (!context.mounted) return;
    if (Navigator.canPop(context)) Navigator.of(context).pop();

    if (success) {
      await onSuccess?.call();
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
