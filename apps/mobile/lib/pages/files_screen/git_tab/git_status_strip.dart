// Pinned top strip for the Git tab: branch / ahead / behind on the left,
// toolbar icons (refresh, wrap, collapse-all, hide-whitespace) on the right.
// See `plans/todos/vicoa-app-git-tab.md` §Phase C Sticky branch strip.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/git_tab_model.dart';
import '/custom_code/actions/rpc_git.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

class GitStatusStrip extends StatelessWidget {
  const GitStatusStrip({
    super.key,
    required this.model,
    required this.onRefresh,
  });

  final GitTabModel model;
  final VoidCallback onRefresh;

  static const double kHeight = 44;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final status = model.status;
    return Container(
      height: kHeight,
      color: theme.secondaryBackground,
      padding: const EdgeInsetsDirectional.fromSTEB(16, 0, 8, 0),
      child: Row(
        children: [
          FaIcon(
            FontAwesomeIcons.codeBranch,
            size: 13,
            color: theme.secondaryText,
          ),
          const SizedBox(width: 8),
          Expanded(child: _branchLabel(context, theme, status)),
          _iconButton(
            theme,
            icon: Icons.refresh_rounded,
            tooltip: l10n.filesGitXRefreshTooltip,
            enabled: !model.offline,
            onTap: onRefresh,
          ),
          _iconButton(
            theme,
            icon: model.wrapLines
                ? Icons.wrap_text_rounded
                : Icons.subject_rounded,
            tooltip: l10n.filesGitXWordWrapTooltip,
            onTap: model.toggleWrapLines,
          ),
          _iconButton(
            theme,
            icon: model.allCollapsed
                ? Icons.unfold_more_rounded
                : Icons.unfold_less_rounded,
            tooltip: model.allCollapsed
                ? l10n.filesGitXExpandAllTooltip
                : l10n.filesGitXCollapseAllTooltip,
            onTap: model.toggleExpandAll,
          ),
          _iconButton(
            theme,
            icon: model.hideWhitespace
                ? Icons.format_clear_rounded
                : Icons.space_bar_rounded,
            tooltip: model.hideWhitespace
                ? l10n.filesGitXShowWhitespaceTooltip
                : l10n.filesGitXHideWhitespaceTooltip,
            onTap: () {
              // Fire-and-forget — the model notifies as diffs come back.
              model.toggleHideWhitespace();
            },
          ),
        ],
      ),
    );
  }

  Widget _branchLabel(
      BuildContext context, FlutterFlowTheme theme, GitStatusResult? status) {
    final l10n = AppLocalizations.of(context);
    if (status == null) {
      return Text(
        '…',
        style: theme.bodySmall.override(
          font: GoogleFonts.sourceSans3(),
          color: theme.secondaryText,
          letterSpacing: 0.0,
        ),
      );
    }
    final spans = <InlineSpan>[];
    spans.add(TextSpan(
      text: status.detachedHead
          ? l10n.filesGitXDetachedAt(status.branch)
          : status.branch,
      style: TextStyle(
        color: theme.primaryText,
        fontWeight: FontWeight.w600,
      ),
    ));
    if (status.upstream == null && !status.detachedHead) {
      spans.add(TextSpan(
        text: l10n.filesGitXNoUpstream,
        style: TextStyle(color: theme.secondaryText),
      ));
    } else {
      if (status.ahead > 0) {
        spans.add(TextSpan(
          text: '  ·  ${status.ahead} ↑',
          style: TextStyle(color: theme.secondaryText),
        ));
      }
      if (status.behind > 0) {
        spans.add(TextSpan(
          text: '  ·  ${status.behind} ↓',
          style: TextStyle(color: theme.secondaryText),
        ));
      }
    }
    return RichText(
      overflow: TextOverflow.ellipsis,
      text: TextSpan(
        style: theme.bodySmall.override(
          font: GoogleFonts.sourceSans3(),
          letterSpacing: 0.0,
        ),
        children: spans,
      ),
    );
  }

  Widget _iconButton(
    FlutterFlowTheme theme, {
    required IconData icon,
    required String tooltip,
    required VoidCallback onTap,
    bool enabled = true,
  }) {
    return Opacity(
      opacity: enabled ? 1.0 : 0.4,
      child: IconButton(
        icon: Icon(icon, size: 20, color: theme.secondaryText),
        tooltip: tooltip,
        onPressed: enabled
            ? () {
                HapticFeedback.lightImpact();
                onTap();
              }
            : null,
        constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
        padding: EdgeInsets.zero,
        splashRadius: 20,
      ),
    );
  }
}

/// Sliver wrapper that pins [GitStatusStrip] at the top of the scroll view.
class GitStatusStripSliver extends StatelessWidget {
  const GitStatusStripSliver({
    super.key,
    required this.model,
    required this.onRefresh,
  });
  final GitTabModel model;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return SliverPersistentHeader(
      pinned: true,
      delegate: _StripDelegate(model: model, onRefresh: onRefresh),
    );
  }
}

class _StripDelegate extends SliverPersistentHeaderDelegate {
  _StripDelegate({required this.model, required this.onRefresh});
  final GitTabModel model;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return GitStatusStrip(model: model, onRefresh: onRefresh);
  }

  @override
  double get maxExtent => GitStatusStrip.kHeight;
  @override
  double get minExtent => GitStatusStrip.kHeight;

  @override
  // The delegate is recreated on every parent rebuild, but `model` is the same
  // singleton instance — so an identity check would always say "no change" and
  // the pinned strip would keep showing stale toggle icons. The parent only
  // rebuilds when the model notifies, so always rebuilding is correct (and
  // cheap — it's a single 44px row).
  bool shouldRebuild(_StripDelegate oldDelegate) => true;
}
