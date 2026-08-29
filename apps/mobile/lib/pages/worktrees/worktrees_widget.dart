import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_git.dart';
import '/custom_code/utils/machine_utils.dart' as mutils;
import '/custom_code/utils/worktree_selection.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/session_actions.dart';
import 'worktree_detail_sheet.dart';
import 'worktrees_model.dart';
export 'worktrees_model.dart';

/// Manage a repo's git worktrees: list them (machines-page styling) and open a
/// detail sheet to inspect / remove the vicoa-managed ones. Each card's trailing
/// indicator signals delete-safety at a glance (in use / external / removable);
/// removal lives in the detail sheet, not an inline button. Entry point: a
/// session's info sheet.
class WorktreesWidget extends StatefulWidget {
  const WorktreesWidget({
    super.key,
    required this.machineId,
    required this.cwd,
    this.projectName,
  });

  static String routeName = 'Worktrees';
  static String routePath = '/worktrees';

  final String machineId;
  final String cwd;
  final String? projectName;

  @override
  State<WorktreesWidget> createState() => _WorktreesWidgetState();
}

class _WorktreesWidgetState extends State<WorktreesWidget> {
  late WorktreesModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();

  // The machine's home dir — used to collapse git's absolute worktree paths to
  // `~` form (for display + matching them against `~`-form session projects).
  String? _homeDir;

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => WorktreesModel());
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'Worktrees'});
    _resolveHomeDir();
    SchedulerBinding.instance.addPostFrameCallback(
      (_) => _model.load(widget.machineId, widget.cwd),
    );
  }

  /// Resolve the machine's home dir from cache; fall back to a one-off fetch so
  /// path relativization + the in-use match work even if the machine wasn't
  /// cached yet. Best-effort: on failure paths stay absolute and the in-use
  /// match degrades to exact string compare.
  void _resolveHomeDir() {
    final cached = FFAppState().cachedMachines.firstWhere(
      (m) => mutils.machineId(m) == widget.machineId,
      orElse: () => null,
    );
    final home = mutils.getMachineHomeDir(cached);
    if (home != null && home.isNotEmpty) {
      _homeDir = home;
      return;
    }
    () async {
      try {
        final fetched = await actions.apiGetMachineById(widget.machineId);
        final h = mutils.getMachineHomeDir(fetched);
        if (h != null && h.isNotEmpty && mounted) {
          safeSetState(() => _homeDir = h);
        }
      } catch (_) {}
    }();
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  Future<void> _refresh() => _model.load(widget.machineId, widget.cwd);

  Future<void> _openDetail(WorktreeInfo wt) async {
    HapticFeedback.lightImpact();
    final removed = await showWorktreeDetailSheet(
      context: context,
      machineId: widget.machineId,
      repoCwd: widget.cwd,
      worktree: wt,
      homeDir: _homeDir,
    );
    // Snack only once the sheet has actually closed and the removal completed,
    // so it never appears over the still-open detail sheet.
    if (removed == true) {
      _model.removeFromList(wt.path);
      if (mounted) {
        await SessionActions.showSnack(
            context, AppLocalizations.of(context).worktreesWorktreeRemoved);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Scaffold(
      key: scaffoldKey,
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
        centerTitle: true,
        toolbarHeight: 72.0,
        leading: Align(
          alignment: const AlignmentDirectional(1.0, 0.0),
          child: FlutterFlowIconButton(
            borderColor: Colors.transparent,
            borderRadius: 10.0,
            buttonSize: 40.0,
            fillColor: theme.primaryBackground,
            icon: Icon(Icons.chevron_left_rounded,
                color: theme.secondaryText, size: 24.0),
            onPressed: () async {
              HapticFeedback.lightImpact();
              context.safePop();
            },
          ),
        ),
        title: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              AppLocalizations.of(context).worktreesTitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: theme.titleLarge.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
              ),
            ),
            if (widget.projectName != null &&
                widget.projectName!.isNotEmpty) ...[
              const SizedBox(height: 3.0),
              Text(
                widget.projectName!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: theme.labelSmall.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.secondaryText,
                  fontSize: 12.0,
                  letterSpacing: 0.0,
                ),
              ),
            ],
          ],
        ),
        elevation: 0.0,
      ),
      body: SafeArea(bottom: false, child: _buildBody(theme)),
    );
  }

  Widget _buildBody(FlutterFlowTheme theme) {
    final l10n = AppLocalizations.of(context);
    if (_model.isLoading && _model.worktrees.isEmpty) {
      return Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
        ),
      );
    }
    if (_model.error == 'not_a_repo') {
      return _MessageState(
        icon: Icons.folder_off_outlined,
        title: l10n.worktreesNotAGitRepo,
        subtitle: l10n.worktreesNotAGitRepoSubtitle,
        onRetry: _refresh,
      );
    }
    if (_model.error != null) {
      return _MessageState(
        icon: Icons.error_outline_rounded,
        title: l10n.worktreesCouldNotLoad,
        subtitle: l10n.worktreesPullToRefresh,
        onRetry: _refresh,
      );
    }
    if (_model.worktrees.isEmpty) {
      return _MessageState(
        icon: FontAwesomeIcons.codeBranch,
        title: l10n.worktreesNoWorktreesYet,
        subtitle: l10n.worktreesNoWorktreesSubtitle,
        onRetry: _refresh,
      );
    }
    return RefreshIndicator(
      color: theme.primary,
      onRefresh: _refresh,
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.only(top: 8.0, bottom: 32.0),
        itemCount: _model.worktrees.length,
        itemBuilder: (context, index) {
          final wt = _model.worktrees[index];
          return _WorktreeCard(
            worktree: wt,
            displayPath: relativizeHome(wt.path, _homeDir),
            inUse: worktreeHasActiveSession(
                wt.path, FFAppState().cachedAgentInstances,
                homeDir: _homeDir),
            onTap: () => _openDetail(wt),
          );
        },
      ),
    );
  }
}

