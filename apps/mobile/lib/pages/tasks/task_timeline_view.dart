import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/components/principal_avatar/principal_avatar.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/task_mentions.dart';
import '/custom_code/utils/task_questions.dart';
import '/custom_code/utils/task_timeline.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/custom_functions.dart' as functions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/home/session_card_text.dart';
import 'task_markdown.dart';
import 'task_people.dart';
import 'task_reactions.dart';
import 'task_timeline_text.dart';

// The task timeline on the phone: comments, generated activity and agent
// sessions in one chronological stream, oldest first. It keeps the web's
// rules (apps/web/app/dashboard/tasks/[taskId]/task-timeline.tsx):
//
// 1. ONE COLUMN. Every row puts its avatar or agent mark at the same x, at the
//    same size, so the stream reads down one edge.
// 2. ONE SURFACE PER THREAD. A root and its replies share a single card with
//    dividers, rather than each comment floating in its own bubble.
// 3. SESSIONS ABSORB THEIR OWN NOISE. A session's status hops fold into its
//    card instead of being listed three times.
// 4. A THREAD SITS WHERE IT STARTED, AND NEVER INDENTS. Replies are one level
//    deep (the server guarantees it), a single ordered chain under the root,
//    so an indent would encode a depth that cannot exist. The thread is placed
//    at its root's time, so a late answer sits next to what it answers.
//
// One deliberate difference, rule 5. On the web every thread ends in its own
// reply box. On a phone a text field inside a scrolling sheet fights the
// keyboard for the same pixels, and two places to type compete. So every
// thread ends in an always-visible "Leave a reply…" row (still no hidden
// affordance), and a tap on it points the sheet's one composer, pinned above
// the keyboard, at that thread. Editing a comment takes the same box.
//
// Your own comments carry a ⋯ menu (Edit, Delete). With no hover on a touch
// screen it is always visible, as on the web's touch layout.

/// What a timeline row may do; null callbacks hide the control (a viewer who
/// can't comment sees reactions and threads but nothing to press).
class TaskTimelineActions {
  const TaskTimelineActions({this.onToggleReaction, this.onReply, this.onEdit, this.onDelete, required this.onOpenSession});

  final void Function(String commentId, String emoji)? onToggleReaction;
  final void Function(TaskThread thread)? onReply;
  final void Function(dynamic comment)? onEdit;
  final void Function(dynamic comment)? onDelete;

  /// Open a session from a "via" line or a session card.
  final void Function(String sessionId) onOpenSession;
}

class TaskTimelineView extends StatelessWidget {
  const TaskTimelineView({
    super.key,
    required this.entries,
    required this.viewer,
    required this.sessionRefs,
    required this.actions,
    this.replyingToRootId,
  });

  final List<TimelineEntry> entries;
  final TaskViewer? viewer;
  final Map<String, Map<String, dynamic>> sessionRefs;
  final TaskTimelineActions actions;

  /// The thread the composer is replying in, drawn as the active one.
  final String? replyingToRootId;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final entry in entries)
          Padding(
            key: ValueKey(entry.id),
            padding: const EdgeInsets.only(bottom: 8.0),
            child: switch (entry) {
              ThreadEntry(:final thread) => _ThreadCard(
                  thread: thread,
                  viewer: viewer,
                  sessionRefs: sessionRefs,
                  actions: actions,
                  replying: replyingToRootId == tutils.commentId(thread.root),
                ),
              ActivityRunEntry(:final rows) => _ActivityRun(rows: rows, viewer: viewer, sessionRefs: sessionRefs, onOpenSession: actions.onOpenSession),
              SessionEntry(:final session, :final absorbed) => _SessionCard(session: session, absorbed: absorbed, onOpenSession: actions.onOpenSession),
            },
          ),
      ],
    );
  }
}

TextStyle _text(FlutterFlowTheme theme, {Color? color, double size = 13.0, FontWeight weight = FontWeight.w400, FontStyle? style}) =>
    theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: color ?? theme.primaryText, fontSize: size, letterSpacing: 0.0, fontWeight: weight, fontStyle: style);

BoxDecoration _card(FlutterFlowTheme theme, {bool highlight = false}) => BoxDecoration(
      color: theme.primaryBackground,
      borderRadius: BorderRadius.circular(12.0),
      border: Border.all(color: highlight ? theme.secondaryText.withValues(alpha: 0.5) : theme.alternate, width: 1.0),
    );

