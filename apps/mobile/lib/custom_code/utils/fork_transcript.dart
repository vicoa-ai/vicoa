// Forking a session: the transcript up to a chosen agent turn, rendered as the
// `<chat-history>` block the new session opens with, plus the payload the
// new-session screen carries it in.
//
// Mirrors the dashboard's `apps/web/lib/fork-session.ts` — same header, same
// budgets, same shape — so a session forked from the phone reads to the agent
// exactly like one forked from the web. The block carries the *conversation*
// (user and agent prose) and, per turn, one line naming the files the agent
// edited. The tool trail itself (Bash, Read, Grep, sub-agents …) is left out:
// on real sessions it is 92-99 % of the transcript by volume and says nothing
// the agent's prose does not, and a bare "Read x" line tempts the new agent
// into believing it has seen the file. The header tells it to re-read instead.
//
// Unlike the web, nothing here has to page the history in first: the chat
// screen already holds every message (`apiGetInstanceMessages` fetches them in
// one request), so the list handed in is the whole session.

import '/custom_code/widgets/thinking_group.dart' show isThinkingMessage;
import '/custom_code/widgets/tool_use_group.dart'
    show isToolUseContent, summarizeToolMessage;
import 'edited_files.dart' show isFileEditToolName;

/// Longest a single transcript entry may be before it is elided.
const int kForkMaxEntryChars = 8000;

/// Overall budget; older entries are dropped first so the fork keeps the tail.
const int kForkMaxTotalChars = 120000;

/// Paths listed on a turn's `[edited: …]` line before it says `+N more`.
const int kForkMaxEditedPaths = 20;

const Set<String> _userSenderTypes = {'user', 'human'};

/// The rendered block plus what the composer chip says about it.
class ForkTranscript {
  const ForkTranscript({
    required this.text,
    required this.messageCount,
    required this.omittedCount,
  });

  /// The `<chat-history>` block prepended to the new session's first message.
  final String text;

  /// Transcript entries the block covers — the chip's "N messages".
  final int messageCount;

  /// Entries dropped from the front to fit the budget.
  final int omittedCount;
}

/// Everything a fork carries from the source session into the new-session
/// screen: the history block itself, and the session's machine / folder /
/// agent so the new run lands where the old one ran. Travels through the
/// router as a plain JSON map (like `taskContext`).
class ForkSessionContext {
  const ForkSessionContext({
    required this.text,
    required this.messageCount,
    this.omittedCount = 0,
    this.sourceInstanceId,
    this.sourceTitle,
    this.machineId,
    this.directory,
    this.agentType,
  });

  final String text;
  final int messageCount;
  final int omittedCount;
  final String? sourceInstanceId;
  final String? sourceTitle;

  /// The source session's machine / folder / agent id, preselected on the
  /// new-session screen. Null when the source session never reported one.
  final String? machineId;
  final String? directory;
  final String? agentType;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'text': text,
        'messageCount': messageCount,
        'omittedCount': omittedCount,
        if (sourceInstanceId != null) 'sourceInstanceId': sourceInstanceId,
        if (sourceTitle != null) 'sourceTitle': sourceTitle,
        if (machineId != null) 'machineId': machineId,
        if (directory != null) 'directory': directory,
        if (agentType != null) 'agentType': agentType,
      };

  /// Reads the map back, or null when it carries no history (a malformed or
  /// empty payload must never silently start a session with nothing attached).
  static ForkSessionContext? fromJson(dynamic raw) {
    if (raw is! Map) return null;
    final text = raw['text']?.toString() ?? '';
    if (text.trim().isEmpty) return null;
    String? str(String key) {
      final value = raw[key]?.toString().trim();
      return value == null || value.isEmpty ? null : value;
    }

    return ForkSessionContext(
      text: text,
      messageCount: (raw['messageCount'] as num?)?.toInt() ?? 0,
      omittedCount: (raw['omittedCount'] as num?)?.toInt() ?? 0,
      sourceInstanceId: str('sourceInstanceId'),
      sourceTitle: str('sourceTitle'),
      machineId: str('machineId'),
      directory: str('directory'),
      agentType: str('agentType'),
    );
  }
}

String _clampEntry(String text) {
  if (text.length <= kForkMaxEntryChars) return text;
  return '${text.substring(0, kForkMaxEntryChars)}\n… (truncated)';
}

/// `/repo/src/a.dart` → `src/a.dart` when the path sits under the source
/// folder. Tool content usually reaches the chat with the project root already
/// stripped, so this only bites on the rows where it did not.
String _relativeToSource(String path, String? sourceDirectory) {
  final base = (sourceDirectory ?? '').replaceAll(RegExp(r'/+$'), '');
  if (base.isEmpty) return path;
  if (path == base) return '.';
  return path.startsWith('$base/') ? path.substring(base.length + 1) : path;
}

String _formatEditedLine(List<String> paths) {
  final shown = paths.take(kForkMaxEditedPaths).toList();
  final more = paths.length - shown.length;
  return '  [edited: ${shown.join(', ')}${more > 0 ? ', … +$more more' : ''}]';
}

enum _EntryKind { user, agent, tool }

class _Classified {
  _Classified(this.kind, this.text, this.edited);

  final _EntryKind kind;
  final String text;

  /// Set on tool rows: the files this row edited, if it is an edit-class tool.
  final List<String> edited;
}

class _Line {
  _Line(this.text, {required this.isMessage});

