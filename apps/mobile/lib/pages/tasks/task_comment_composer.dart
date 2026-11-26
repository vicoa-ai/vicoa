import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/principal_avatar/principal_avatar.dart';
import '/custom_code/utils/composer_references.dart' show detectTriggerToken, replaceTriggerToken, TriggerToken;
import '/custom_code/utils/task_mentions.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/agent_chat/components/composer_primary_button.dart';
import 'dashed_border.dart';
import 'task_surface.dart';
import 'task_timeline_text.dart';

/// What the composer is aimed at.
enum TaskComposerTarget { comment, reply, edit }

/// The task sheet's one comment box, pinned above the keyboard (see rule 5 in
/// `task_timeline_view.dart` for why there is one box rather than one per
/// thread). By default it starts a new thread; a thread's "Leave a reply…" row
/// aims it at that thread, and a comment's Edit loads that comment into it.
///
/// Like the web's comment box: `@` opens a picker of the viewer's agents and
/// the people who can see the task. A pick writes plain `@Name`, which only
/// becomes the mention link on send, and deleting the name drops it.
/// Mentioning an agent asks it to answer; mentioning a person only tells them.
/// A hint under the box says which agents sending would wake, mirroring the
/// server's routing, so a comment never starts a run by surprise. A comment
/// starting with `/note` wakes nobody; the box tints and the hint says so.
///
/// Return sends nothing on a phone: it breaks the line, as in every other
/// multi-line box, and the arrow button posts.
class TaskCommentComposer extends StatefulWidget {
  const TaskCommentComposer({
    super.key,
    required this.controller,
    required this.focusNode,
    required this.target,
    required this.targetName,
    required this.wake,
    required this.agents,
    required this.people,
    required this.agentNames,
    required this.viewerId,
    required this.onSubmit,
    required this.onClearTarget,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final TaskComposerTarget target;

  /// Whom a reply answers (the thread root's author), for its header.
  final String? targetName;

  /// Where a comment from this box goes (null while editing: an edit wakes no
  /// one).
  final WakeContext? wake;

  /// Agents an `@` can mention (the viewer's own, live ones).
  final List<dynamic> agents;

  /// People an `@` can mention: who can see the task.
  final List<dynamic> people;

  /// Agent names by lower-cased id, for the hint.
  final Map<String, String> agentNames;
  final String? viewerId;

  /// Post the body; true when it landed (the box then clears).
  final Future<bool> Function(String body) onSubmit;

  /// Drop the reply or edit target and go back to a new thread.
  final VoidCallback onClearTarget;

  @override
  State<TaskCommentComposer> createState() => _TaskCommentComposerState();
}

class _Candidate {
  const _Candidate({required this.kind, required this.id, required this.name, required this.principal});
  final String kind;
  final String id;
  final String name;
  final Map<String, dynamic> principal;
}

const int _kMentionLimit = 5;

class _TaskCommentComposerState extends State<TaskCommentComposer> {
  List<PickedMention> _picks = [];
  TriggerToken? _mention;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChanged);
    widget.focusNode.addListener(_onChanged);
  }

