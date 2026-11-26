import 'package:flutter/material.dart';

import '/custom_code/utils/task_mentions.dart';
import '/custom_code/widgets/markdown_text_builder.dart';
import '/custom_code/widgets/transcript_selection.dart';

/// A comment's (or a description's) markdown, drawn by the chat's renderer so
/// code, lists, quotes and links read the same as in a session.
///
/// That renderer sets its sizes for a chat bubble (18pt body). A task sheet
/// reads at [fontSize], so the whole block is scaled down through the text
/// scaler instead of forking the renderer: headings, code and body keep their
/// proportions, and the reader's own text-size setting still applies on top.
///
/// Mentions (`[@Name](vicoa://agent/…)`) are drawn as bold names: as links
/// they would try to open a `vicoa://` URL that goes nowhere.
///
/// Selectable like a chat message (long press, then Copy): agents write
/// paths, commands and ids people want to lift out.
class TaskMarkdown extends StatelessWidget {
  const TaskMarkdown(this.text, {super.key, this.fontSize = 15.0});

  final String text;
  final double fontSize;

  /// The chat renderer's body size.
  static const double _chatBodySize = 18.0;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    return MediaQuery(
      data: media.copyWith(textScaler: _ScaledTextScaler(media.textScaler, fontSize / _chatBodySize)),
      child: TranscriptSelectionArea(
        child: Builder(
          builder: (context) => buildMarkdownText(context, displayMentions(text), false, onSendMessage: (_) {}),
        ),
      ),
    );
  }
}

/// [inner], scaled by a fixed [factor] first.
class _ScaledTextScaler extends TextScaler {
  const _ScaledTextScaler(this.inner, this.factor);

  final TextScaler inner;
  final double factor;

  @override
  double scale(double fontSize) => inner.scale(fontSize * factor);

  @override
  // ignore: deprecated_member_use
  double get textScaleFactor => inner.textScaleFactor * factor;

  @override
  bool operator ==(Object other) => other is _ScaledTextScaler && other.inner == inner && other.factor == factor;

  @override
  int get hashCode => Object.hash(inner, factor);
}
