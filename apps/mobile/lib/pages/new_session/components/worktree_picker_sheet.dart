import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_git.dart';
import '/custom_code/utils/worktree_selection.dart';
import '/pages/common/worktree_actions.dart';

/// The user's choice from the worktree picker: a mode and, for `existing`, the
/// chosen worktree path. Returned to the new-session screen which applies it to
/// the model.
typedef WorktreePick = ({WorktreeMode mode, String? path, String? branch});

/// Bottom sheet for choosing how a new session relates to a git worktree:
/// run in the current branch, fork a new worktree, or reuse an existing one.
/// Mirrors [showDirectoryPickerSheet]'s full-bleed handle + header style.
///
/// Fetches the repo's worktrees over RPC; a non-git directory degrades to just
/// the "Current branch" option. Returns the [WorktreePick] (or `null` on
/// cancel).
Future<WorktreePick?> showWorktreePickerSheet({
  required BuildContext context,
  required String machineId,
  required String cwd,
  required WorktreeMode currentMode,
  String? currentPath,
}) async {
  return showModalBottomSheet<WorktreePick>(
    context: context,
    isScrollControlled: true,
    useSafeArea: false,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _WorktreePickerSheet(
      machineId: machineId,
      cwd: cwd,
      currentMode: currentMode,
      currentPath: currentPath,
    ),
  );
}

class _WorktreePickerSheet extends StatefulWidget {
  const _WorktreePickerSheet({
    required this.machineId,
    required this.cwd,
    required this.currentMode,
    required this.currentPath,
  });
  final String machineId;
  final String cwd;
  final WorktreeMode currentMode;
  final String? currentPath;

  @override
  State<_WorktreePickerSheet> createState() => _WorktreePickerSheetState();
}

class _WorktreePickerSheetState extends State<_WorktreePickerSheet> {
  bool _loading = true;
  String? _error; // 'not_a_repo' or a transport error string
  List<WorktreeInfo> _worktrees = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final worktrees = await rpcGitWorktreeList(
        call: actions.VicoaWsClient.instance.callRpc,
        machineId: widget.machineId,
        cwd: widget.cwd,
      );
      if (!mounted) return;
      setState(() {
        _worktrees = worktrees;
        _loading = false;
      });
    } on GitOpsException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.code;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _pick(WorktreePick pick) {
    HapticFeedback.lightImpact();
    Navigator.of(context).pop(pick);
  }

  /// A worktree row; managed worktrees get swipe-to-remove. The remove flow
  /// owns its own confirm + safety checks; we only refresh the list on success.
  Widget _buildWorktreeRow(WorktreeInfo wt) {
    final row = _WorktreeRow(
      info: wt,
      selected: widget.currentMode == WorktreeMode.existing &&
          widget.currentPath == wt.path,
      onTap: () =>
          _pick((mode: WorktreeMode.existing, path: wt.path, branch: wt.branch)),
    );
    if (!wt.managed) return row;
    return Dismissible(
      key: ValueKey('wt:${wt.path}'),
      direction: DismissDirection.endToStart,
      background: _SwipeRemoveBackground(),
      // We manage the list ourselves (return false), so Dismissible never
      // removes a row whose removal was cancelled or failed.
      confirmDismiss: (_) async {
        final removed = await WorktreeActions.removeWorktree(
          context,
          machineId: widget.machineId,
          repoCwd: widget.cwd,
          worktree: wt,
        );
        if (removed && mounted) {
          setState(() {
            _worktrees =
                _worktrees.where((w) => w.path != wt.path).toList();
          });
        }
        return false;
      },
      child: row,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final isRepo = _error != 'not_a_repo';
    return Container(
      width: double.infinity,
      height: MediaQuery.of(context).size.height * 0.65,
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(24.0),
          topRight: Radius.circular(24.0),
        ),
      ),
      child: Column(mainAxisSize: MainAxisSize.max, children: [
        _SheetHandle(),
        _SheetHeader(
          title: AppLocalizations.of(context).worktreePickerWorktree,
          onClose: () {
            HapticFeedback.lightImpact();
            Navigator.pop(context);
          },
        ),
        Expanded(
          child: ListView(
            padding: EdgeInsets.fromLTRB(
              16.0,
              16.0,
              16.0,
              16.0 + MediaQuery.of(context).padding.bottom,
            ),
            children: [
              _OptionTile(
                icon: FontAwesomeIcons.codeBranch,
                faIcon: true,
                title: AppLocalizations.of(context).worktreePickerCurrentBranch,
                subtitle: AppLocalizations.of(context).worktreePickerCurrentBranchSubtitle,
                selected: widget.currentMode == WorktreeMode.none,
                onTap: () =>
                    _pick((mode: WorktreeMode.none, path: null, branch: null)),
              ),
              const SizedBox(height: 8.0),
              if (isRepo)
                _OptionTile(
                  icon: Icons.add_circle_outline_rounded,
                  title: AppLocalizations.of(context).worktreePickerNewWorktree,
                  subtitle: AppLocalizations.of(context).worktreePickerNewWorktreeSubtitle,
                  selected: widget.currentMode == WorktreeMode.newWorktree,
                  onTap: () =>
                      _pick((mode: WorktreeMode.newWorktree, path: null, branch: null)),
                ),
              if (_loading) ...[
                const SizedBox(height: 24.0),
                Center(
                  child: SizedBox(
                    width: 22.0,
                    height: 22.0,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.0,
                      valueColor:
                          AlwaysStoppedAnimation<Color>(theme.secondaryText),
                    ),
                  ),
                ),
              ],
              if (!_loading && _error == 'not_a_repo')
                _InfoNote(
                  text: AppLocalizations.of(context).worktreePickerNotARepo,
                ),
              if (!_loading && _error != null && _error != 'not_a_repo')
                _ErrorRow(message: _error!, onRetry: _load),
              if (!_loading && _error == null && _worktrees.isNotEmpty) ...[
                const SizedBox(height: 20.0),
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: _sectionLabel(
                      context, AppLocalizations.of(context).worktreePickerExistingWorktrees),
                ),
                const SizedBox(height: 8.0),
                for (final wt in _worktrees) ...[
                  _buildWorktreeRow(wt),
                  const SizedBox(height: 8.0),
                ],
              ],
            ],
          ),
        ),
      ]),
    );
  }
}

