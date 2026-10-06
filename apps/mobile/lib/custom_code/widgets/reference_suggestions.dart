import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/start_ellipsis_text.dart';
import '/custom_code/utils/composer_references.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/tasks/task_glyphs.dart';

/// The composer's `#` panel: the user's sessions, tasks and automations,
/// grouped under a heading wherever `kind` changes (the server returns them
/// kind-ordered). Same surface as [FileMentionSuggestions], so `@` and `#`
/// read as one feature.
class ReferenceSuggestions extends StatelessWidget {
  const ReferenceSuggestions({
    super.key,
    required this.mixin,
    this.margin = const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 12.0),
    this.onSelected,
  });

  final ComposerReferenceMixin mixin;
  final EdgeInsetsGeometry margin;
  final void Function(ReferenceCandidate)? onSelected;

  @override
  Widget build(BuildContext context) {
    if (!mixin.showReferenceSuggestions) return const SizedBox.shrink();

    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final items = mixin.referenceCandidates;

    return Container(
      constraints: const BoxConstraints(maxHeight: 240.0),
      margin: margin,
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: BorderRadius.circular(16.0),
        border: Border.all(
          color: theme.secondaryText.withValues(alpha: 0.15),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 8.0,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: items.isEmpty
          ? Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18.0, vertical: 14.0),
              child: Text(
                mixin.isLoadingReferences
                    ? l10n.chatInputReferencesSearching
                    : l10n.chatInputReferencesNoMatches,
                style: theme.bodySmall.override(
                  font: GoogleFonts.sourceSans3(),
                  fontSize: 14.0,
                  letterSpacing: 0.0,
                  color: theme.secondaryText,
                ),
              ),
            )
          : ListView.builder(
              shrinkWrap: true,
              padding: const EdgeInsets.symmetric(vertical: 4.0),
              itemCount: items.length,
              itemBuilder: (context, index) {
                final item = items[index];
                final startsGroup =
                    index == 0 || items[index - 1].kind != item.kind;
                final row = _ReferenceRow(
                  item: item,
                  onTap: () {
                    HapticFeedback.lightImpact();
                    mixin.insertReference(item);
                    onSelected?.call(item);
                  },
                );
                if (!startsGroup) return row;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [_groupHeader(theme, _groupLabel(l10n, item.kind)), row],
                );
              },
            ),
    );
  }

  String _groupLabel(AppLocalizations l10n, String kind) => switch (kind) {
        'task' => l10n.tabTasks,
        'automation' => l10n.tabAutomations,
        _ => l10n.searchSessions,
      };

  Widget _groupHeader(FlutterFlowTheme theme, String label) => Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(18.0, 10.0, 18.0, 2.0),
        child: Text(
          label,
          style: theme.bodySmall.override(
            font: GoogleFonts.sourceSans3(),
            fontSize: 13.0,
            letterSpacing: 0.0,
            fontWeight: FontWeight.w600,
            color: theme.secondaryText,
          ),
        ),
      );
}

/// "Sending files this session under X": shown above the composer while a
/// `#`-referenced task would link this session, because a send that writes to
/// the user's Tasks board shouldn't happen with nothing on screen saying so.
/// Listens to the text itself, so deleting the token hides it at once.
class ReferenceLinkHint extends StatelessWidget {
  const ReferenceLinkHint({
    super.key,
    required this.mixin,
    required this.currentTaskId,
    required this.message,
    this.padding = const EdgeInsets.only(bottom: 6.0),
  });

  final ComposerReferenceMixin mixin;

  /// The task the session already belongs to (a link never re-files it).
  final String? Function() currentTaskId;
  final String Function(String label) message;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<TextEditingValue>(
      valueListenable: mixin.referenceTextController,
      builder: (context, value, _) {
        final link = mixin.pendingTaskLink(value.text, currentTaskId());
        if (link == null) return const SizedBox.shrink();
        final theme = FlutterFlowTheme.of(context);
        return Padding(
          padding: padding,
          child: Row(
            children: [
              Icon(Icons.link_rounded, size: 14.0, color: theme.secondaryText),
              const SizedBox(width: 6.0),
              Expanded(
                child: Text(
                  message(link.label),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 13.0, letterSpacing: 0.0, color: theme.secondaryText),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// One line per row, like the web panel: glyph, title, then where the thing
/// lives (project icon + name, else its folder ellipsized from the front) and
/// a task's `#KEY`.
class _ReferenceRow extends StatelessWidget {
  const _ReferenceRow({required this.item, required this.onTap});

  final ReferenceCandidate item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final metaStyle = theme.bodySmall.override(
      font: GoogleFonts.sourceSans3(),
      fontSize: 13.0,
      letterSpacing: 0.0,
      color: theme.secondaryText,
    );
    final meta = item.meta?.trim() ?? '';
    final identifier = item.identifier?.trim() ?? '';

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18.0, vertical: 11.0),
          child: LayoutBuilder(
            builder: (context, constraints) => Row(
              children: [
                SizedBox(
                  width: 20.0,
                  child: Center(child: _leading(theme)),
                ),
                const SizedBox(width: 10.0),
                Expanded(
                  child: Text(
                    item.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      fontSize: 15.0,
                      letterSpacing: 0.0,
                      color: theme.primaryText,
                    ),
                  ),
                ),
                if (meta.isNotEmpty) ...[
                  const SizedBox(width: 10.0),
                  ConstrainedBox(
                    constraints:
                        BoxConstraints(maxWidth: constraints.maxWidth * 0.45),
                    child: item.project != null
                        ? Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              TaskProjectIcon(project: item.project, size: 12.0),
                              const SizedBox(width: 5.0),
                              Flexible(
                                child: Text(
                                  meta,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: metaStyle,
                                ),
                              ),
                            ],
                          )
                        // A raw folder: the tail carries the meaning.
                        : StartEllipsisText(meta, style: metaStyle),
                  ),
                ],
                if (identifier.isNotEmpty) ...[
                  const SizedBox(width: 8.0),
                  // With the "#", because the key IS the token this row types.
                  Text('#$identifier', style: metaStyle),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _leading(FlutterFlowTheme theme) => switch (item.kind) {
        'task' => TaskStatusIcon(status: item.status ?? 'backlog', size: 15.0),
        'automation' =>
          Icon(Icons.schedule_rounded, size: 18.0, color: theme.secondaryText),
        _ => Icon(Icons.chat_bubble_outline_rounded,
            size: 17.0, color: theme.secondaryText),
      };
}
