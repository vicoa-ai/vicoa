// Annotations waiting in a composer, and the two sheets that edit them.
//
// The web's pill opens its list on hover and writes the comment in a popover at
// the selection. A phone has no hover, and a field at the selection would sit
// under the keyboard, so here both live in bottom sheets: tapping the pill lists
// the annotations, and "Add to chat" opens a sheet with the passage above the
// comment field, which stands in for the highlight the web keeps on the page.
//
// Closing either sheet without its button keeps what was typed, as clicking away
// does on the web. There is no Esc to mean "throw this away" on a phone.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/chat_annotations.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

/// The "N annotations" pill. Tapping it opens the list; the × drops them all.
class AnnotationsChip extends StatelessWidget {
  const AnnotationsChip({super.key, required this.composer});

  final ChatAnnotationsMixin composer;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: Container(
        decoration: BoxDecoration(
          color: theme.secondaryText.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(16.0),
        ),
        child: Material(
          color: Colors.transparent,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              InkWell(
                borderRadius: BorderRadius.circular(16.0),
                onTap: () {
                  HapticFeedback.lightImpact();
                  showAnnotationsListSheet(context, composer);
                },
                child: Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(10.0, 7.0, 4.0, 7.0),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.format_quote_rounded, size: 16.0, color: theme.secondaryText),
                      const SizedBox(width: 6.0),
                      Text(
                        l10n.chatAnnotationsCount(composer.annotations.length),
                        style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.primaryText, fontSize: 14.0, letterSpacing: 0.0),
                      ),
                    ],
                  ),
                ),
              ),
              InkResponse(
                radius: 16.0,
                onTap: () {
                  HapticFeedback.lightImpact();
                  composer.clearAnnotations();
                },
                child: Semantics(
                  button: true,
                  label: l10n.chatAnnotationsRemoveAll,
                  child: Tooltip(
                    message: l10n.chatAnnotationsRemoveAll,
                    child: SizedBox(
                      width: 32.0,
                      height: 32.0,
                      child: Icon(Icons.close_rounded, size: 16.0, color: theme.secondaryText),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// How a comment sheet ended: what was typed, and whether to send right away.
class AnnotationCommentResult {
  String comment = '';
  bool send = false;
}

/// Writes the comment for a passage just added to the composer. With [canSend]
/// the sheet also offers to send the message at once, as ⌘⏎ does on the web.
Future<AnnotationCommentResult> showAnnotationCommentSheet(BuildContext context, {required String quote, required bool canSend}) async {
  final result = AnnotationCommentResult();
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _AnnotationCommentSheet(quote: quote, canSend: canSend, result: result),
  );
  return result;
}

class _AnnotationCommentSheet extends StatelessWidget {
  const _AnnotationCommentSheet({required this.quote, required this.canSend, required this.result});

  final String quote;
  final bool canSend;
  final AnnotationCommentResult result;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final media = MediaQuery.of(context);
    return _SheetSurface(
      child: Padding(
        padding: EdgeInsets.fromLTRB(16.0, 4.0, 16.0, 12.0 + (media.viewInsets.bottom > 0 ? media.viewInsets.bottom : media.padding.bottom)),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(4.0, 0.0, 4.0, 10.0),
              child: _QuoteText(quote, maxLines: 3),
            ),
            AnnotationCommentField(
              autofocus: true,
              onChanged: (text) => result.comment = text,
              onSubmit: () => Navigator.pop(context),
              submitLabel: l10n.chatAnnotationAdd,
              onSend: canSend
                  ? () {
                      result.send = true;
                      Navigator.pop(context);
                    }
                  : null,
            ),
          ],
        ),
      ),
    );
  }
}

/// Lists the composer's annotations. A comment is edited in place in the same
/// field the comment sheet uses; starting another row's edit, or closing the
/// sheet, keeps what was typed.
Future<void> showAnnotationsListSheet(BuildContext context, ChatAnnotationsMixin composer) async {
  final edit = _CommentEdit();
  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _AnnotationsListSheet(composer: composer, edit: edit),
  );
  edit.commit(composer);
}

/// The row being edited. Held outside the sheet because the sheet is still
/// animating out when its future completes, and it can't notify the page from
/// its own dispose.
class _CommentEdit {
  String? id;
  String draft = '';

