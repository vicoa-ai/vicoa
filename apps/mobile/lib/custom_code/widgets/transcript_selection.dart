// Selecting text in the chat transcript: the system selection toolbar, with the
// session's "Add to chat" and "Continue in new session" next to Copy.
//
// Transcript text is selectable through more than one widget: the message's
// [TranscriptSelectionArea], the areas nested in diff and terminal output, and
// the code blocks' `SelectableText`. They all read the actions from one
// [TranscriptSelectionActions] above the message list rather than taking
// callbacks through the markdown builder. Outside a chat there is no scope, so
// the same widgets keep the plain system menu.

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show SelectedContent;
import 'package:flutter/services.dart';

import '/custom_code/utils/chat_annotations.dart';
import '/l10n/app_localizations.dart';

/// What the toolbar offers for a selection in the transcript below it. A null
/// action hides its row.
class TranscriptSelectionActions extends InheritedWidget {
  const TranscriptSelectionActions({super.key, this.onAddToChat, this.onContinueInNewSession, required super.child});

  final ValueChanged<String>? onAddToChat;
  final ValueChanged<String>? onContinueInNewSession;

  /// Read when a toolbar opens, not depended on: the callbacks are new closures
  /// on every page rebuild, which must not rebuild every message.
  static TranscriptSelectionActions? maybeOf(BuildContext context) => context.getInheritedWidgetOfExactType<TranscriptSelectionActions>();

  @override
  bool updateShouldNotify(TranscriptSelectionActions oldWidget) => false;
}

/// [items] with the transcript's actions added after Copy. Each one runs on the
/// text selected at the moment of the tap, after [dismiss] has ended the
/// selection. [context] must sit under the scope; the context a toolbar is built
/// in belongs to the overlay, above the page.
List<ContextMenuButtonItem> withTranscriptSelectionActions(
  BuildContext context,
  List<ContextMenuButtonItem> items, {
  required String Function() selectedText,
  required VoidCallback dismiss,
}) {
  final actions = TranscriptSelectionActions.maybeOf(context);
  if (actions == null) return items;
  final l10n = AppLocalizations.of(context);
  ContextMenuButtonItem item(String label, ValueChanged<String> action) => ContextMenuButtonItem(
        label: label,
        onPressed: () {
          final quote = normalizeSelectedText(selectedText());
          dismiss();
          if (quote.isEmpty) return;
          HapticFeedback.lightImpact();
          action(quote);
        },
      );
  final copyIndex = items.indexWhere((i) => i.type == ContextMenuButtonType.copy);
  return [...items]..insertAll(copyIndex + 1, [
      if (actions.onAddToChat != null) item(l10n.chatSelectionAddToChat, actions.onAddToChat!),
      if (actions.onContinueInNewSession != null) item(l10n.chatSelectionContinueInNewSession, actions.onContinueInNewSession!),
    ]);
}

/// A [SelectionArea] for transcript text.
///
/// Besides the toolbar above, it keeps block boundaries in the selected text:
/// Flutter's own delegate writes its children's text back to back, so two
/// selected paragraphs would quote and copy as "first.Second".
class TranscriptSelectionArea extends StatefulWidget {
  const TranscriptSelectionArea({super.key, required this.child});

  final Widget child;

  @override
  State<TranscriptSelectionArea> createState() => _TranscriptSelectionAreaState();
}

class _TranscriptSelectionAreaState extends State<TranscriptSelectionArea> {
  final _delegate = _BlockSelectionDelegate();
  String _selectedText = '';

  @override
  void dispose() {
    _delegate.dispose();
    super.dispose();
  }

  Widget _buildToolbar(BuildContext _, SelectableRegionState region) => AdaptiveTextSelectionToolbar.buttonItems(
        anchors: region.contextMenuAnchors,
        buttonItems: withTranscriptSelectionActions(
          context,
          region.contextMenuButtonItems,
          selectedText: () => _selectedText,
          dismiss: () {
            region.clearSelection();
            region.hideToolbar();
          },
        ),
      );

  @override
  Widget build(BuildContext context) => SelectionArea(
        onSelectionChanged: (content) => _selectedText = content?.plainText ?? '',
        contextMenuBuilder: _buildToolbar,
        child: SelectionContainer(delegate: _delegate, child: widget.child),
      );
}

/// Joins its children's selected text by where they sit: a line break when the
/// next one starts below the previous one, a space when they share a line (a
/// bullet and its text, two table cells).
class _BlockSelectionDelegate extends StaticSelectionContainerDelegate {
  @override
  SelectedContent? getSelectedContent() {
    final buffer = StringBuffer();
    Rect? previousLine;
    var previousText = '';
    for (final selectable in selectables) {
      final text = selectable.getSelectedContent()?.plainText ?? '';
      if (text.isEmpty) continue;
      final boxes = selectable.boundingBoxes;
      final transform = selectable.getTransformTo(null);
      final firstLine = boxes.isEmpty ? null : MatrixUtils.transformRect(transform, boxes.first);
      if (previousText.isNotEmpty) {
        if (previousLine == null || firstLine == null || firstLine.center.dy > previousLine.bottom) {
          buffer.write('\n');
        } else if (!_endsOrStartsWithSpace(previousText, text)) {
          buffer.write(' ');
        }
      }
      buffer.write(text);
      previousLine = boxes.isEmpty ? null : MatrixUtils.transformRect(transform, boxes.last);
      previousText = text;
    }
    return buffer.isEmpty ? null : SelectedContent(plainText: buffer.toString());
  }

  static bool _endsOrStartsWithSpace(String before, String after) {
    const space = ' \t\n';
    return space.contains(before[before.length - 1]) || space.contains(after[0]);
  }
}