/// Horizontal inset of every row, cards and bare lines alike (rule 1).
const double _kRowInset = 12.0;

class _ThreadCard extends StatelessWidget {
  const _ThreadCard({required this.thread, required this.viewer, required this.sessionRefs, required this.actions, required this.replying});

  final TaskThread thread;
  final TaskViewer? viewer;
  final Map<String, Map<String, dynamic>> sessionRefs;
  final TaskTimelineActions actions;
  final bool replying;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final divider = Divider(height: 1.0, thickness: 1.0, color: theme.alternate);
    return Container(
      decoration: _card(theme, highlight: replying),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _CommentBlock(comment: thread.root, viewer: viewer, sessionRefs: sessionRefs, actions: actions),
          // Not indented (rule 4).
          for (final reply in thread.replies) ...[
            divider,
            _CommentBlock(comment: reply, viewer: viewer, sessionRefs: sessionRefs, actions: actions),
          ],
          if (actions.onReply != null) ...[
            divider,
            InkWell(
              borderRadius: const BorderRadius.vertical(bottom: Radius.circular(12.0)),
              onTap: () {
                HapticFeedback.selectionClick();
                actions.onReply!(thread);
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: _kRowInset, vertical: 10.0),
                child: Row(
                  children: [
                    if (viewer != null) PrincipalAvatar.fromResponse(viewer!.toPrincipal(), size: PrincipalAvatarSize.xs) else const SizedBox(width: 16.0),
                    const SizedBox(width: 8.0),
                    Expanded(
                      child: Text(
                        replying ? l10n.tasksReplyingTo(principalDisplayName(l10n, tutils.commentAuthor(thread.root), viewer)) : l10n.tasksReplyPlaceholder,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: _text(theme, color: replying ? theme.primaryText : theme.secondaryText.withValues(alpha: 0.7), size: 13.5),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _CommentBlock extends StatelessWidget {
  const _CommentBlock({required this.comment, required this.viewer, required this.sessionRefs, required this.actions});

  final dynamic comment;
  final TaskViewer? viewer;
  final Map<String, Map<String, dynamic>> sessionRefs;
  final TaskTimelineActions actions;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final author = tutils.commentAuthor(comment);
    final body = tutils.commentBody(comment);
    final viaId = tutils.commentAgentInstanceId(comment);
    final via = viaId == null ? null : sessionRefs[viaId];
    // Only the author may rewrite or remove a comment (the server holds the
    // same line). A comment an agent posted with your key is the agent's.
    final mine = body != null && viewer != null && tutils.principalType(author) == 'user' && tutils.principalId(author) == viewer!.id;
    final canEdit = mine && actions.onEdit != null;
    final canDelete = mine && actions.onDelete != null;
    // A `/note` (it woke nobody) reads as an aside: the prefix is the
    // instruction, not the content, so a badge replaces it.
    final note = body != null && isNoteComment(body);
    final shown = body != null && note ? stripNotePrefix(body) : body;
    final question = openQuestion(comment);
    final isAgent = tutils.principalType(author) == 'agent';
    final hasMeta = question != null || via != null || tutils.commentEditedAt(comment) != null;
    final locale = Localizations.localeOf(context).toLanguageTag();

    return Padding(
      padding: const EdgeInsets.fromLTRB(_kRowInset, 10.0, 4.0, 10.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              PrincipalAvatar.fromResponse(author, size: PrincipalAvatarSize.xs),
              const SizedBox(width: 8.0),
              // The name is the one part that gives way; the badges and the
              // time keep their width.
              Expanded(
                child: Row(
                  children: [
                    Flexible(
                      child: Text(principalDisplayName(l10n, author, viewer), maxLines: 1, overflow: TextOverflow.ellipsis, style: _text(theme, size: 13.5, weight: FontWeight.w600)),
                    ),
                    if (isAgent) ...[const SizedBox(width: 6.0), _Badge(label: l10n.tasksAgentBadge)],
                    if (note) ...[const SizedBox(width: 6.0), _Badge(label: l10n.tasksNoteBadge, dashed: true)],
                    const SizedBox(width: 8.0),
                    Text(timelineTimeLabel(tutils.commentCreatedAt(comment), locale), style: _text(theme, color: theme.secondaryText, size: 12.0)),
                  ],
                ),
              ),
              if (canEdit || canDelete)
                _CommentMenu(onEdit: canEdit ? () => actions.onEdit!(comment) : null, onDelete: canDelete ? () => actions.onDelete!(comment) : null)
              else
                const SizedBox(height: 28.0),
            ],
          ),
          if (hasMeta)
            Padding(
              padding: const EdgeInsets.only(top: 2.0, right: 8.0),
              child: Wrap(
                spacing: 8.0,
                runSpacing: 4.0,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  // An agent's question that still waits: "Waiting on Nick".
                  if (question != null) WaitingOnPill(people: [question['addressee']], viewerId: viewer?.id),
                  if (via != null) _ViaLink(sessionRef: via, onOpen: actions.onOpenSession),
                  if (tutils.commentEditedAt(comment) != null) Text(l10n.tasksCommentEdited, style: _text(theme, color: theme.secondaryText.withValues(alpha: 0.6), size: 12.0)),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.only(top: 6.0, right: 8.0),
            child: shown == null
                // The tombstone stays: its replies are still under it, and a
                // thread with a hole where its opening post was is unreadable.
                ? Text(l10n.tasksCommentDeletedBody, style: _text(theme, color: theme.secondaryText.withValues(alpha: 0.6), size: 14.0, style: FontStyle.italic))
                : Opacity(opacity: note ? 0.75 : 1.0, child: TaskMarkdown(shown)),
          ),
          if (body != null && (tutils.commentReactions(comment).isNotEmpty || actions.onToggleReaction != null))
            Padding(
              padding: const EdgeInsets.only(top: 8.0, right: 8.0),
              child: TaskReactionRow(
                reactions: tutils.commentReactions(comment),
                viewer: viewer,
                onToggle: actions.onToggleReaction == null ? null : (emoji) => actions.onToggleReaction!(tutils.commentId(comment), emoji),
              ),
            ),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, this.dashed = false});

  final String label;
  final bool dashed;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5.0, vertical: 1.0),
      decoration: BoxDecoration(
        color: dashed ? null : theme.alternate.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(4.0),
        border: dashed ? Border.all(color: theme.alternate) : null,
      ),
      child: Text(label, style: _text(theme, color: theme.secondaryText, size: 10.5)),
    );
  }
}

class _CommentMenu extends StatelessWidget {
  const _CommentMenu({this.onEdit, this.onDelete});

  final VoidCallback? onEdit;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    return SizedBox(
      width: 32.0,
      height: 28.0,
      child: PopupMenuButton<String>(
        padding: EdgeInsets.zero,
        iconSize: 18.0,
        icon: Icon(Icons.more_horiz_rounded, color: theme.secondaryText, size: 18.0),
        color: theme.secondaryBackground,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12.0), side: BorderSide(color: theme.alternate)),
        onSelected: (v) => v == 'edit' ? onEdit?.call() : onDelete?.call(),
        itemBuilder: (_) => [
          if (onEdit != null)
            PopupMenuItem(
              value: 'edit',
              height: 40.0,
              child: Row(children: [Icon(Icons.edit_outlined, size: 18.0, color: theme.primaryText), const SizedBox(width: 10.0), Text(l10n.tasksCommentEditAction, style: _text(theme, size: 14.0))]),
            ),
          if (onDelete != null)
            PopupMenuItem(
              value: 'delete',
              height: 40.0,
              child: Row(children: [Icon(Icons.delete_outline_rounded, size: 18.0, color: theme.error), const SizedBox(width: 10.0), Text(l10n.tasksCommentDeleteAction, style: _text(theme, color: theme.error, size: 14.0))]),
            ),
        ],
      ),
    );
  }
}

/// "via <session>" after a byline: the session a comment or change came
/// from. Only for a session the viewer may open (the timeline's refs).
class _ViaLink extends StatelessWidget {
  const _ViaLink({required this.sessionRef, required this.onOpen});