  void commit(ChatAnnotationsMixin composer) {
    final current = id;
    id = null;
    if (current != null) composer.updateAnnotationComment(current, draft);
  }
}

class _AnnotationsListSheet extends StatefulWidget {
  const _AnnotationsListSheet({required this.composer, required this.edit});

  final ChatAnnotationsMixin composer;
  final _CommentEdit edit;

  @override
  State<_AnnotationsListSheet> createState() => _AnnotationsListSheetState();
}

class _AnnotationsListSheetState extends State<_AnnotationsListSheet> {
  void _startEdit(ChatAnnotation annotation) {
    if (widget.edit.id == annotation.id) return;
    HapticFeedback.lightImpact();
    setState(() {
      widget.edit.commit(widget.composer);
      widget.edit.id = annotation.id;
      widget.edit.draft = annotation.comment;
    });
  }

  void _commitEdit() => setState(() => widget.edit.commit(widget.composer));

  void _remove(ChatAnnotation annotation) {
    HapticFeedback.lightImpact();
    if (widget.edit.id == annotation.id) widget.edit.id = null;
    widget.composer.removeAnnotation(annotation.id);
    // The last one gone leaves nothing to show.
    if (widget.composer.annotations.isEmpty) {
      Navigator.pop(context);
      return;
    }
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final annotations = widget.composer.annotations;
    final maxHeight = media.size.height * 0.65;
    // A modal sheet's MediaQuery has the status bar removed; the view still knows.
    final statusBar = MediaQueryData.fromView(View.of(context)).padding.top;
    final available = media.size.height - media.viewInsets.bottom - statusBar - 12.0;
    return Padding(
      padding: EdgeInsets.only(bottom: media.viewInsets.bottom),
      child: _SheetSurface(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: maxHeight < available ? maxHeight : available),
          child: ListView.separated(
            shrinkWrap: true,
            padding: EdgeInsets.fromLTRB(16.0, 4.0, 8.0, 12.0 + (media.viewInsets.bottom > 0 ? 0.0 : media.padding.bottom)),
            itemCount: annotations.length,
            separatorBuilder: (_, __) => Divider(height: 20.0, thickness: 1.0, color: FlutterFlowTheme.of(context).alternate),
            itemBuilder: (_, index) => _buildRow(annotations[index], index),
          ),
        ),
      ),
    );
  }

  Widget _buildRow(ChatAnnotation annotation, int index) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final editing = widget.edit.id == annotation.id;
    final labelStyle = theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 12.0, letterSpacing: 0.0);
    final hasComment = annotation.comment.isNotEmpty;
    return Column(
      key: ValueKey(annotation.id),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 22.0, child: Padding(padding: const EdgeInsets.only(top: 1.0), child: Text('${index + 1}.', style: labelStyle))),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _QuoteText(annotation.quote, maxLines: 3),
                  if (!editing && hasComment) ...[
                    const SizedBox(height: 6.0),
                    GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => _startEdit(annotation),
                      child: Text(
                        annotation.comment,
                        style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.primaryText, fontSize: 14.0, letterSpacing: 0.0),
                      ),
                    ),
                  ],
                  if (!editing && !hasComment)
                    GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => _startEdit(annotation),
                      child: Padding(padding: const EdgeInsets.only(top: 6.0), child: Text(l10n.chatAnnotationAddComment, style: labelStyle)),
                    ),
                ],
              ),
            ),
            _RowIconButton(
              icon: Icons.edit_outlined,
              tooltip: hasComment ? l10n.chatAnnotationEditComment : l10n.chatAnnotationAddComment,
              onPressed: () => _startEdit(annotation),
            ),
            _RowIconButton(icon: Icons.delete_outline_rounded, tooltip: l10n.chatAnnotationDelete, onPressed: () => _remove(annotation)),
          ],
        ),
        if (editing)
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(22.0, 8.0, 8.0, 0.0),
            child: AnnotationCommentField(
              key: ValueKey('edit_${annotation.id}'),
              autofocus: true,
              initialValue: annotation.comment,
              onChanged: (text) => widget.edit.draft = text,
              onSubmit: _commitEdit,
              submitLabel: l10n.commonSave,
            ),
          ),
      ],
    );
  }
}

