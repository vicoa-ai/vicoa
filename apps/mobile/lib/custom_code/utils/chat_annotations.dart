// Chat annotations: a passage selected in the transcript, with an optional
// comment, carried in the composer until the next send.
//
// Mirrors the dashboard's `apps/web/lib/chat-annotations.ts` — same clamp, same
// block — so a quote sent from the phone reads to the agent exactly like one
// sent from the web. Like `#` references they are composer state the text field
// never sees, and they reach the agent as text: at send time the list becomes a
// numbered block of quotes and comments under the typed message. Nothing is
// stored server-side.
//
// Two surfaces hold them. The chat composer keeps a list per session in
// `FFAppState`, next to the draft. "Continue in new session" hands one quote to
// the new-session screen as a [ChatAnnotationHandoff]; like a fork's history
// that is deliberately not persisted, so it can't attach itself to an unrelated
// session later.

import 'dart:ui' show VoidCallback;

import 'package:uuid/uuid.dart';

class ChatAnnotation {
  const ChatAnnotation({required this.id, required this.quote, this.comment = ''});

  final String id;

  /// The selected text, normalised by [normalizeSelectedText].
  final String quote;

  /// The user's note on it; empty when they added none.
  final String comment;

  ChatAnnotation copyWith({String? comment}) => ChatAnnotation(id: id, quote: quote, comment: comment ?? this.comment);

  Map<String, dynamic> toJson() => <String, dynamic>{'id': id, 'quote': quote, 'comment': comment};
}

/// Longest quote kept; a longer selection is cut with a marker.
const int kMaxQuoteChars = 4000;

/// A selection as a quote: CRLF folded, trailing spaces stripped per line, runs
/// of blank lines squeezed to one, the whole trimmed, then clamped.
String normalizeSelectedText(String text) {
  final cleaned = text
      .replaceAll(RegExp(r'\r\n?'), '\n')
      .split('\n')
      .map((line) => line.replaceFirst(RegExp('[ \\t\u00a0]+\$'), ''))
      .join('\n')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
  if (cleaned.length <= kMaxQuoteChars) return cleaned;
  // Never leave half a surrogate pair at the cut: Flutter refuses to lay out
  // ill-formed UTF-16, so the pill's list would throw on the quote.
  final last = cleaned.codeUnitAt(kMaxQuoteChars - 1);
  final end = last >= 0xD800 && last <= 0xDBFF ? kMaxQuoteChars - 1 : kMaxQuoteChars;
  return '${cleaned.substring(0, end).trimRight()}\n… (truncated)';
}

ChatAnnotation createAnnotation(String quote, {String comment = ''}) =>
    ChatAnnotation(id: const Uuid().v4(), quote: normalizeSelectedText(quote), comment: comment.trim());

/// One list item: the quote as `>` lines, then the comment. The continuation
/// lines are indented under the number so the block reads as a list both raw
/// (the user bubble renders plain text) and to an agent parsing markdown.
String _formatAnnotation(ChatAnnotation annotation, int index) {
  final marker = '${index + 1}. ';
  final indent = ' ' * marker.length;
  final lines = <String>[];
  final quoteLines = annotation.quote.split('\n');
  for (var i = 0; i < quoteLines.length; i++) {
    final line = quoteLines[i];
    lines.add('${i == 0 ? marker : indent}>${line.isEmpty ? '' : ' $line'}');
  }
  final comment = annotation.comment.trim();
  if (comment.isEmpty) return lines.join('\n');
  final commentLines = comment.split('\n');
  for (var i = 0; i < commentLines.length; i++) {
    lines.add('$indent${i == 0 ? 'Comment: ' : ''}${commentLines[i]}');
  }
  return lines.join('\n');
}

/// The numbered quotes, with no header line: the block is read by the agent,
/// and the `>` quotes already say what they are.
String buildAnnotationBlock(List<ChatAnnotation> annotations) {
  final kept = annotations.where((a) => a.quote.trim().isNotEmpty).toList();
  return [for (var i = 0; i < kept.length; i++) _formatAnnotation(kept[i], i)].join('\n\n');
}

