import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/rpc_git.dart';
import '/custom_code/utils/worktree_selection.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/session_actions.dart';
import '/pages/common/worktree_actions.dart';

/// Bottom sheet showing one worktree's details (branch, path, type, status) and,
/// for vicoa-managed worktrees, a Remove action. Mirrors the session info sheet
/// styling. Returns `true` if the worktree was removed.
Future<bool?> showWorktreeDetailSheet({
  required BuildContext context,
  required String machineId,
  required String repoCwd,
  required WorktreeInfo worktree,
  String? homeDir,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => Padding(
      padding: MediaQuery.viewInsetsOf(ctx),
      child: _WorktreeDetailSheet(
        machineId: machineId,
        repoCwd: repoCwd,
        worktree: worktree,
        homeDir: homeDir,
      ),
    ),
  );
}

class _WorktreeDetailSheet extends StatefulWidget {
  const _WorktreeDetailSheet({
    required this.machineId,
    required this.repoCwd,
    required this.worktree,
    this.homeDir,
  });

  final String machineId;
  final String repoCwd;
  final WorktreeInfo worktree;
  final String? homeDir;

  @override
  State<_WorktreeDetailSheet> createState() => _WorktreeDetailSheetState();
}

class _WorktreeDetailSheetState extends State<_WorktreeDetailSheet> {
  bool _removing = false;

  WorktreeInfo get _wt => widget.worktree;

  bool get _inUse => worktreeHasActiveSession(
      _wt.path, FFAppState().cachedAgentInstances,
      homeDir: widget.homeDir);

