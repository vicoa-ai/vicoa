import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;

/// `#` references: pointing a message at another Vicoa thing.
///
/// `@` mentions a file; `#` mentions a *session*, *task* or *automation*. A
/// port of the web's `apps/web/lib/composer-references.ts`, kept line-for-line
/// where it matters so a message reads the same whichever client sent it:
///
///  * The **token** (`#VIC-42`) is what the user sees and edits. It is plain
///    text in the message, so deleting it is just deleting text.
///  * The **reference** (kind + id + the expanded context block) is composer
///    state the text field never sees, fetched once when the row is picked.
///
/// Nothing re-parses the token to find the entity again (a title-derived slug
/// is not a stable key). [activeReferences] reconciles the two by presence: a
/// reference counts only while its token is still somewhere in the text.

/// One row of the `#` panel, as `GET /api/v1/references` returns it.
class ReferenceCandidate {
  const ReferenceCandidate({
    required this.kind,
    required this.id,
    required this.label,
    required this.token,
    this.meta,
    this.project,
    this.identifier,
    this.status,
  });

  /// `session`, `task` or `automation`.
  final String kind;
  final String id;
  final String label;

  /// Text after "#", e.g. `VIC-42`. Whitespace-free by construction.
  final String token;

  /// Where the thing lives: its project's name, else its folder.
  final String? meta;

  /// `{id, name, icon, icon_image_uri, updated_at}` when [meta] is a project.
  final Map<String, dynamic>? project;

  /// Tasks only, and only when the task has a key (`VIC-42`).
  final String? identifier;
  final String? status;

  factory ReferenceCandidate.fromJson(Map<String, dynamic> json) {
    final project = json['project'];
    return ReferenceCandidate(
      kind: json['kind']?.toString() ?? 'session',
      id: json['id']?.toString() ?? '',
      label: json['label']?.toString() ?? '',
      token: json['token']?.toString() ?? '',
      meta: json['meta']?.toString(),
      project: project is Map ? Map<String, dynamic>.from(project) : null,
      identifier: json['identifier']?.toString(),
      status: json['status']?.toString(),
    );
  }
}

/// A picked reference, carried alongside the draft until it is sent.
@immutable
class ComposerReference {
  const ComposerReference({
    required this.kind,
    required this.id,
    required this.token,
    required this.label,
    required this.context,
  });

  final String kind;
  final String id;
  final String token;
  final String label;

  /// The rendered block; empty when the expansion fetch failed.
  final String context;

  /// From `GET /api/v1/references/{kind}/{id}`.
  factory ComposerReference.fromDetail(Map<String, dynamic> json) =>
      ComposerReference(
        kind: json['kind']?.toString() ?? 'session',
        id: json['id']?.toString() ?? '',
        token: json['token']?.toString() ?? '',
        label: json['label']?.toString() ?? '',
        context: json['context']?.toString() ?? '',
      );

  /// What a pick is worth before its expansion arrives. See
  /// [fallbackReferenceContext].
  factory ComposerReference.fromCandidate(ReferenceCandidate item) =>
      ComposerReference(
        kind: item.kind,
        id: item.id,
        token: item.token,
        label: item.label,
        context: fallbackReferenceContext(item),
      );

  @override
  bool operator ==(Object other) =>
      other is ComposerReference &&
      other.kind == kind &&
      other.id == id &&
      other.token == token &&
      other.label == label &&
      other.context == context;

  @override
  int get hashCode => Object.hash(kind, id, token, label, context);
}

const Map<String, String> _kindNoun = {
  'session': 'Session',
  'task': 'Task',
  'automation': 'Automation',
};

/// The one line a reference is worth before its expansion arrives.
///
/// A pick inserts its token instantly and fetches the full block behind it, so
/// a send in that window (or after a failed fetch) would otherwise ship a
/// `#token` the agent has no way to resolve.
String fallbackReferenceContext(ReferenceCandidate item) {
  final noun = _kindNoun[item.kind] ?? 'Session';
  final facts = [
    if (item.meta != null && item.meta!.isNotEmpty) item.meta!,
    'id: ${item.id}',
  ].join(' · ');
  return '$noun "${item.label}"\n$facts';
}

/// The trigger token the caret currently sits in.
@immutable
class TriggerToken {
  const TriggerToken(this.start, this.end, this.query);

  /// Index of the trigger character itself.
  final int start;

  /// Index just past the token (exclusive): the first whitespace, or EOL.
  final int end;

  /// Everything between the trigger and [end].
  final String query;

  @override
  bool operator ==(Object other) =>
      other is TriggerToken &&
      other.start == start &&
      other.end == end &&
      other.query == query;

  @override
  int get hashCode => Object.hash(start, end, query);

  @override
  String toString() => 'TriggerToken($start, $end, "$query")';
}

final RegExp _whitespace = RegExp(r'\s');