/// Typed text first, then the annotations under a rule, as `#` references do.
/// Without annotations the body goes through untouched.
String appendAnnotations(String body, List<ChatAnnotation> annotations) {
  final block = buildAnnotationBlock(annotations);
  if (block.isEmpty) return body;
  final typed = body.trim();
  return typed.isEmpty ? block : '$typed\n\n---\n$block';
}

/// A stored list, keeping only well-formed entries.
List<ChatAnnotation> parseAnnotations(dynamic raw) {
  if (raw is! List) return [];
  final out = <ChatAnnotation>[];
  for (final item in raw) {
    if (item is! Map) continue;
    final id = item['id'];
    final quote = item['quote'];
    if (id is! String || quote is! String || quote.trim().isEmpty) continue;
    final comment = item['comment'];
    out.add(ChatAnnotation(id: id, quote: quote, comment: comment is String ? comment : ''));
  }
  return out;
}

/// What "Continue in new session" carries into the new-session screen: the
/// selected text and, for the session's owner, the machine / folder / agent to
/// open on (the way a fork does). Travels through the router as a plain JSON
/// map (like `forkContext`).
class ChatAnnotationHandoff {
  const ChatAnnotationHandoff({required this.annotations, this.machineId, this.directory, this.agentType});

  final List<ChatAnnotation> annotations;
  final String? machineId;
  final String? directory;
  final String? agentType;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'annotations': [for (final a in annotations) a.toJson()],
        if (machineId != null) 'machineId': machineId,
        if (directory != null) 'directory': directory,
        if (agentType != null) 'agentType': agentType,
      };

  /// Reads the map back, or null when it carries no text to continue from.
  static ChatAnnotationHandoff? fromJson(dynamic raw) {
    if (raw is! Map) return null;
    final annotations = parseAnnotations(raw['annotations']);
    if (annotations.isEmpty) return null;
    String? str(String key) {
      final value = raw[key]?.toString().trim();
      return value == null || value.isEmpty ? null : value;
    }

    return ChatAnnotationHandoff(annotations: annotations, machineId: str('machineId'), directory: str('directory'), agentType: str('agentType'));
  }
}

/// The composer's list of annotations, for the page models. The list is
/// replaced, never mutated, and every change goes through
/// [onAnnotationsChanged] so the host can persist it and repaint.
mixin ChatAnnotationsMixin {
  List<ChatAnnotation> annotations = const [];

  /// Bumped on every change; the chat page gates its rebuilds on it, the way it
  /// does on `pendingAttachmentsRevision`.
  int annotationsRevision = 0;

  VoidCallback? get annotationsOnStateChanged;

  /// Called after every change, before the repaint. The chat persists here.
  void onAnnotationsChanged() {}

  void _setAnnotations(List<ChatAnnotation> next) {
    annotations = next;
    annotationsRevision++;
    onAnnotationsChanged();
    annotationsOnStateChanged?.call();
  }

  /// Adds a selected passage; null when nothing is left of it once normalised.
  ChatAnnotation? addAnnotation(String quote) {
    final annotation = createAnnotation(quote);
    if (annotation.quote.isEmpty) return null;
    _setAnnotations([...annotations, annotation]);
    return annotation;
  }

  void updateAnnotationComment(String id, String comment) =>
      _setAnnotations([for (final a in annotations) a.id == id ? a.copyWith(comment: comment.trim()) : a]);

  void removeAnnotation(String id) => _setAnnotations(annotations.where((a) => a.id != id).toList());

  void clearAnnotations() => _setAnnotations(const []);

  /// Drops the annotations a send carried. One picked while that send was still
  /// uploading its attachments isn't in the message, so it stays.
  void removeSentAnnotations(List<ChatAnnotation> sent) {
    final ids = {for (final a in sent) a.id};
    _setAnnotations(annotations.where((a) => !ids.contains(a.id)).toList());
  }
}
