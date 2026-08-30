// Per-file slivers for the Git tab.
//
// Body is lazy-built (`SliverList.builder`) and truncated to `previewRows`
// rows by default; tap "Show more" to expand the file via
// `GitTabModel.showFullBody`. The header pins inside its enclosing
// `SliverMainAxisGroup` so only ONE file header pins at a time — see
// `git_tab_view.dart` for the wiring. The pinned-vs-flowing transition
// is reflected in the header's background: when it's pinned over scrolling
// content, the row reads as a primary card; when it's just at its natural
// position in the scroll flow, it blends into the overall surface.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/atom-one-dark.dart';
import 'package:flutter_highlight/themes/atom-one-light.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/git_tab_model.dart';
import '/custom_code/actions/rpc_git.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

const double _kHeaderHeight = 40;

// ----------------------------------------------------------------- sliver header

/// Pinned-while-its-group-is-visible sliver. Wrap with `SliverMainAxisGroup`
/// in the caller so the pin scope ends with the body — only one file header
/// is pinned at any time.
class DiffFileHeaderSliver extends StatelessWidget {
  const DiffFileHeaderSliver({
    super.key,
    required this.theme,
    required this.entry,
    required this.staged,
    required this.collapsed,
    required this.onTap,
    this.headerKey,
  });

  final FlutterFlowTheme theme;
  final GitFileEntry entry;
  final bool staged;
  final bool collapsed;
  final VoidCallback onTap;
  /// Optional GlobalKey attached to the rendered header row. Lets a caller
  /// (`GitTabView`) measure the row's viewport y-position before and after
  /// a toggle so the scroll can be anchored to keep it in place.
  final Key? headerKey;

  @override
  Widget build(BuildContext context) {
    return SliverPersistentHeader(
      pinned: true,
      delegate: _HeaderDelegate(
        theme: theme,
        entry: entry,
        collapsed: collapsed,
        onTap: onTap,
        headerKey: headerKey,
      ),
    );
  }
}

class _HeaderDelegate extends SliverPersistentHeaderDelegate {
  _HeaderDelegate({
    required this.theme,
    required this.entry,
    required this.collapsed,
    required this.onTap,
    this.headerKey,
  });
  final FlutterFlowTheme theme;
  final GitFileEntry entry;
  final bool collapsed;
  final VoidCallback onTap;
  final Key? headerKey;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return DiffFileHeaderRow(
      key: headerKey,
      theme: theme,
      entry: entry,
      collapsed: collapsed,
      sticky: overlapsContent,
      onTap: onTap,
    );
  }

  @override
  double get maxExtent => _kHeaderHeight;
  @override
  double get minExtent => _kHeaderHeight;

  @override
  bool shouldRebuild(_HeaderDelegate old) =>
      old.collapsed != collapsed ||
      old.entry.contentHash != entry.contentHash ||
      old.entry.additions != entry.additions ||
      old.entry.deletions != entry.deletions ||
      old.entry.oldPath != entry.oldPath;
}

class DiffFileHeaderRow extends StatelessWidget {
  const DiffFileHeaderRow({
    super.key,
    required this.theme,
    required this.entry,
    required this.collapsed,
    required this.sticky,
    required this.onTap,
  });
  final FlutterFlowTheme theme;
  final GitFileEntry entry;
  final bool collapsed;
  // True when the row is currently pinned over scrolling content. Used to
  // pick the background and the divider treatment.
  final bool sticky;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final parts = entry.path.split('/');
    final fileName = parts.last;
    final dirSegment = parts.length > 1
        ? '${parts.sublist(0, parts.length - 1).join('/')}/'
        : '';
    final renameSegment =
        entry.oldPath != null ? '  ← ${entry.oldPath}' : '';

