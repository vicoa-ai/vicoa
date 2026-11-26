/// Mentions in task comments, and who a comment would wake. A port of the
/// web's `lib/task-mentions.ts`; keep the two in step.
///
/// A mention is the markdown link the composer's `@` picker inserts:
/// `[@Name](vicoa://agent/<profile id>)` for an agent, `[@Name](vicoa://user/
/// <user id>)` for a person. A plain typed "@name" is not one: an agent mention
/// starts a run on someone's computer and a person mention sends a push, so
/// either has to be a deliberate pick. A person mention only tells them; it
/// wakes no agent.
///
/// [agentsToWake] mirrors the server's routing (`shared/task_dispatch.py`,
/// `route_comment`) so the hint under the box says what sending will do. The
/// first rule that applies decides, and only that one:
///
/// 1. a comment starting with `/note` wakes nobody;
/// 2. explicit agent mentions wake those agents (on a Done or Cancelled task a
///    mention is the only thing that wakes anyone);
/// 3. a reply in a thread an agent wrote in wakes that agent;
/// 4. a top-level comment wakes the agents with an open question to the person
///    writing it (it answers them), if any;
/// 5. else a top-level comment on a task assigned to an agent wakes that agent.
///
/// The server stays the authority: this only predicts it for the hint.
library;

const String _uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
final RegExp _agentInBody = RegExp('\\(vicoa://agent/($_uuid)\\)');

/// A mention link anywhere in a body: `[@Name](vicoa://agent|user/<id>)`.
final RegExp _mentionLink = RegExp('\\[@([^\\]]*)\\]\\(vicoa://(agent|user)/($_uuid)\\)');

/// `/note` as a word at the very start ("/notebook" is not a note); mirrors
/// the server's `is_note`.
final RegExp _note = RegExp(r'^/note(?:\s|:|$)', caseSensitive: false);

const String _notePrefix = '/note';

/// Who a mention names: `agent` or `user`.
String mentionMarkdown(String kind, String name, String id) {
  final safe = name.replaceAll(RegExp(r'[\[\]]'), '');
  return '[@$safe](vicoa://${kind == 'user' ? 'user' : 'agent'}/$id)';
}

/// Profiles a body mentions, in order, each once, lower-cased.
List<String> mentionedAgentIds(String body) {
  final out = <String>[];
  for (final m in _agentInBody.allMatches(body)) {
    final id = m.group(1)!.toLowerCase();
    if (!out.contains(id)) out.add(id);
  }
  return out;
}

bool isNoteComment(String body) => _note.hasMatch(body.trimLeft());

/// The note body without its `/note` prefix, for display.
String stripNotePrefix(String body) {
  final trimmed = body.trimLeft();
  return trimmed.substring(_notePrefix.length).replaceFirst(RegExp(r'^[\s:]+'), '');
}

/// A posted body as the timeline shows it: each mention link drawn as bold
/// `@Name` rather than a link. The markdown renderer would otherwise open the
/// `vicoa://` URL on a tap, which goes nowhere.
String displayMentions(String body) => body.replaceAllMapped(_mentionLink, (m) => '**@${m.group(1)}**');

/// An agent waiting on the viewer: it asked them a question on this task.
class WaitingAgent {
  const WaitingAgent(this.id, this.name);
  final String id;
  final String name;
}

/// Where a box sits, for [agentsToWake].
class WakeContext {
  const WakeContext({
    required this.inThread,
    this.threadAgentId,
    this.assigneeAgentId,
    this.taskClosed = false,
    this.askers = const [],
  });

  /// The box replies inside a thread (vs. starting a new one).
  final bool inThread;

  /// In a thread: the agent that wrote in it most recently.
  final String? threadAgentId;

  /// The task's assignee, when it is an agent.
  final String? assigneeAgentId;

  /// Done or Cancelled: only an explicit mention wakes an agent.
  final bool taskClosed;

  /// Agents with an open question to the viewer: a top-level comment from the
  /// viewer is their answer and goes to them instead of the assignee.
  final List<WaitingAgent> askers;
}

