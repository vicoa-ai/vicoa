// CustomScrollView host for the Git tab. See
// `plans/todos/vicoa-app-git-tab.md` §Phase C Render.
//
// Layout: pinned strip → for each non-empty section (Staged → Unstaged →
// Untracked): scroll-away divider, then for each file in that section a
// pinned filename header and (unless collapsed) the typed-line body sliver.

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/git_tab_model.dart';
import '/custom_code/actions/rpc_git.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'diff_file_sliver.dart';
import 'git_status_strip.dart';

// Max rows of any single file's diff to render before showing "Show N more
// lines." Vicoa-defined (no longer reads the Appearance code-collapse
// setting); 50 keeps most files visible in full while still gating very
// large diffs behind a tap.
const int _kBodyPreviewRows = 50;

class GitTabView extends StatefulWidget {
  const GitTabView({super.key, required this.model});
  final GitTabModel model;

  @override
  State<GitTabView> createState() => _GitTabViewState();
}

class _GitTabViewState extends State<GitTabView> {
  // Shared ScrollController so we can measure & adjust the scroll position
  // when the user toggles a file (scroll anchoring — see _onFileHeaderTap).
  final ScrollController _scrollController = ScrollController();
  // Per-file GlobalKey on the header row so we can locate it after a
  // toggle-triggered rebuild and read its new viewport y.
  final Map<String, GlobalKey> _headerKeys = {};

  GlobalKey _keyForFile(String path, bool staged) {
    final id = '$path|${staged ? 's' : 'u'}';
    return _headerKeys.putIfAbsent(
      id,
      () => GlobalKey(debugLabel: 'git-hdr-$id'),
    );
  }

  void _rebuild() {
    if (mounted) setState(() {});
  }

  @override
  void initState() {
    super.initState();
    widget.model.addListener(_rebuild);
  }

  @override
  void didUpdateWidget(GitTabView old) {
    super.didUpdateWidget(old);
    if (old.model != widget.model) {
      old.model.removeListener(_rebuild);
      widget.model.addListener(_rebuild);
    }
  }

  @override
  void dispose() {
    widget.model.removeListener(_rebuild);
    _scrollController.dispose();
    super.dispose();
  }

  /// Capture the tapped file header's viewport y, toggle, then after the
  /// rebuild scroll so the header lands at the same y — keeps the user
  /// pinned to the file they were looking at instead of letting the
  /// content above/below jump out from under them.
  void _onFileHeaderTap(String path, bool staged) {
    final beforeY = _measureHeaderY(path, staged);
    widget.model.toggleFile(path, staged: staged);
    if (beforeY == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final afterY = _measureHeaderY(path, staged);
      if (afterY == null) return;
      final delta = afterY - beforeY;
      // < 1px = layout didn't really move, don't bother nudging.
      if (delta.abs() < 1) return;
      if (!_scrollController.hasClients) return;
      final pos = _scrollController.position;
      final target = (_scrollController.offset + delta)
          .clamp(pos.minScrollExtent, pos.maxScrollExtent);
      _scrollController.jumpTo(target);
    });
  }

  double? _measureHeaderY(String path, bool staged) {
    final ctx = _keyForFile(path, staged).currentContext;
    if (ctx == null) return null;
    final rb = ctx.findRenderObject() as RenderBox?;
    if (rb == null || !rb.attached) return null;
    return rb.localToGlobal(Offset.zero).dy;
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final model = widget.model;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    // flutter_highlight theme is computed once per build and shared across
    // every DiffLineRow — building a HighlightView per line is fine, but
    // re-materialising the theme map for each one isn't.
    final syntaxTheme = buildDiffSyntaxTheme(isDark: isDark, theme: theme);

    final body = _maybeEmptyBody(context, theme, model);
    if (body != null) {
      return Column(
        children: [
          GitStatusStrip(model: model, onRefresh: model.refresh),
          Expanded(child: body),
        ],
      );
    }

    final slivers = <Widget>[
      GitStatusStripSliver(model: model, onRefresh: model.refresh),
      ..._sliversForStatus(context, theme, model, _kBodyPreviewRows, syntaxTheme),
      const SliverToBoxAdapter(child: SizedBox(height: 32)),
    ];

    return RefreshIndicator(
      onRefresh: model.refresh,
      child: CustomScrollView(
        controller: _scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: slivers,
      ),
    );
  }

  Widget? _maybeEmptyBody(
      BuildContext context, FlutterFlowTheme theme, GitTabModel model) {
    final l10n = AppLocalizations.of(context);
    final status = model.status;
    if (status == null) {
      if (model.statusError != null) {
        return _StatusErrorBody(theme: theme, code: model.statusError!);
      }
      // No cached status + machine unreachable: don't spin forever, mirror
      // the file_viewer "not downloaded on this device" surface so the
      // user understands they need to reconnect.
      if (model.offline) {
        return _MissingContentBody(
          theme: theme,
          icon: Icons.cloud_off_outlined,
          title: l10n.filesGitXStatusNotLoaded,
          subtitle: l10n.filesGitXReconnectToSeeChanges,
        );
      }
      return const Center(child: CircularProgressIndicator());
    }
    if (status.isClean) {
      return _EmptyBody(
        theme: theme,
        title: l10n.filesGitXWorkingTreeClean,
        subtitle: l10n.filesGitXNoChangesVsHead,
      );
    }
    return null;
  }

  List<Widget> _sliversForStatus(
    BuildContext context,
    FlutterFlowTheme theme,
    GitTabModel model,
    int previewRows,
    Map<String, TextStyle> syntaxTheme,
  ) {
    final l10n = AppLocalizations.of(context);
    final status = model.status!;
    final slivers = <Widget>[];

    void addSection(String label, List<GitFileEntry> entries, bool staged) {
      if (entries.isEmpty) return;
      slivers.add(SliverToBoxAdapter(
        child: _SectionDivider(theme: theme, label: label, count: entries.length),
      ));
      for (final e in entries) {
        final isCollapsed = model.isCollapsed(e.path, staged: staged);
        // Each file is its own SliverMainAxisGroup — the pinned header
        // sticks only while this group is scrolling, then scrolls off with
        // the body (no stacking, no viewport eaten by many pinned headers).
        slivers.add(SliverMainAxisGroup(
          slivers: [
            DiffFileHeaderSliver(
              theme: theme,
              entry: e,
              staged: staged,
              collapsed: isCollapsed,
              onTap: () => _onFileHeaderTap(e.path, staged),
              headerKey: _keyForFile(e.path, staged),
            ),
            if (!isCollapsed)
              buildDiffFileBody(
                theme: theme,
                diff: model.diffFor(e.path, staged: staged) ??
                    DiffEntry(loading: true),
                wrapLines: model.wrapLines,
                bodyFullyShown: model.isBodyFullyShown(e.path, staged: staged),
                previewRows: previewRows,
                language: detectLangFromPath(e.path),
                syntaxTheme: syntaxTheme,
                onShowMore: () => model.showFullBody(e.path, staged: staged),
              ),
          ],
        ));
      }
    }

    addSection(l10n.filesGitXSectionStaged, status.staged, true);
    addSection(l10n.filesGitXSectionUnstaged, status.unstaged, false);
    addSection(l10n.filesGitXSectionUntracked, status.untracked, false);
    return slivers;
  }
}