/// One worktree row, styled like `MachineCard`. Trailing indicator encodes
/// delete-safety: a live dot (a session runs here), a lock (external, not
/// removable), or a trash glyph (vicoa-managed → removable from the sheet).
class _WorktreeCard extends StatelessWidget {
  const _WorktreeCard({
    required this.worktree,
    required this.displayPath,
    required this.inUse,
    required this.onTap,
  });

  final WorktreeInfo worktree;
  final String displayPath;
  final bool inUse;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final branch = worktree.branch.isNotEmpty
        ? worktree.branch
        : AppLocalizations.of(context).worktreesDetached;
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 6.0, 16.0, 6.0),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          onTap: onTap,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(18.0),
            decoration: BoxDecoration(
              color: theme.primaryBackground,
              borderRadius: BorderRadius.circular(16.0),
              border: Border.all(color: theme.alternate, width: 1.0),
            ),
            child: Row(
              children: [
                SizedBox(
                  width: 22.0,
                  height: 22.0,
                  child: Center(
                    child: FaIcon(FontAwesomeIcons.codeBranch,
                        color: theme.secondaryText, size: 16.0),
                  ),
                ),
                const SizedBox(width: 14.0),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        branch,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.bodyLarge.override(
                          font: GoogleFonts.firaCode(),
                          color: theme.primaryText,
                          fontSize: 15.0,
                          letterSpacing: 0.0,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 4.0),
                      Text(
                        displayPath,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.labelSmall.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText,
                          fontSize: 12.0,
                          letterSpacing: 0.0,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10.0),
                _StatusIndicator(managed: worktree.managed, inUse: inUse),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusIndicator extends StatelessWidget {
  const _StatusIndicator({required this.managed, required this.inUse});
  final bool managed;
  final bool inUse;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    if (inUse) {
      return Icon(Icons.fiber_manual_record,
          color: theme.success, size: 12.0);
    }
    if (!managed) {
      return Icon(Icons.lock_outline_rounded,
          color: theme.secondaryText, size: 20.0);
    }
    return Icon(Icons.delete_outline_rounded,
        color: theme.secondaryText, size: 20.0);
  }
}

class _MessageState extends StatelessWidget {
  const _MessageState({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onRetry,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return RefreshIndicator(
      color: theme.primary,
      onRefresh: onRetry,
      child: LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Padding(
              padding: const EdgeInsets.all(32.0),
              child: Align(
                alignment: const Alignment(0.0, -0.35),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(icon, size: 56.0, color: theme.secondaryText),
                    const SizedBox(height: 16.0),
                    Text(
                      title,
                      textAlign: TextAlign.center,
                      style: theme.titleMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        letterSpacing: 0.0,
                      ),
                    ),
                    const SizedBox(height: 8.0),
                    Text(
                      subtitle,
                      textAlign: TextAlign.center,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.secondaryText,
                        letterSpacing: 0.0,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