  final Map<String, dynamic> sessionRef;
  final void Function(String sessionId) onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => onOpen(sessionRef['id'].toString()),
      child: Text(
        l10n.tasksVia(sessionRefTitle(l10n, sessionRef)),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: _text(theme, color: theme.secondaryText, size: 12.0).copyWith(decoration: TextDecoration.underline, decorationColor: theme.secondaryText.withValues(alpha: 0.4)),
      ),
    );
  }
}

class _ActivityLine extends StatelessWidget {
  const _ActivityLine({required this.row, required this.viewer, required this.sessionRefs, required this.onOpenSession, this.inset = true});

  final dynamic row;
  final TaskViewer? viewer;
  final Map<String, Map<String, dynamic>> sessionRefs;
  final void Function(String sessionId) onOpenSession;
  final bool inset;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final actor = tutils.activityActor(row);
    final viaId = tutils.activityAgentInstanceId(row);
    final via = viaId == null ? null : sessionRefs[viaId];
    final locale = Localizations.localeOf(context).toLanguageTag();
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: inset ? _kRowInset : 8.0, vertical: 4.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(padding: const EdgeInsets.only(top: 1.0), child: PrincipalAvatar.fromResponse(actor, size: PrincipalAvatarSize.xs)),
          const SizedBox(width: 8.0),
          Expanded(
            child: Wrap(
              spacing: 6.0,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text.rich(
                  TextSpan(children: [
                    TextSpan(text: principalDisplayName(l10n, actor, viewer), style: _text(theme, color: theme.primaryText.withValues(alpha: 0.75), size: 12.5, weight: FontWeight.w500)),
                    TextSpan(text: ' ${activityText(l10n, row)}'),
                  ]),
                  style: _text(theme, color: theme.secondaryText, size: 12.5),
                ),
                if (via != null) _ViaLink(sessionRef: via, onOpen: onOpenSession),
                Text(timelineTimeLabel(tutils.activityCreatedAt(row), locale), style: _text(theme, color: theme.secondaryText.withValues(alpha: 0.6), size: 12.0)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ActivityRun extends StatefulWidget {
  const _ActivityRun({required this.rows, required this.viewer, required this.sessionRefs, required this.onOpenSession});

  final List<dynamic> rows;
  final TaskViewer? viewer;
  final Map<String, Map<String, dynamic>> sessionRefs;
  final void Function(String sessionId) onOpenSession;

  @override
  State<_ActivityRun> createState() => _ActivityRunState();
}

class _ActivityRunState extends State<_ActivityRun> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    if (widget.rows.length == 1) {
      return _ActivityLine(row: widget.rows.first, viewer: widget.viewer, sessionRefs: widget.sessionRefs, onOpenSession: widget.onOpenSession);
    }
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final actors = <String>[];
    for (final row in widget.rows) {
      final name = principalDisplayName(l10n, tutils.activityActor(row), widget.viewer);
      if (!actors.contains(name)) actors.add(name);
    }
    final locale = Localizations.localeOf(context).toLanguageTag();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        InkWell(
          borderRadius: BorderRadius.circular(8.0),
          onTap: () => setState(() => _open = !_open),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: _kRowInset, vertical: 4.0),
            child: Row(
              children: [
                PrincipalAvatar.fromResponse(tutils.activityActor(widget.rows.first), size: PrincipalAvatarSize.xs),
                const SizedBox(width: 8.0),
                Flexible(
                  child: Text.rich(
                    TextSpan(children: [
                      TextSpan(text: actors.join(' & '), style: _text(theme, color: theme.primaryText.withValues(alpha: 0.75), size: 12.5, weight: FontWeight.w500)),
                      TextSpan(text: ' ${l10n.tasksActivityRun(widget.rows.length)}'),
                    ]),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: _text(theme, color: theme.secondaryText, size: 12.5),
                  ),
                ),
                const SizedBox(width: 6.0),
                Text(timelineTimeLabel(tutils.activityCreatedAt(widget.rows.first), locale), style: _text(theme, color: theme.secondaryText.withValues(alpha: 0.6), size: 12.0)),
                AnimatedRotation(
                  turns: _open ? 0.5 : 0.0,
                  duration: const Duration(milliseconds: 150),
                  child: Icon(Icons.keyboard_arrow_down_rounded, size: 18.0, color: theme.secondaryText),
                ),
              ],
            ),
          ),
        ),
        if (_open)
          Container(
            margin: const EdgeInsets.only(left: _kRowInset + 7.0, top: 2.0),
            decoration: BoxDecoration(border: Border(left: BorderSide(color: theme.alternate, width: 1.0))),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final row in widget.rows) _ActivityLine(row: row, viewer: widget.viewer, sessionRefs: widget.sessionRefs, onOpenSession: widget.onOpenSession, inset: false),
              ],
            ),
          ),
      ],
    );
  }
}