    return Material(
      // Sticky rows surface as a primaryBackground card so the eye locks on
      // them; non-sticky rows blend with the overall scroll surface.
      color: sticky ? theme.primaryBackground : theme.secondaryBackground,
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        child: Container(
          height: _kHeaderHeight,
          padding: const EdgeInsetsDirectional.fromSTEB(12, 0, 12, 0),
          decoration: BoxDecoration(
            border: sticky
                ? Border(
                    top: BorderSide(color: theme.alternate, width: 0.5),
                    bottom: BorderSide(color: theme.alternate, width: 0.5),
                  )
                : null,
          ),
          child: Row(
            children: [
              AnimatedRotation(
                turns: collapsed ? -0.25 : 0,
                duration: const Duration(milliseconds: 150),
                child: Icon(
                  Icons.expand_more_rounded,
                  size: 20,
                  color: theme.secondaryText,
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: RichText(
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  text: TextSpan(
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      letterSpacing: 0.0,
                    ),
                    children: [
                      TextSpan(
                        text: fileName,
                        style: TextStyle(
                          color: theme.primaryText,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (dirSegment.isNotEmpty || renameSegment.isNotEmpty)
                        TextSpan(
                          text: '  $dirSegment$renameSegment',
                          style: TextStyle(color: theme.secondaryText),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _statBadge(theme, entry),
            ],
          ),
        ),
      ),
    );
  }

  Widget _statBadge(FlutterFlowTheme theme, GitFileEntry e) {
    if (e.additions == 0 && e.deletions == 0) return const SizedBox.shrink();
    return RichText(
      text: TextSpan(
        style: GoogleFonts.jetBrainsMono(
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
        children: [
          if (e.additions > 0)
            TextSpan(
              text: '+${e.additions}',
              style: TextStyle(color: theme.success),
            ),
          // Thin space (U+2009) — narrower than a regular ' ' but still
          // visible. Keeps `+12 −3` from fusing into `+12−3`.
          if (e.additions > 0 && e.deletions > 0)
            const TextSpan(text: ' '),
          if (e.deletions > 0)
            TextSpan(
              text: '−${e.deletions}',
              style: TextStyle(color: theme.error),
            ),
        ],
      ),
    );
  }
}

// --- body slivers -----------------------------------------------------------

sealed class _BodyRow {
  const _BodyRow();
}

class _HunkHeaderData extends _BodyRow {
  const _HunkHeaderData(this.header);
  final String header;
}

class _LineData extends _BodyRow {
  const _LineData({
    required this.type,
    required this.content,
    required this.gutter,
  });
  final String type;
  final String content;
  final int? gutter;
}

class _BinaryData extends _BodyRow {
  const _BinaryData(this.size);
  final int size;
}

class _ErrorData extends _BodyRow {
  const _ErrorData(this.code);
  final String code;
}

class _SkeletonData extends _BodyRow {
  const _SkeletonData();
}

class _TruncatedBannerData extends _BodyRow {
  const _TruncatedBannerData();
}

class _ShowMoreData extends _BodyRow {
  const _ShowMoreData(this.hidden);
  final int hidden;
}

List<_BodyRow> _rowsForDiff(DiffEntry diff) {
  if (diff.loading && diff.payload == null) {
    return const [_SkeletonData(), _SkeletonData(), _SkeletonData()];
  }
  if (diff.error != null) {
    return [_ErrorData(diff.error!)];
  }
  final payload = diff.payload;
  if (payload == null) return const [];
  if (payload.isBinary) return [_BinaryData(payload.size)];

  final rows = <_BodyRow>[];
  for (final hunk in payload.hunks) {
    rows.add(_HunkHeaderData(hunk.header));
    var oldLine = hunk.oldStart;
    var newLine = hunk.newStart;
    for (final line in hunk.lines) {
      final int? gutter;
      switch (line.type) {
        case 'add':
          gutter = newLine;
          newLine += 1;
        case 'remove':
          gutter = oldLine;
          oldLine += 1;
        default:
          gutter = newLine;
          oldLine += 1;
          newLine += 1;
      }
      rows.add(_LineData(type: line.type, content: line.content, gutter: gutter));
    }
  }
  if (payload.truncated) rows.add(const _TruncatedBannerData());
  return rows;
}

/// `previewRows`: maximum typed rows to render before showing the
/// "Show N more lines" affordance. 0 = no cap (show everything inline).
///
/// Layout branches on `wrapLines`:
/// * wrapLines=true → `SliverList.builder` (lazy). Lines wrap naturally
///   inside the available width; each row builds only when scrolled into
///   view.
/// * wrapLines=false → split into two groups so the chrome stays visible
///   in the viewport even when the diff is wider than the screen:
///     - Diff content rows (`_HunkHeaderData` / `_LineData`) go inside a
///       single `SingleChildScrollView(horizontal) → IntrinsicWidth →
///       Column`; they all pan left/right together.
///     - Status / footer rows (skeleton, error, binary, truncated banner,
///       "Show N more") are siblings *outside* the horizontal scroll, so
///       their centred Row layouts centre in the viewport — not in a
///       2000-px-wide diff column where the text would end up off-screen.
Widget buildDiffFileBody({
  required FlutterFlowTheme theme,
  required DiffEntry diff,
  required bool wrapLines,
  required bool bodyFullyShown,
  required int previewRows,
  required String language,
  required Map<String, TextStyle> syntaxTheme,
  required VoidCallback onShowMore,
}) {
  final rows = _rowsForDiff(diff);
  final List<_BodyRow> visible;
  if (!bodyFullyShown && previewRows > 0 && rows.length > previewRows) {
    visible = [
      ...rows.take(previewRows),
      _ShowMoreData(rows.length - previewRows),
    ];
  } else {
    visible = rows;
  }
  if (wrapLines) {
    return SliverList.builder(
      itemCount: visible.length,
      itemBuilder: (context, i) => _buildRowWidget(
        visible[i],
        theme,
        true,
        language,
        syntaxTheme,
        onShowMore,
      ),
    );
  }
  final scrollableRows = <_BodyRow>[];
  final fixedRows = <_BodyRow>[];
  for (final row in visible) {
    if (row is _HunkHeaderData || row is _LineData) {
      scrollableRows.add(row);
    } else {
      fixedRows.add(row);
    }
  }
  final children = <Widget>[
    if (scrollableRows.isNotEmpty)
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: IntrinsicWidth(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final row in scrollableRows)
                _buildRowWidget(
                  row,
                  theme,
                  false,
                  language,
                  syntaxTheme,
                  onShowMore,
                ),
            ],
          ),
        ),
      ),
    for (final row in fixedRows)
      _buildRowWidget(row, theme, false, language, syntaxTheme, onShowMore),
  ];
  return SliverList(delegate: SliverChildListDelegate.fixed(children));
}

Widget _buildRowWidget(
  _BodyRow row,
  FlutterFlowTheme theme,
  bool wrapLines,
  String language,
  Map<String, TextStyle> syntaxTheme,
  VoidCallback onShowMore,
) {
  switch (row) {
    case _HunkHeaderData(:final header):
      return _HunkHeaderRow(theme: theme, header: header);
    case _LineData(:final type, :final content, :final gutter):
      return DiffLineRow(
        theme: theme,
        type: type,
        content: content,
        gutter: gutter,
        wrapLines: wrapLines,
        language: language,
        syntaxTheme: syntaxTheme,
      );
    case _BinaryData(:final size):
      return _BinaryCard(theme: theme, size: size);
    case _ErrorData(:final code):
      return _ErrorCard(theme: theme, code: code);
    case _SkeletonData():
      return _SkeletonRow(theme: theme);
    case _TruncatedBannerData():
      return _TruncatedBanner(theme: theme);
    case _ShowMoreData(:final hidden):
      return _ShowMoreRow(theme: theme, hidden: hidden, onTap: onShowMore);
  }
}

// flutter_highlight bakes a 'root' background into every theme. For diff
// rows we want the row's container to own the background colour (so adds /
// removes get their tints), so strip the root bg + root colour and pin the
// font to JetBrainsMono. Caller computes this once per file body.
Map<String, TextStyle> buildDiffSyntaxTheme({
  required bool isDark,
  required FlutterFlowTheme theme,
}) {
  final base = isDark ? atomOneDarkTheme : atomOneLightTheme;
  final tuned = Map<String, TextStyle>.from(base);
  tuned['root'] = (base['root'] ?? const TextStyle()).copyWith(
    backgroundColor: Colors.transparent,
    color: theme.primaryText,
  );
  return tuned;
}

String detectLangFromPath(String path) {
  final lower = path.toLowerCase();
  if (lower.endsWith('.dart')) return 'dart';
  if (lower.endsWith('.py')) return 'python';
  if (lower.endsWith('.js') || lower.endsWith('.jsx')) return 'javascript';
  if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return 'typescript';
  if (lower.endsWith('.go')) return 'go';
  if (lower.endsWith('.rs')) return 'rust';
  if (lower.endsWith('.rb')) return 'ruby';
  if (lower.endsWith('.java')) return 'java';
  if (lower.endsWith('.kt')) return 'kotlin';
  if (lower.endsWith('.swift')) return 'swift';
  if (lower.endsWith('.c') || lower.endsWith('.h')) return 'c';
  if (lower.endsWith('.cc') ||
      lower.endsWith('.cpp') ||
      lower.endsWith('.hpp')) {
    return 'cpp';
  }
  if (lower.endsWith('.cs')) return 'csharp';
  if (lower.endsWith('.sh') ||
      lower.endsWith('.zsh') ||
      lower.endsWith('.bash')) {
    return 'bash';
  }
  if (lower.endsWith('.json')) return 'json';
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'yaml';
  if (lower.endsWith('.toml')) return 'ini';
  if (lower.endsWith('.html')) return 'xml';
  if (lower.endsWith('.svg') || lower.endsWith('.xml')) return 'xml';
  if (lower.endsWith('.md') ||
      lower.endsWith('.markdown') ||
      lower.endsWith('.mdx')) {
    return 'markdown';
  }
  if (lower.endsWith('.css')) return 'css';
  if (lower.endsWith('.scss') || lower.endsWith('.sass')) return 'scss';
  if (lower.endsWith('.sql')) return 'sql';
  return 'plaintext';
}

class DiffLineRow extends StatelessWidget {
  const DiffLineRow({
    super.key,
    required this.theme,
    required this.type,
    required this.content,
    required this.gutter,
    required this.wrapLines,
    required this.language,
    required this.syntaxTheme,
  });
  final FlutterFlowTheme theme;
  final String type;
  final String content;
  final int? gutter;
  final bool wrapLines;
  final String language;
  final Map<String, TextStyle> syntaxTheme;

  @override
  Widget build(BuildContext context) {
    final Color? bg;
    switch (type) {
      case 'add':
        bg = theme.diffAddedBackground;
      case 'remove':
        bg = theme.diffDeletedBackground;
      default:
        bg = null;
    }
    final monospace = GoogleFonts.jetBrainsMono(
      fontSize: 13,
      height: 1.4,
      color: theme.primaryText,
    );
    final Widget contentWidget = content.isEmpty
        ? Text(' ', style: monospace)
        : HighlightView(
            content,
            language: language,
            theme: syntaxTheme,
            padding: EdgeInsets.zero,
            textStyle: monospace,
          );
    return Container(
      color: bg,
      padding: const EdgeInsetsDirectional.fromSTEB(0, 1, 12, 1),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 44,
            child: Text(
              gutter?.toString() ?? '',
              textAlign: TextAlign.right,
              style: GoogleFonts.jetBrainsMono(
                color: theme.secondaryText.withValues(alpha: 0.6),
                fontSize: 11,
              ),
            ),
          ),
          const SizedBox(width: 8),
          // wrapLines=true: Expanded forces a finite cross-axis width so the
          //   highlighted text wraps within the viewport.
          // wrapLines=false: NO Expanded — the row gets its intrinsic width
          //   and an outer SingleChildScrollView(horizontal) (set up in
          //   `buildDiffFileBody`) pans the entire block left/right.
          if (wrapLines) Expanded(child: contentWidget) else contentWidget,
        ],
      ),
    );
  }
}