  Future<void> _remove() async {
    if (_removing) return;
    setState(() => _removing = true);
    // WorktreeActions owns the confirm dialog + safety checks. Suppress its
    // success snack — the worktrees page shows it after this sheet has closed,
    // so it never stacks on top of the still-open sheet.
    final removed = await WorktreeActions.removeWorktree(
      context,
      machineId: widget.machineId,
      repoCwd: widget.repoCwd,
      worktree: _wt,
      showSuccessSnack: false,
      homeDir: widget.homeDir,
    );
    if (!mounted) return;
    if (removed) {
      Navigator.of(context).pop(true);
    } else {
      setState(() => _removing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final branch = _wt.branch.isNotEmpty ? _wt.branch : l10n.worktreesDetached;
    final inUse = _inUse;

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(24.0),
          topRight: Radius.circular(24.0),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
            child: Container(
              width: 50.0,
              height: 4.0,
              decoration: BoxDecoration(
                color: theme.alternate,
                borderRadius: BorderRadius.circular(8.0),
              ),
            ),
          ),
          Padding(
            padding:
                const EdgeInsetsDirectional.fromSTEB(18.0, 8.0, 16.0, 0.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  l10n.worktreeDetailWorktree,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
                    fontSize: 20.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                FlutterFlowIconButton(
                  borderColor: theme.alternate,
                  borderRadius: 10.0,
                  borderWidth: 1.0,
                  buttonSize: 40.0,
                  icon: Icon(Icons.close_rounded,
                      color: theme.secondaryText, size: 20.0),
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    Navigator.pop(context);
                  },
                ),
              ],
            ),
          ),
          Padding(
            padding:
                const EdgeInsetsDirectional.fromSTEB(16.0, 24.0, 16.0, 24.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                _group(theme, [
                  _infoRow(theme,
                      icon: FontAwesomeIcons.codeBranch,
                      faIcon: true,
                      label: l10n.worktreeDetailBranch,
                      value: branch,
                      mono: true),
                  _infoRow(theme,
                      icon: Icons.folder_outlined,
                      label: l10n.worktreeDetailPath,
                      value: relativizeHome(_wt.path, widget.homeDir),
                      copyable: true),
                  _infoRow(theme,
                      icon: Icons.start_rounded,
                      label: l10n.worktreeDetailOrigin,
                      value: _wt.managed
                          ? l10n.worktreeDetailOriginVicoa
                          : l10n.worktreeDetailOriginExternal),
                  _infoRow(theme,
                      icon: inUse
                          ? Icons.toggle_on_rounded
                          : Icons.toggle_off_rounded,
                      label: l10n.worktreeDetailStatus,
                      value: inUse
                          ? l10n.worktreeDetailStatusInUse
                          : l10n.worktreeDetailStatusIdle),
                ]),
                const SizedBox(height: 20.0),
                _actionArea(theme, inUse),
                SizedBox(height: MediaQuery.of(context).padding.bottom),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _actionArea(FlutterFlowTheme theme, bool inUse) {
    final l10n = AppLocalizations.of(context);
    if (!_wt.managed) {
      return _note(
        theme,
        l10n.worktreeDetailNotManagedNote,
      );
    }
    final disabled = inUse || _removing;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(14.0),
            onTap: disabled
                ? null
                : () {
                    HapticFeedback.mediumImpact();
                    _remove();
                  },
            child: Container(
              width: double.infinity,
              decoration: BoxDecoration(
                color: theme.primaryBackground,
                borderRadius: BorderRadius.circular(14.0),
                border: Border.all(color: theme.alternate, width: 1.0),
              ),
              padding: const EdgeInsetsDirectional.fromSTEB(
                  16.0, 14.0, 16.0, 14.0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      l10n.worktreeDetailRemoveWorktree,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: disabled ? theme.secondaryText : theme.error,
                        fontSize: 16.0,
                        letterSpacing: 0.0,
                      ),
                    ),
                  ),
                  if (_removing)
                    SizedBox(
                      width: 18.0,
                      height: 18.0,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.0,
                        valueColor:
                            AlwaysStoppedAnimation<Color>(theme.secondaryText),
                      ),
                    )
                  else
                    Icon(Icons.delete_outline_rounded,
                        color: disabled ? theme.secondaryText : theme.error,
                        size: 22.0),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 8.0),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(4.0, 0.0, 4.0, 0.0),
          child: Text(
            inUse
                ? l10n.worktreeDetailInUseDescription
                : l10n.worktreeDetailRemoveDescription,
            style: theme.labelSmall.override(
              font: GoogleFonts.sourceSans3(),
              color: theme.secondaryText,
              fontSize: 12.0,
              letterSpacing: 0.0,
              lineHeight: 1.4,
            ),
          ),
        ),
      ],
    );
  }

  Widget _group(FlutterFlowTheme theme, List<Widget> rows) {
    final children = <Widget>[];
    for (var i = 0; i < rows.length; i++) {
      if (i > 0) {
        children.add(Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
          child: Container(
            height: 0.5,
            color: theme.secondaryText.withValues(alpha: 0.12),
          ),
        ));
      }
      children.add(rows[i]);
    }
    return Container(
      width: double.infinity,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(14.0),
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: children),
    );
  }

  Widget _infoRow(
    FlutterFlowTheme theme, {
    required IconData icon,
    required String label,
    required String value,
    bool faIcon = false,
    bool mono = false,
    bool copyable = false,
    Color? valueColor,
  }) {
    return Container(
      width: double.infinity,
      padding: EdgeInsetsDirectional.fromSTEB(
          16.0, 12.0, copyable ? 8.0 : 16.0, 12.0),
      child: Row(
        children: [
          SizedBox(
            width: 20.0,
            height: 20.0,
            child: Center(
              child: faIcon
                  ? FaIcon(icon, color: theme.secondaryText, size: 15.0)
                  : Icon(icon, color: theme.secondaryText, size: 20.0),
            ),
          ),
          const SizedBox(width: 14.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  style: theme.labelSmall.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.secondaryText,
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                  ),
                ),
                const SizedBox(height: 2.0),
                Text(
                  value,
                  maxLines: copyable ? 3 : 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: mono ? GoogleFonts.firaCode() : GoogleFonts.sourceSans3(),
                    color: valueColor ?? theme.primaryText,
                    fontSize: mono ? 14.0 : 16.0,
                    letterSpacing: 0.0,
                  ),
                ),
              ],
            ),
          ),
          if (copyable)
            IconButton(
              icon: Icon(Icons.content_copy_rounded,
                  color: theme.secondaryText, size: 20.0),
              tooltip: AppLocalizations.of(context).worktreeDetailCopyPath,
              onPressed: () async {
                HapticFeedback.lightImpact();
                await Clipboard.setData(ClipboardData(text: value));
                if (mounted) {
                  await SessionActions.showSnack(context,
                      AppLocalizations.of(context).worktreeDetailPathCopied);
                }
              },
            ),
        ],
      ),
    );
  }

  Widget _note(FlutterFlowTheme theme, String text) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(14.0),
      ),
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 14.0, 16.0, 14.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline_rounded,
              color: theme.secondaryText, size: 18.0),
          const SizedBox(width: 12.0),
          Expanded(
            child: Text(
              text,
              style: theme.bodySmall.override(
                font: GoogleFonts.sourceSans3(),
                color: theme.secondaryText,
                fontSize: 13.0,
                letterSpacing: 0.0,
                lineHeight: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