/// A session filed under the task is running: ACTIVE and still reachable.
/// `status` freezes at ACTIVE when an agent dies, so the server's liveness
/// gates it, as on Home.
bool taskSessionIsLive(dynamic session) {
  if (session is! Map) return false;
  final live = session['live_state']?.toString();
  return session['status'] == 'ACTIVE' && (live == null || actions.liveStateIsReachable(live));
}

/// A finished session: its mark greys out, as in the web's `CLOSED_STATUSES`.
/// The mark never wears Home's spinning ring here: the ring is 26 px wider
/// than the mark and would push a live row out of the column.
bool taskSessionIsClosed(dynamic session) => session is Map && const {'COMPLETED', 'FAILED', 'KILLED', 'DELETED', 'DISCONNECTED'}.contains(session['status']);

/// A session's title as Home's card shows it.
String taskSessionTitle(dynamic session) => session is Map ? sessionCardRow1(Map<String, dynamic>.from(session)) : '';

/// Last activity, short ("5m", "Nov 3"), as Home's card shows it.
String taskSessionTime(dynamic session) {
  final raw = (session is Map ? (session['latest_message_at'] ?? session['started_at']) : null)?.toString() ?? '';
  final t = DateTime.tryParse(raw);
  return t == null ? '' : functions.formatRelativeTimeShort(t.toLocal());
}

