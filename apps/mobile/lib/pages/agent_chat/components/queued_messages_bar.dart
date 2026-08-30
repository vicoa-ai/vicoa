import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

/// One user message staged behind a busy agent, ready to surface in the queue
/// bar. [text] is already sanitized by the caller (permission-mode tokens etc.
/// stripped) so the bar can render it verbatim.
class QueuedMessageEntry {
  const QueuedMessageEntry({required this.id, required this.text});
  final String id;
  final String text;
}

/// Collapsed queue bar that sits directly above the chat input. Shows the
/// count + a one-line preview of the oldest staged message and expands into
/// [showQueuedMessagesSheet] on tap. Renders nothing when the queue is empty.
///
/// Queued messages never enter the transcript — they're held here until the
/// agent frees up and the backend flips them to `consumed` (at which point
/// they drop out of this list and appear in the chat as normal messages).
class QueuedMessagesBar extends StatelessWidget {
  const QueuedMessagesBar(
      {super.key, required this.items, required this.onTap});

  final List<QueuedMessageEntry> items;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final theme = FlutterFlowTheme.of(context);
    final preview = items.first.text.trim().replaceAll('\n', ' ');
    return Container(
      // 12px side inset matches the chat input container (4px outer padding +
      // 8px inner margin); 8px bottom gap floats it just above the input.
      margin: const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 8.0),
      decoration: BoxDecoration(
        color: theme.secondaryText.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(18.0),
        border: Border.all(
          color: theme.secondaryText.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(18.0),
          onTap: () {
            HapticFeedback.lightImpact();
            onTap();
          },
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(14.0, 10.0, 8.0, 10.0),
            child: Row(
              children: [
                Icon(Icons.pending_outlined,
                    size: 16.0, color: theme.secondaryText),
                const SizedBox(width: 8.0),
                Text(
                  AppLocalizations.of(context).agentChatQueuedCount(items.length),
                  style: theme.bodySmall.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.secondaryText,
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (preview.isNotEmpty) ...[
                  const SizedBox(width: 8.0),
                  Expanded(
                    child: Text(
                      preview,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.bodySmall.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.secondaryText.withValues(alpha: 0.7),
                        fontSize: 13.0,
                        letterSpacing: 0.0,
                      ),
                    ),
                  ),
                ] else
                  const Spacer(),
                const SizedBox(width: 4.0),
                Icon(Icons.unfold_more,
                    size: 18.0,
                    color: theme.secondaryText.withValues(alpha: 0.7)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Opens the expanded queue as a bottom sheet: a scrollable stack of the
/// staged messages, each with a revert-to-input and a cancel action. Stays
/// live while open by rebuilding off [revision] and re-reading [itemsProvider]
/// / [isCancelling], so items consumed or cancelled elsewhere update in place.
/// Auto-dismisses once the queue empties. [onRevert] fires with the message id
/// and its text; the caller closes the sheet, drops the text into the composer
/// and cancels the queued copy.
Future<void> showQueuedMessagesSheet({
  required BuildContext context,
  required Listenable revision,
  required List<QueuedMessageEntry> Function() itemsProvider,
  required bool Function(String id) isCancelling,
  required Future<void> Function(String id) onCancel,
  required Future<void> Function(String id, String text) onRevert,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _QueuedMessagesSheet(
      revision: revision,
      itemsProvider: itemsProvider,
      isCancelling: isCancelling,
      onCancel: onCancel,
      onRevert: onRevert,
    ),
  );
}

class _QueuedMessagesSheet extends StatefulWidget {
  const _QueuedMessagesSheet({
    required this.revision,
    required this.itemsProvider,
    required this.isCancelling,
    required this.onCancel,
    required this.onRevert,
  });

  final Listenable revision;
  final List<QueuedMessageEntry> Function() itemsProvider;
  final bool Function(String id) isCancelling;
  final Future<void> Function(String id) onCancel;
  final Future<void> Function(String id, String text) onRevert;

  @override
  State<_QueuedMessagesSheet> createState() => _QueuedMessagesSheetState();
}

class _QueuedMessagesSheetState extends State<_QueuedMessagesSheet> {
  /// Latches on the first auto-dismiss so a burst of revision bumps (cancel
  /// spinner on → WS removal → spinner off all fire while the queue is empty)
  /// can only ever pop once. A second pop would take the chat page with it and
  /// dump the user on the home screen.
  bool _dismissing = false;

  void _dismissWhenEmpty() {
    if (_dismissing) return;
    _dismissing = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Only pop while this sheet is still the top route — if the user already
      // swiped it away (or pushed something over it), popping would eat the
      // wrong route.
      final route = ModalRoute.of(context);
      if (route != null && route.isCurrent) Navigator.of(context).pop();
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return AnimatedBuilder(
      animation: widget.revision,
      builder: (context, _) {
        final items = widget.itemsProvider();
        if (items.isEmpty) {
          // Nothing left to manage — close so the user lands back on the chat.
          _dismissWhenEmpty();
          return const SizedBox.shrink();
        }
        final maxHeight = MediaQuery.of(context).size.height * 0.5;
        return Container(
          constraints: BoxConstraints(maxHeight: maxHeight),
          decoration: BoxDecoration(
            color: theme.secondaryBackground,
            borderRadius:
                const BorderRadius.vertical(top: Radius.circular(24.0)),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Handle + centered title mirror the agent config sheet
                // (agent_config_sheet.dart) — minus its close/confirm buttons,
                // which have no place here.
                Padding(
                  padding:
                      const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
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
                      const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 16.0),
                  child: Text(
                    AppLocalizations.of(context).agentChatQueuedSheetTitle,
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
                      fontSize: 19.0,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                Flexible(
                  child: ListView.separated(
                    shrinkWrap: true,
                    padding: const EdgeInsetsDirectional.fromSTEB(
                        20.0, 0.0, 12.0, 16.0),
                    itemCount: items.length,
                    separatorBuilder: (_, __) => Divider(
                      height: 1.0,
                      thickness: 1.0,
                      color: theme.alternate,
                    ),
                    itemBuilder: (context, i) => _QueuedRow(
                      entry: items[i],
                      cancelling: widget.isCancelling(items[i].id),
                      onCancel: () => widget.onCancel(items[i].id),
                      // Close the sheet first so the composer (now holding the
                      // reverted text) is visible and focusable underneath.
                      onRevert: () {
                        final entry = items[i];
                        Navigator.of(context).pop();
                        widget.onRevert(entry.id, entry.text);
                      },
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// A single staged message inside the sheet: 2-line preview + a revert-to-input
/// affordance and a cancel affordance (both collapse to a spinner while a
/// cancel request is in flight). Flat on the sheet surface, separated by
/// hairline dividers — mirrors the web queue row.
class _QueuedRow extends StatelessWidget {
  const _QueuedRow({
    required this.entry,
    required this.cancelling,
    required this.onCancel,
    required this.onRevert,
  });

  final QueuedMessageEntry entry;
  final bool cancelling;
  final VoidCallback onCancel;
  final VoidCallback onRevert;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 12.0),
            child: Text(
              entry.text,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: theme.bodyMedium.override(
                font: GoogleFonts.sourceSans3(),
                fontSize: 14.0,
                letterSpacing: 0.0,
              ),
            ),
          ),
        ),
        const SizedBox(width: 8.0),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(0.0, 6.0, 0.0, 0.0),
          child: cancelling
              ? Container(
                  width: 32.0,
                  height: 32.0,
                  alignment: Alignment.center,
                  child: SizedBox(
                    width: 16.0,
                    height: 16.0,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.0,
                      color: theme.secondaryText.withValues(alpha: 0.7),
                    ),
                  ),
                )
              : Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _QueuedRowAction(
                      icon: Icons.undo_rounded,
                      tooltip: AppLocalizations.of(context)
                          .agentChatRevertQueuedMessageTooltip,
                      onTap: () {
                        HapticFeedback.lightImpact();
                        onRevert();
                      },
                    ),
                    _QueuedRowAction(
                      icon: Icons.close_rounded,
                      tooltip: AppLocalizations.of(context)
                          .agentChatCancelQueuedMessageTooltip,
                      onTap: () {
                        HapticFeedback.lightImpact();
                        onCancel();
                      },
                    ),
                  ],
                ),
        ),
      ],
    );
  }
}

/// A 32×32 icon affordance in a queued-message row (revert / cancel). Kept flat
/// and low-contrast so it reads as secondary chrome next to the message text.
class _QueuedRowAction extends StatelessWidget {
  const _QueuedRowAction({
    required this.icon,
    required this.tooltip,
    required this.onTap,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(16.0),
        onTap: onTap,
        child: Tooltip(
          message: tooltip,
          child: Container(
            width: 32.0,
            height: 32.0,
            alignment: Alignment.center,
            child: Icon(
              icon,
              size: 18.0,
              color: theme.secondaryText.withValues(alpha: 0.8),
            ),
          ),
        ),
      ),
    );
  }
}