/// Find the [trigger]-led token the caret is inside, or null.
///
/// The trigger must start the text or follow whitespace, and the caret must
/// sit within the token it opens, the same rules `@` uses, so `@` and `#` can
/// never both claim the caret.
TriggerToken? detectTriggerToken(String text, int cursor, String trigger) {
  if (text.isEmpty) return null;
  final start = text.lastIndexOf(trigger, math.max(0, cursor - 1));
  if (start == -1) return null;

  final after = text.substring(start + 1);
  final whitespaceIndex = after.indexOf(_whitespace);
  final end =
      whitespaceIndex == -1 ? text.length : start + 1 + whitespaceIndex;
  if (cursor < start || cursor > end) return null;
  if (start != 0 && !_whitespace.hasMatch(text[start - 1])) return null;

  return TriggerToken(start, end, text.substring(start + 1, end));
}

/// Replace [token]'s slice with `<trigger><value>`, leaving the caret after it.
({String text, int cursor}) replaceTriggerToken(
  String text,
  TriggerToken token,
  String trigger,
  String value,
) {
  final before = text.substring(0, token.start);
  final after = text.substring(token.end);
  final needsSpace = after.isEmpty || !after.startsWith(' ');
  final inserted = '$trigger$value${needsSpace ? ' ' : ''}';
  return (
    text: '$before$inserted$after',
    cursor: before.length + inserted.length,
  );
}

/// Add a pick, replacing any earlier reference that produced the same token.
///
/// Two entities can slugify alike ("Fix the bug" twice). Keeping both would
/// attach two blocks for one visible token, so the newest pick wins.
List<ComposerReference> addReference(
  List<ComposerReference> refs,
  ComposerReference next,
) =>
    [...refs.where((r) => r.token != next.token), next];

/// The references whose token still appears in the draft.
List<ComposerReference> activeReferences(
  List<ComposerReference> refs,
  String text,
) =>
    refs.where((ref) => text.contains('#${ref.token}')).toList();

const String _blockHeader = 'Referenced with # in Vicoa:';

/// The context block appended to the outgoing message.
///
/// Sent as text rather than resolved by the agent on demand: the agent may
/// have no Vicoa CLI on its PATH, and a reference the user typed is context
/// they have already decided is relevant.
String buildReferenceBlock(List<ComposerReference> refs) {
  final blocks = refs
      .map((ref) => ref.context.trim())
      .where((block) => block.isNotEmpty)
      .toList();
  if (blocks.isEmpty) return '';
  return [_blockHeader, '', blocks.join('\n\n')].join('\n');
}

/// Typed text + reference blocks, in the order the agent reads.
String composeOutgoingMessage(String body, List<ComposerReference> refs) {
  final block = buildReferenceBlock(refs);
  if (block.isEmpty) return body;
  return body.isNotEmpty ? '$body\n\n---\n$block' : block;
}

/// The task a send should file the session under, or null.
///
/// One task, because `agent_instances.task_id` is a single column. The
/// *first* referenced task wins, and an existing link is never overwritten:
/// silently re-filing someone's session is the one failure mode here that
/// loses data the UI doesn't show.
String? taskLinkForSend(List<ComposerReference> refs, String? currentTaskId) {
  if (currentTaskId != null && currentTaskId.isNotEmpty) return null;
  for (final ref in refs) {
    if (ref.kind == 'task') return ref.id;
  }
  return null;
}