class _SectionDivider extends StatelessWidget {
  const _SectionDivider({
    required this.theme,
    required this.label,
    required this.count,
  });
  final FlutterFlowTheme theme;
  final String label;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: theme.secondaryBackground,
      padding: const EdgeInsetsDirectional.fromSTEB(16, 16, 16, 8),
      child: Text(
        AppLocalizations.of(context).filesGitXSectionLabel(label, count),
        style: theme.labelMedium.override(
          font: GoogleFonts.sourceSans3(),
          color: theme.secondaryText,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.4,
        ),
      ),
    );
  }
}

class _EmptyBody extends StatelessWidget {
  const _EmptyBody({
    required this.theme,
    required this.title,
    required this.subtitle,
  });
  final FlutterFlowTheme theme;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              title,
              textAlign: TextAlign.center,
              style: theme.titleMedium.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: theme.bodySmall.override(
                font: GoogleFonts.sourceSans3(),
                color: theme.secondaryText,
                letterSpacing: 0.0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusErrorBody extends StatelessWidget {
  const _StatusErrorBody({required this.theme, required this.code});
  final FlutterFlowTheme theme;
  final String code;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final (title, subtitle) = switch (code) {
      'not_a_repo' => (
          l10n.filesGitXNotARepoTitle,
          l10n.filesGitXNotARepoSubtitle,
        ),
      _ => (l10n.filesGitXCouldntLoadStatus, code),
    };
    return _EmptyBody(theme: theme, title: title, subtitle: subtitle);
  }
}

/// "Missing content" empty state — mirrors `file_viewer_widget.dart`'s
/// "File not downloaded on this device." surface (icon ~42 px, bold title,
/// muted subtitle, slightly-above-centre alignment). Used for offline-with-
/// no-cache scenarios where there's nothing to render and a spinner would
/// just sit there forever.
class _MissingContentBody extends StatelessWidget {
  const _MissingContentBody({
    required this.theme,
    required this.icon,
    required this.title,
    required this.subtitle,
  });
  final FlutterFlowTheme theme;
  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: const Alignment(0.0, -0.3),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 42, color: theme.secondaryText),
            const SizedBox(height: 24),
            Text(
              title,
              textAlign: TextAlign.center,
              style: theme.titleMedium.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: theme.bodySmall.override(
                font: GoogleFonts.sourceSans3(),
                color: theme.secondaryText,
                letterSpacing: 0.0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