class _RowIconButton extends StatelessWidget {
  const _RowIconButton({required this.icon, required this.tooltip, required this.onPressed});

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => IconButton(
        icon: Icon(icon, size: 18.0, color: FlutterFlowTheme.of(context).secondaryText),
        tooltip: tooltip,
        visualDensity: VisualDensity.compact,
        constraints: const BoxConstraints(minWidth: 36.0, minHeight: 36.0),
        padding: EdgeInsets.zero,
        onPressed: onPressed,
      );
}

/// The rounded comment field: grows with its text up to six lines, then scrolls.
/// ✓ submits; with [onSend], an arrow beside it submits and sends the message.
/// The return key breaks the line, as it does in the composer.
class AnnotationCommentField extends StatefulWidget {
  const AnnotationCommentField({
    super.key,
    this.initialValue = '',
    this.autofocus = false,
    required this.onChanged,
    required this.onSubmit,
    required this.submitLabel,
    this.onSend,
  });

  final String initialValue;
  final bool autofocus;
  final ValueChanged<String> onChanged;
  final VoidCallback onSubmit;

  /// What ✓ does, e.g. "Add" or "Save"; names the button.
  final String submitLabel;
  final VoidCallback? onSend;

  @override
  State<AnnotationCommentField> createState() => _AnnotationCommentFieldState();
}

class _AnnotationCommentFieldState extends State<AnnotationCommentField> {
  late final _controller = TextEditingController(text: widget.initialValue);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Widget _button({required IconData icon, required String label, required VoidCallback onTap, required bool impact}) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.only(start: 6.0),
      child: Semantics(
        button: true,
        label: label,
        child: Tooltip(
          message: label,
          child: Material(
            color: theme.primaryText,
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: () {
                impact ? HapticFeedback.mediumImpact() : HapticFeedback.lightImpact();
                onTap();
              },
              child: SizedBox(width: 36.0, height: 36.0, child: Icon(icon, size: 20.0, color: theme.primaryBackground)),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Container(
            constraints: const BoxConstraints(minHeight: 36.0),
            decoration: BoxDecoration(
              color: theme.secondaryText.withValues(alpha: 0.05),
              borderRadius: BorderRadius.circular(18.0),
              border: Border.all(color: theme.secondaryText.withValues(alpha: 0.2), width: 1.0),
            ),
            child: TextField(
              controller: _controller,
              autofocus: widget.autofocus,
              minLines: 1,
              maxLines: 6,
              keyboardType: TextInputType.multiline,
              textCapitalization: TextCapitalization.sentences,
              textInputAction: TextInputAction.newline,
              onChanged: widget.onChanged,
              style: theme.bodyMedium.override(fontSize: 16.0),
              decoration: InputDecoration(
                isDense: true,
                hintText: l10n.chatAnnotationCommentHint,
                hintStyle: theme.bodyMedium.override(color: theme.secondaryText, fontSize: 16.0),
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                contentPadding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 8.0),
              ),
            ),
          ),
        ),
        _button(icon: Icons.check_rounded, label: widget.submitLabel, onTap: widget.onSubmit, impact: false),
        if (widget.onSend != null) _button(icon: Icons.arrow_upward_rounded, label: l10n.chatAnnotationSend, onTap: widget.onSend!, impact: true),
      ],
    );
  }
}

/// A passage in the sheets: secondary text with a rule at its side, so it reads
/// as a quote and not as the comment.
class _QuoteText extends StatelessWidget {
  const _QuoteText(this.quote, {required this.maxLines});

  final String quote;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      padding: const EdgeInsetsDirectional.only(start: 10.0),
      decoration: BoxDecoration(
        border: BorderDirectional(start: BorderSide(color: theme.secondaryText.withValues(alpha: 0.35), width: 2.0)),
      ),
      child: Text(
        quote,
        maxLines: maxLines,
        overflow: TextOverflow.ellipsis,
        style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 14.0, letterSpacing: 0.0),
      ),
    );
  }
}

/// The sheet's rounded surface and drag handle, as in the fork preview.
class _SheetSurface extends StatelessWidget {
  const _SheetSurface({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20.0)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 10.0, bottom: 10.0),
            width: 36.0,
            height: 4.0,
            decoration: BoxDecoration(color: theme.secondaryText.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(2.0)),
          ),
          Flexible(child: child),
        ],
      ),
    );
  }
}