/// The `#` picker's state for one composer: the panel (query → candidates)
/// and the references picked into the current draft.
///
/// The `@` panel filters a local file index; this one asks the server on
/// every (debounced) keystroke, because sessions, tasks and automations only
/// live there and change while you type.
mixin ComposerReferenceMixin {
  List<ReferenceCandidate> referenceCandidates = [];
  bool showReferenceSuggestions = false;
  bool isLoadingReferences = false;

  /// The backend has no `/references` route (an older deployment). The `#`
  /// trigger then stays inert rather than opening an empty panel every time.
  bool referencesUnavailable = false;

  /// Bumped on every panel or pick change; the chat page gates its rebuilds
  /// on it, the way it does on `fileMentionSuggestionsRevision`.
  int referenceRevision = 0;

  /// `#` picks for the next message. Not persisted with the draft: the token
  /// survives as plain text, the attached context does not, which is better
  /// than silently re-attaching context the user can no longer see.
  List<ComposerReference> pendingReferences = [];

  static const Duration referenceDebounce = Duration(milliseconds: 150);

  Timer? _referenceDebounceTimer;
  int _referenceQuerySequence = 0;
  String? _referenceQuery;

  TextEditingController get referenceTextController;
  VoidCallback? get referenceOnStateChanged;

  /// Whether `#` opens the picker on this composer. The chat turns it off for
  /// a session the viewer doesn't own: the candidates are the viewer's own
  /// things, and a task link would re-file someone else's session.
  bool get referencesEnabled => true;

  /// The session doing the referencing; dropped from the candidates.
  String? get referenceExcludeSessionId => null;

  /// Seam for tests. Throws [actions.ApiException] as the request does.
  Future<List<ReferenceCandidate>> fetchReferenceCandidates(
      String query) async {
    final items = await actions.apiListReferences(query,
        excludeSessionId: referenceExcludeSessionId);
    return items.map(ReferenceCandidate.fromJson).toList();
  }

  /// Seam for tests. Null when the expansion failed.
  Future<ComposerReference?> fetchReferenceDetail(
      String kind, String id) async {
    final json = await actions.apiGetReference(kind, id);
    return json == null ? null : ComposerReference.fromDetail(json);
  }

  void _notifyReferences() {
    referenceRevision++;
    referenceOnStateChanged?.call();
  }

  int _referenceCaret(String text) {
    final selection = referenceTextController.selection;
    return selection.isValid && selection.baseOffset >= 0
        ? selection.baseOffset.clamp(0, text.length)
        : text.length;
  }

  /// Open, update or close the panel for the caret's position in [text].
  void filterReferences(String text) {
    if (!referencesEnabled || referencesUnavailable) {
      hideReferenceSuggestions();
      return;
    }
    final token = detectTriggerToken(text, _referenceCaret(text), '#');
    if (token == null) {
      hideReferenceSuggestions();
      return;
    }
    if (showReferenceSuggestions && token.query == _referenceQuery) return;

    _referenceQuery = token.query;
    final sequence = ++_referenceQuerySequence;
    _referenceDebounceTimer?.cancel();
    // Open right away on the previous rows (or "Searching…"), so the panel
    // doesn't blank between keystrokes while the request is in flight.
    showReferenceSuggestions = true;
    isLoadingReferences = true;
    _notifyReferences();

    _referenceDebounceTimer = Timer(referenceDebounce, () async {
      try {
        final items = await fetchReferenceCandidates(token.query);
        if (sequence != _referenceQuerySequence) return;
        referenceCandidates = items;
      } on actions.ApiException catch (e) {
        if (sequence != _referenceQuerySequence) return;
        if (e.statusCode == 404) {
          referencesUnavailable = true;
          hideReferenceSuggestions();
          return;
        }
        referenceCandidates = [];
      } catch (e) {
        if (sequence != _referenceQuerySequence) return;
        debugPrint('Error loading # references: $e');
        referenceCandidates = [];
      }
      isLoadingReferences = false;
      _notifyReferences();
    });
  }

  /// Close the panel and drop its rows, so reopening `#` never flashes the
  /// previous matches before the new request lands.
  void hideReferenceSuggestions() {
    _referenceDebounceTimer?.cancel();
    _referenceQuerySequence++;
    _referenceQuery = null;
    final changed = showReferenceSuggestions ||
        referenceCandidates.isNotEmpty ||
        isLoadingReferences;
    showReferenceSuggestions = false;
    referenceCandidates = [];
    isLoadingReferences = false;
    if (changed) _notifyReferences();
  }

  /// A row was picked: swap the partial `#` token for the row's token, record
  /// the reference from what the panel already knew, then upgrade it in place
  /// when the full block arrives (a failed fetch keeps the one-line fallback).
  void insertReference(ReferenceCandidate item) {
    final text = referenceTextController.text;
    final token = detectTriggerToken(text, _referenceCaret(text), '#');
    final next = token != null
        ? replaceTriggerToken(text, token, '#', item.token)
        : (
            text: '$text#${item.token} ',
            cursor: text.length + item.token.length + 2,
          );
    referenceTextController.value = TextEditingValue(
      text: next.text,
      selection: TextSelection.collapsed(offset: next.cursor),
    );
    pendingReferences = addReference(
      pendingReferences,
      ComposerReference.fromCandidate(item),
    );
    hideReferenceSuggestions();
    _notifyReferences();

    unawaited(fetchReferenceDetail(item.kind, item.id).then((detail) {
      bool same(ComposerReference ref) =>
          detail != null && ref.kind == detail.kind && ref.id == detail.id;
      // Gone already (the draft was sent or the pick replaced): nothing to do.
      if (!pendingReferences.any(same)) return;
      pendingReferences = [
        for (final ref in pendingReferences) same(ref) ? detail! : ref,
      ];
      _notifyReferences();
    }));
  }

  /// The picks whose token is still in [text]: what a send would attach.
  List<ComposerReference> liveReferences(String text) =>
      activeReferences(pendingReferences, text.trim());

  /// The referenced task a send would file this session under, for the hint
  /// above the composer. Null when nothing would be linked.
  ComposerReference? pendingTaskLink(String text, String? currentTaskId) {
    final refs = liveReferences(text);
    final taskId = taskLinkForSend(refs, currentTaskId);
    if (taskId == null) return null;
    for (final ref in refs) {
      if (ref.kind == 'task' && ref.id == taskId) return ref;
    }
    return null;
  }

  /// Forget the picks (after a send). The panel closes too.
  void clearPendingReferences() {
    final hadRefs = pendingReferences.isNotEmpty;
    pendingReferences = [];
    hideReferenceSuggestions();
    if (hadRefs) _notifyReferences();
  }

  void disposeComposerReferenceMixin() {
    _referenceDebounceTimer?.cancel();
    _referenceDebounceTimer = null;
  }
}