class _SessionCard extends StatefulWidget {
  const _SessionCard({required this.session, required this.absorbed, required this.onOpenSession});

  final dynamic session;
  final List<dynamic> absorbed;
  final void Function(String sessionId) onOpenSession;

  @override
  State<_SessionCard> createState() => _SessionCardState();
}

class _SessionCardState extends State<_SessionCard> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final s = widget.session as Map;
    final live = taskSessionIsLive(s);
    final id = s['id']?.toString() ?? '';
    return Container(
      decoration: _card(theme),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(12.0),
            onTap: id.isEmpty ? null : () => widget.onOpenSession(id),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(_kRowInset, 10.0, 8.0, 10.0),
              child: Row(
                children: [
                  AgentTypeIconWidget(agentTypeName: s['agent_type_name']?.toString(), size: 16.0, muted: taskSessionIsClosed(s)),
                  const SizedBox(width: 10.0),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(taskSessionTitle(s), maxLines: 1, overflow: TextOverflow.ellipsis, style: _text(theme, size: 14.0, weight: FontWeight.w500)),
                        const SizedBox(height: 2.0),
                        Row(
                          children: [
                            if (live) ...[
                              Container(width: 6.0, height: 6.0, decoration: BoxDecoration(color: theme.primaryText, shape: BoxShape.circle)),
                              const SizedBox(width: 4.0),
                              Text(l10n.tasksSessionRunning, style: _text(theme, color: theme.primaryText, size: 12.0, weight: FontWeight.w500)),
                            ] else
                              Text((s['status']?.toString() ?? '').toLowerCase(), style: _text(theme, color: theme.secondaryText, size: 12.0)),
                            Text('  ·  ${taskSessionTime(s)}', style: _text(theme, color: theme.secondaryText, size: 12.0)),
                          ],
                        ),
                      ],
                    ),
                  ),
                  Text(l10n.tasksSessionOpen, style: _text(theme, color: theme.secondaryText, size: 12.5)),
                  Icon(Icons.chevron_right_rounded, size: 18.0, color: theme.secondaryText),
                ],
              ),
            ),
          ),
          if (widget.absorbed.isNotEmpty) ...[
            Divider(height: 1.0, thickness: 1.0, color: theme.alternate),
            InkWell(
              borderRadius: const BorderRadius.vertical(bottom: Radius.circular(12.0)),
              onTap: () => setState(() => _open = !_open),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: _kRowInset, vertical: 7.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        AnimatedRotation(turns: _open ? 0.5 : 0.0, duration: const Duration(milliseconds: 150), child: Icon(Icons.keyboard_arrow_down_rounded, size: 16.0, color: theme.secondaryText)),
                        const SizedBox(width: 4.0),
                        Text(l10n.tasksSessionStatusChanges(widget.absorbed.length), style: _text(theme, color: theme.secondaryText.withValues(alpha: 0.8), size: 12.0)),
                      ],
                    ),
                    if (_open)
                      Padding(
                        padding: const EdgeInsets.only(left: 20.0, top: 4.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            for (final row in widget.absorbed)
                              Padding(padding: const EdgeInsets.symmetric(vertical: 2.0), child: Text(activityText(l10n, row), style: _text(theme, color: theme.secondaryText, size: 12.0))),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