class _HunkHeaderRow extends StatelessWidget {
  const _HunkHeaderRow({required this.theme, required this.header});
  final FlutterFlowTheme theme;
  final String header;

  @override
  Widget build(BuildContext context) {
    // Render the whole `@@ -10,7 +10,8 @@ function context` line in the
    // muted base style — no per-token coloring, no italic function context.
    return Container(
      color: theme.secondaryText.withValues(alpha: 0.08),
      padding: const EdgeInsetsDirectional.fromSTEB(16, 6, 16, 6),
      child: Text(
        header,
        style: GoogleFonts.jetBrainsMono(
          color: theme.secondaryText,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}

class _SkeletonRow extends StatelessWidget {
  const _SkeletonRow({required this.theme});
  final FlutterFlowTheme theme;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 18,
      margin: const EdgeInsetsDirectional.fromSTEB(64, 4, 16, 4),
      decoration: BoxDecoration(
        color: theme.secondaryText.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(4),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.theme, required this.code});
  final FlutterFlowTheme theme;
  final String code;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Text(
        AppLocalizations.of(context).filesGitXCouldntLoadDiff(code),
        style: theme.bodySmall.override(
          font: GoogleFonts.sourceSans3(),
          color: theme.error,
          letterSpacing: 0.0,
        ),
      ),
    );
  }
}

class _BinaryCard extends StatelessWidget {
  const _BinaryCard({required this.theme, required this.size});
  final FlutterFlowTheme theme;
  final int size;