  String text;

  /// Counts toward the chip's "N messages" (a standalone edited line does not).
  final bool isMessage;
}

/// One turn: the user message that opened it (null for a leading agent run)
/// and everything agent-side that followed, in order.
class _Turn {
  _Classified? user;
  final List<_Classified> entries = <_Classified>[];
}

_Classified? _classify(dynamic message, String Function(String) sanitize) {
  if (message is! Map) return null;
  // Reasoning blocks are the model's scratchpad, not conversation — a fresh
  // agent has its own, so carrying them over is noise.
  if (isThinkingMessage(message)) return null;
  final content = sanitize(message['content']?.toString() ?? '');
  // Control commands and the "waiting for input" filler sanitize away to
  // nothing; so does a message that was only an AskUserQuestion payload.
  if (content.trim().isEmpty) return null;
  final sender = message['sender_type']?.toString().toLowerCase() ?? '';
  if (_userSenderTypes.contains(sender)) {
    return _Classified(_EntryKind.user, content.trim(), const <String>[]);
  }
  if (isToolUseContent(content)) {
    final tool = summarizeToolMessage(content);
    final edited = isFileEditToolName(tool.name) && tool.isFile
        ? <String>[tool.description]
        : const <String>[];
    return _Classified(_EntryKind.tool, content.trim(), edited);
  }
  return _Classified(_EntryKind.agent, content.trim(), const <String>[]);
}

List<_Turn> _groupTurns(List<_Classified> entries) {
  final turns = <_Turn>[];
  _Turn? current;
  for (final entry in entries) {
    if (entry.kind == _EntryKind.user) {
      current = _Turn();
      current.user = entry;
      turns.add(current);
      continue;
    }
    if (current == null) {
      // A leading agent run: a turn with no user message of its own.
      current = _Turn();
      turns.add(current);
    }
    current.entries.add(entry);
  }
  return turns;
}

String _identity(String content) => content;

/// Render the transcript up to and including [boundaryMessageId] as the text
/// block a forked session opens with. An unknown boundary id (the message was
/// pruned mid-tap) falls back to the whole timeline rather than failing.
///
/// [sanitize] is the chat's own `sanitizeMessageContent` ∘
/// `filterProjectRootFromContent` — passed in so this stays a pure function
/// over the message list and can be unit-tested without the chat model.
ForkTranscript buildForkTranscript({
  required List<dynamic> messages,
  required String boundaryMessageId,
  String Function(String content)? sanitize,
  String? sourceTitle,
  String? sourceDirectory,
}) {
  final String Function(String) clean = sanitize ?? _identity;
  final boundaryIndex =
      messages.indexWhere((m) => m is Map && m['id']?.toString() == boundaryMessageId);
  final selected =
      boundaryIndex >= 0 ? messages.sublist(0, boundaryIndex + 1) : messages;
  final directory = sourceDirectory?.trim();

  final classified = <_Classified>[];
  for (final message in selected) {
    final entry = _classify(message, clean);
    if (entry != null) classified.add(entry);
  }

  final lines = <_Line>[];
  for (final turn in _groupTurns(classified)) {
    final user = turn.user;
    if (user != null && user.text.isNotEmpty) {
      lines.add(_Line('User: ${_clampEntry(user.text)}', isMessage: true));
    }

    final turnStart = lines.length;
    final edited = <String>[];
    final seen = <String>{};
    for (final entry in turn.entries) {
      if (entry.kind == _EntryKind.agent) {
        lines.add(_Line('Agent: ${_clampEntry(entry.text)}', isMessage: true));
        continue;
      }
      for (final path in entry.edited) {
        final shown = _relativeToSource(path, directory);
        if (!seen.add(shown)) continue;
        edited.add(shown);
      }
    }
    if (edited.isEmpty) continue;
    // The line rides on the turn's last prose entry so a budget trim never
    // separates the two; a turn that only edited (no prose) still gets it.
    final line = _formatEditedLine(edited);
    if (lines.length > turnStart) {
      lines.last.text = '${lines.last.text}\n$line';
    } else {
      lines.add(_Line(line, isMessage: false));
    }
  }

  // Trim from the front — the messages nearest the fork point are the ones the
  // new session actually needs.
  var total = lines.fold<int>(0, (sum, line) => sum + line.text.length + 1);
  var omitted = 0;
  while (lines.length > 1 && total > kForkMaxTotalChars) {
    final first = lines.removeAt(0);
    total -= first.text.length + 1;
    if (first.isMessage) omitted += 1;
  }

  final rendered = lines.map((line) => line.text).toList();
  if (omitted > 0) {
    rendered.insert(
        0, '… $omitted earlier message${omitted == 1 ? '' : 's'} omitted …');
  }

  final header = <String>[
    'Chat history from an earlier Vicoa session, for context.',
    'Tool outputs are not included; re-read any file you need.',
  ];
  final title = sourceTitle?.trim();
  if (title != null && title.isNotEmpty) header.add('Source session: $title');
  if (directory != null && directory.isNotEmpty) {
    header.add('Source directory: $directory');
  }

  final body =
      rendered.isNotEmpty ? rendered.join('\n') : 'No chat history to display.';
  return ForkTranscript(
    text: '<chat-history>\n${header.join('\n')}\n\n$body\n</chat-history>',
    messageCount: lines.where((line) => line.isMessage).length,
    omittedCount: omitted,
  );
}