/// The agent profile ids (lower-cased) sending [body] would wake.
List<String> agentsToWake(String body, WakeContext ctx) {
  if (body.trim().isEmpty || isNoteComment(body)) return const [];
  final mentioned = mentionedAgentIds(body);
  if (mentioned.isNotEmpty) return mentioned;
  if (ctx.taskClosed) return const [];
  if (ctx.inThread) return ctx.threadAgentId == null ? const [] : [ctx.threadAgentId!.toLowerCase()];
  final askers = <String>[];
  for (final a in ctx.askers) {
    final id = a.id.toLowerCase();
    if (!askers.contains(id)) askers.add(id);
  }
  if (askers.isNotEmpty) return askers;
  return ctx.assigneeAgentId == null ? const [] : [ctx.assigneeAgentId!.toLowerCase()];
}

// --- The composer's side: `@Name` text plus the picks behind it -------------
//
// The same split as `#` references (composer_references.dart): the box shows
// plain `@Name`, which the user edits like any text, and the pick (name + id)
// is composer state. A pick counts only while its `@Name` is still in the
// text, so deleting the name drops the mention. Only on send does each picked
// `@Name` become the link the server routes on.

/// An agent or person picked from the `@` list, carried beside the draft.
class PickedMention {
  const PickedMention({required this.id, required this.name, this.kind = 'agent'});

  final String id;
  final String name;

  /// `agent` or `user`.
  final String kind;
}

/// What the box shows for a pick. Brackets would break the link on send.
String mentionToken(String name) => '@${name.replaceAll(RegExp(r'[\[\]]'), '')}';

/// Where one picked `@Name` sits in a draft.
class MentionRange {
  const MentionRange(this.start, this.end, this.id);
  final int start;
  final int end;
  final String id;
}

final RegExp _boundaryBefore = RegExp(r'[\s(]');
final RegExp _boundaryAfter = RegExp(r'[\s.,;:!?)]');

bool _isBoundaryBefore(String text, int i) => i == 0 || _boundaryBefore.hasMatch(text[i - 1]);

bool _isBoundaryAfter(String text, int i) => i >= text.length || _boundaryAfter.hasMatch(text[i]);

/// Where each picked `@Name` sits in [text], left to right, never overlapping.
/// Longer names are tried first at a position, so `@bot2` is not read as
/// `@bot` followed by "2".
List<MentionRange> mentionRanges(String text, List<PickedMention> picks) {
  final byToken = <String, String>{for (final p in picks) mentionToken(p.name): p.id};
  final tokens = byToken.entries.toList()..sort((a, b) => b.key.length.compareTo(a.key.length));
  final ranges = <MentionRange>[];
  var index = 0;
  while (index < text.length) {
    final at = text.indexOf('@', index);
    if (at == -1) break;
    MentionRange? matched;
    if (_isBoundaryBefore(text, at)) {
      for (final t in tokens) {
        final end = at + t.key.length;
        if (text.startsWith(t.key, at) && _isBoundaryAfter(text, end)) {
          matched = MentionRange(at, end, t.value);
          break;
        }
      }
    }
    if (matched != null) {
      ranges.add(matched);
      index = matched.end;
    } else {
      index = at + 1;
    }
  }
  return ranges;
}

/// The picks whose `@Name` is still in [text].
List<PickedMention> activeMentions(List<PickedMention> picks, String text) {
  final present = mentionRanges(text, picks).map((r) => r.id).toSet();
  return picks.where((p) => present.contains(p.id)).toList();
}

/// The body to post: each picked `@Name` written as its mention link.
String serializeMentions(String text, List<PickedMention> picks) {
  final ranges = mentionRanges(text, picks);
  if (ranges.isEmpty) return text;
  final byId = {for (final p in picks) p.id: p};
  final out = StringBuffer();
  var cursor = 0;
  for (final r in ranges) {
    out.write(text.substring(cursor, r.start));
    final pick = byId[r.id];
    out.write(mentionMarkdown(pick?.kind ?? 'agent', pick?.name ?? '', r.id));
    cursor = r.end;
  }
  out.write(text.substring(cursor));
  return out.toString();
}