  String _formatBytes(int n) {
    if (n < 1024) return '$n B';
    if (n < 1024 * 1024) return '${(n / 1024).toStringAsFixed(1)} KB';
    return '${(n / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.insert_drive_file_outlined,
            size: 18,
            color: theme.secondaryText,
          ),
          const SizedBox(width: 8),
          Text(
            AppLocalizations.of(context).filesGitXBinaryFileChanged(_formatBytes(size)),
            style: theme.bodySmall.override(
              font: GoogleFonts.sourceSans3(),
              color: theme.secondaryText,
              letterSpacing: 0.0,
            ),
          ),
        ],
      ),
    );
  }
}

class _TruncatedBanner extends StatelessWidget {
  const _TruncatedBanner({required this.theme});
  final FlutterFlowTheme theme;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: theme.warning.withValues(alpha: 0.12),
      padding: const EdgeInsetsDirectional.fromSTEB(16, 10, 16, 10),
      child: Text(
        AppLocalizations.of(context).filesGitXDiffTruncated,
        style: theme.bodySmall.override(
          font: GoogleFonts.sourceSans3(),
          color: theme.warning,
          letterSpacing: 0.0,
        ),
      ),
    );
  }
}

class _ShowMoreRow extends StatelessWidget {
  const _ShowMoreRow({
    required this.theme,
    required this.hidden,
    required this.onTap,
  });
  final FlutterFlowTheme theme;
  final int hidden;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: theme.secondaryText.withValues(alpha: 0.04),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16, 10, 16, 10),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                AppLocalizations.of(context).filesGitXShowMoreLines(hidden),
                style: theme.bodySmall.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.secondaryText,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.0,
                ),
              ),
              const SizedBox(width: 6),
              Icon(
                Icons.unfold_more_rounded,
                size: 16,
                color: theme.secondaryText,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