Widget _sectionLabel(BuildContext context, String label) {
  final theme = FlutterFlowTheme.of(context);
  return Text(
    label,
    style: theme.labelMedium.override(
      font: GoogleFonts.sourceSans3(),
      fontSize: 15.0,
      fontWeight: FontWeight.w500,
      color: theme.secondaryText,
    ),
  );
}

class _OptionTile extends StatelessWidget {
  const _OptionTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
    this.faIcon = false,
  });
  final IconData icon;
  final bool faIcon;
  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    // Selected rows read as a soft tinted surface (fill + hairline + accent
    // leading icon/check) instead of a loud full-strength ring. The accent is
    // the neutral primaryText — no brand/primary color here.
    final accent = theme.primaryText;
    final iconColor = selected ? accent : theme.secondaryText;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12.0),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 14.0),
        decoration: BoxDecoration(
          color: selected ? accent.withValues(alpha: 0.10) : theme.primaryBackground,
          borderRadius: BorderRadius.circular(12.0),
        ),
        child: Row(children: [
          faIcon
              ? FaIcon(icon, color: iconColor, size: 15.0)
              : Icon(icon, color: iconColor, size: 20.0),
          const SizedBox(width: 12.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    fontWeight: FontWeight.w500,
                    color: selected ? accent : theme.primaryText,
                  ),
                ),
                const SizedBox(height: 2.0),
                Text(
                  subtitle,
                  style: theme.bodySmall.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 12.0,
                    color: theme.secondaryText,
                  ),
                ),
              ],
            ),
          ),
          if (selected) Icon(Icons.check_rounded, color: accent, size: 20.0),
        ]),
      ),
    );
  }
}

class _WorktreeRow extends StatelessWidget {
  const _WorktreeRow({
    required this.info,
    required this.selected,
    required this.onTap,
  });
  final WorktreeInfo info;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final accent = theme.primaryText;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12.0),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 12.0),
        decoration: BoxDecoration(
          color: selected ? accent.withValues(alpha: 0.10) : theme.primaryBackground,
          borderRadius: BorderRadius.circular(12.0),
        ),
        child: Row(children: [
          FaIcon(FontAwesomeIcons.codeBranch,
              color: selected ? accent : theme.secondaryText, size: 13.0),
          const SizedBox(width: 12.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  info.branch.isNotEmpty
                      ? info.branch
                      : AppLocalizations.of(context).worktreePickerDetached,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.firaCode(),
                    fontSize: 14.0,
                    color: selected ? accent : theme.primaryText,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2.0),
                Text(
                  info.managed
                      ? info.path
                      : AppLocalizations.of(context).worktreePickerExternalPath(info.path),
                  style: theme.bodySmall.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 11.0,
                    color: theme.secondaryText,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          if (selected) Icon(Icons.check_rounded, color: accent, size: 18.0),
        ]),
      ),
    );
  }
}

class _InfoNote extends StatelessWidget {
  const _InfoNote({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16.0),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(Icons.info_outline_rounded, size: 15.0, color: theme.secondaryText),
        const SizedBox(width: 8.0),
        Expanded(
          child: Text(
            text,
            style: theme.bodySmall.override(
              font: GoogleFonts.sourceSans3(),
              fontSize: 13.0,
              color: theme.secondaryText,
            ),
          ),
        ),
      ]),
    );
  }
}

class _ErrorRow extends StatelessWidget {
  const _ErrorRow({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16.0),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          AppLocalizations.of(context).worktreePickerLoadFailed,
          style: theme.bodyMedium.override(
            font: GoogleFonts.sourceSans3(),
            fontSize: 14.0,
            color: theme.error,
          ),
        ),
        const SizedBox(height: 8.0),
        TextButton(
            onPressed: onRetry,
            child: Text(AppLocalizations.of(context).commonRetry)),
      ]),
    );
  }
}

class _SwipeRemoveBackground extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      alignment: Alignment.centerRight,
      padding: const EdgeInsets.symmetric(horizontal: 20.0),
      decoration: BoxDecoration(
        color: theme.error.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12.0),
      ),
      child: Icon(Icons.delete_outline_rounded, color: theme.error, size: 20.0),
    );
  }
}

class _SheetHandle extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
      child: Container(
        width: 50.0,
        height: 4.0,
        decoration: BoxDecoration(
          color: FlutterFlowTheme.of(context).alternate,
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({required this.title, required this.onClose});
  final String title;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 8.0),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        FlutterFlowIconButton(
          borderColor: theme.alternate,
          borderRadius: 10.0,
          borderWidth: 1.0,
          buttonSize: 40.0,
          icon: Icon(Icons.close_rounded, color: theme.secondaryText, size: 20.0),
          onPressed: onClose,
        ),
        Text(
          title,
          style: theme.bodyMedium.override(
            font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
            fontSize: 19.0,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(width: 40.0),
      ]),
    );
  }
}