  @override
  void didUpdateWidget(TaskCommentComposer old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_onChanged);
      widget.controller.addListener(_onChanged);
    }
    if (old.focusNode != widget.focusNode) {
      old.focusNode.removeListener(_onChanged);
      widget.focusNode.addListener(_onChanged);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChanged);
    widget.focusNode.removeListener(_onChanged);
    super.dispose();
  }

  /// Agents first (a mention there starts work), then the people on the
  /// board, the viewer left out.
  List<_Candidate> get _candidates {
    final out = <_Candidate>[];
    for (final a in widget.agents) {
      final id = (a is Map ? a['id'] : null)?.toString() ?? '';
      final name = (a is Map ? a['name'] : null)?.toString().trim() ?? '';
      if (id.isEmpty || name.isEmpty) continue;
      out.add(_Candidate(kind: 'agent', id: id, name: name, principal: {'type': 'agent', 'id': id, 'name': name, 'avatar_image_uri': a['avatar_image_uri'], 'emoji': a['emoji'], 'updated_at': a['updated_at']}));
    }
    for (final p in widget.people) {
      final id = tutils.principalId(p);
      final name = tutils.principalName(p);
      if (id == null || name == null || id == widget.viewerId) continue;
      out.add(_Candidate(kind: 'user', id: id, name: name, principal: Map<String, dynamic>.from(p as Map)));
    }
    return out;
  }

  List<_Candidate> get _matches {
    final token = _mention;
    if (token == null) return const [];
    final q = token.query.toLowerCase();
    return _candidates.where((c) => c.name.toLowerCase().contains(q)).take(_kMentionLimit).toList();
  }

  void _onChanged() {
    if (!mounted) return;
    final value = widget.controller.value;
    final cursor = value.selection.isValid ? value.selection.baseOffset : value.text.length;
    final token = widget.focusNode.hasFocus && widget.target != TaskComposerTarget.edit ? detectTriggerToken(value.text, cursor, '@') : null;
    setState(() => _mention = token);
  }

  void _choose(_Candidate c) {
    final token = _mention;
    if (token == null) return;
    final next = replaceTriggerToken(widget.controller.text, token, '@', mentionToken(c.name).substring(1));
    _picks = [..._picks.where((p) => p.id != c.id), PickedMention(id: c.id, name: c.name, kind: c.kind)];
    widget.controller.value = TextEditingValue(text: next.text, selection: TextSelection.collapsed(offset: next.cursor));
    HapticFeedback.selectionClick();
  }

  String _outgoing(String text) => serializeMentions(text, activeMentions(_picks, text));

  Future<void> _send() async {
    final typed = widget.controller.text;
    final body = _outgoing(typed).trim();
    if (body.isEmpty || _sending) return;
    setState(() => _sending = true);
    final ok = await widget.onSubmit(body);
    if (!mounted) return;
    setState(() {
      _sending = false;
      if (ok) {
        _picks = [];
        _mention = null;
      }
    });
    // Only what was sent: finishing an edit puts the displaced draft back,
    // and that must survive.
    if (ok && widget.controller.text == typed) widget.controller.clear();
  }

  List<String> _wakeNames(String text) {
    final wake = widget.wake;
    if (wake == null) return const [];
    final ids = agentsToWake(text.trim().isEmpty ? '.' : _outgoing(text), wake);
    return [for (final id in ids) if ((widget.agentNames[id] ?? '').isNotEmpty) widget.agentNames[id]!];
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final text = widget.controller.text;
    final empty = text.trim().isEmpty;
    final editing = widget.target == TaskComposerTarget.edit;
    final note = !editing && isNoteComment(text);
    final names = _wakeNames(text);
    final focused = widget.focusNode.hasFocus;
    final answering = (widget.wake?.askers ?? const []).isNotEmpty;

    // Hint copy is secondary: only while typing here, whole sentences. An
    // empty box says whom it is for in its placeholder instead.
    String? hint;
    if (focused && !empty && !editing) {
      if (note) {
        hint = l10n.tasksNoteHint;
      } else if (names.isNotEmpty) {
        hint = l10n.tasksWakeHint(joinNames(l10n, names));
      }
    }
    final baseNames = editing ? const <String>[] : _wakeNames('');
    final placeholder = baseNames.isNotEmpty
        ? ((widget.target == TaskComposerTarget.reply || answering) ? l10n.tasksReplyToNames(joinNames(l10n, baseNames)) : l10n.tasksCommentForNames(joinNames(l10n, baseNames)))
        : (widget.target == TaskComposerTarget.reply ? l10n.tasksReplyPlaceholder : l10n.tasksCommentPlaceholder);
    final matches = _matches;

    final style = theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.primaryText, fontSize: 15.0, letterSpacing: 0.0);
    final small = theme.labelSmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 12.5, letterSpacing: 0.0);

    // Laid out like the chat page's composer: no rule above it, the box
    // inset from the sheet's edges, the same surface and the same button.
    return Container(
      color: theme.secondaryBackground,
      padding: const EdgeInsets.fromLTRB(8.0, 6.0, 8.0, 8.0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.target != TaskComposerTarget.comment)
            Padding(
              padding: const EdgeInsets.only(bottom: 6.0, left: 4.0),
              child: Row(
                children: [
                  Icon(editing ? Icons.edit_outlined : Icons.reply_rounded, size: 15.0, color: theme.secondaryText),
                  const SizedBox(width: 6.0),
                  Expanded(
                    child: Text(
                      editing ? l10n.tasksEditingComment : l10n.tasksReplyingTo(widget.targetName ?? ''),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: small.copyWith(color: theme.primaryText),
                    ),
                  ),
                  InkWell(
                    borderRadius: BorderRadius.circular(12.0),
                    onTap: widget.onClearTarget,
                    child: Padding(padding: const EdgeInsets.all(4.0), child: Icon(Icons.close_rounded, size: 16.0, color: theme.secondaryText)),
                  ),
                ],
              ),
            ),
          if (matches.isNotEmpty)
            Container(
              margin: const EdgeInsets.only(bottom: 6.0),
              decoration: taskChatSurface(theme, radius: 16.0),
              child: Column(
                children: [
                  for (final c in matches)
                    InkWell(
                      onTap: () => _choose(c),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 9.0),
                        child: Row(
                          children: [
                            PrincipalAvatar.fromResponse(c.principal, size: PrincipalAvatarSize.sm),
                            const SizedBox(width: 10.0),
                            Expanded(child: Text(c.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: style.copyWith(fontSize: 14.5))),
                            if (c.kind == 'agent') Text(l10n.tasksAgentBadge, style: small.copyWith(fontSize: 11.0)),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ),
          Row(
            // Keyed: the picker and the hint appear around this row, often
            // both at once on the `@` that opens them. Matched by position it
            // would be rebuilt, and the new field has no keyboard.
            key: const ValueKey('composer-input'),
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                // A note reads as an aside before it is even sent: the box
                // sinks into the sheet inside a dashed outline, as on the web.
                // The CustomPaint is always there so the field is never rebuilt.
                child: CustomPaint(
                  foregroundPainter: note ? DashedBorderPainter(color: theme.secondaryText.withValues(alpha: 0.7), radius: 24.0) : null,
                  child: Container(
                    padding: const EdgeInsetsDirectional.fromSTEB(14.0, 4.0, 4.0, 4.0),
                    decoration: note
                        ? BoxDecoration(borderRadius: BorderRadius.circular(24.0), border: Border.all(color: Colors.transparent, width: 1.0))
                        : taskChatSurface(theme, radius: 24.0),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Expanded(
                          child: TextField(
                      controller: widget.controller,
                      focusNode: widget.focusNode,
                      minLines: 1,
                      maxLines: 5,
                      keyboardType: TextInputType.multiline,
                      textCapitalization: TextCapitalization.sentences,
                      style: style,
                      decoration: InputDecoration(
                        isDense: true,
                        border: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(vertical: 10.0),
                        hintText: placeholder,
                        hintStyle: style.copyWith(color: theme.secondaryText.withValues(alpha: 0.6)),
                      ),
                          ),
                        ),
                        const SizedBox(width: 6.0),
                        // The chat composer's own Send button.
                        ComposerPrimaryButton(
                          isSending: _sending,
                          showStop: false,
                          onStop: () {},
                          onSend: () {
                            if (empty) return;
                            HapticFeedback.mediumImpact();
                            _send();
                          },
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
          if (hint != null)
            Padding(
              padding: const EdgeInsets.only(top: 4.0, left: 6.0, right: 40.0),
              child: Text(hint, style: small.copyWith(fontSize: 11.5, color: theme.secondaryText.withValues(alpha: 0.6))),
            ),
        ],
      ),
    );
  }
}
