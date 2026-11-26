import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_questions.dart';
import '/custom_code/utils/task_timeline.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/session_actions.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import 'task_chips.dart';
import 'task_comment_composer.dart';
import 'task_detail_model.dart';
import 'task_glyphs.dart';
import 'task_l10n.dart';
import 'task_markdown.dart';
import 'task_people.dart';
import 'task_reactions.dart';
import 'task_session_list.dart';
import 'task_timeline_text.dart';
import 'task_timeline_view.dart';

/// The task detail sheet: an optional parent breadcrumb, the "VIC-42"
/// identifier, title, "Created in <session>", description, reactions on the
/// task, the status/priority/assignee/project/label chips (plus whom an open
/// question waits on and what a dispatched agent is doing), the sub-tasks, the
/// Start session / Edit / Delete row, every related session, and the timeline
/// of comments, activity and session cards, with a comment box pinned at the
/// bottom.
///
/// Stateful because the timeline loads, polls and takes input (see
/// `TaskDetailModel`): it reloads when the app returns to the foreground and
/// every [kTaskDetailPollInterval] while open. No WebSocket channel for tasks.
///
/// Returns the chosen action, or null if dismissed: `start`, `edit`,
/// `delete`, `open:<task id>` (the parent or a sub-task), or
/// `session:<instance id>` (a session to open; the caller brings the sheet
/// back when the chat closes).
Future<String?> showTaskDetailSheet({
  required BuildContext context,
  required dynamic task,
  required dynamic project,
  dynamic parentTask,
  List<dynamic> subtasks = const [],
}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    enableDrag: true,
    builder: (ctx) => TaskDetailSheet(
      task: task,
      project: project,
      parentTask: parentTask,
      subtasks: subtasks,
    ),
  );
}

class TaskDetailSheet extends StatefulWidget {
  const TaskDetailSheet({
    super.key,
    required this.task,
    required this.project,
    required this.parentTask,
    required this.subtasks,
  });

  final dynamic task;
  final dynamic project;
  final dynamic parentTask;
  final List<dynamic> subtasks;

  @override
  State<TaskDetailSheet> createState() => _TaskDetailSheetState();
}

class _TaskDetailSheetState extends State<TaskDetailSheet> with WidgetsBindingObserver {
  late final TaskDetailModel _model;
  final TextEditingController _composer = TextEditingController();
  final FocusNode _composerFocus = FocusNode();
  final ScrollController _scroll = ScrollController();
  Timer? _poll;
  bool _foreground = true;

  /// The thread the composer replies in, or null.
  TaskThread? _replyTo;

  /// The comment the composer is editing, or null.
  dynamic _editing;

  /// What was in the box when an edit took it over, put back when the edit
  /// ends, so editing a comment never costs an unsent draft.
  String? _draftBeforeEdit;

  @override
  void initState() {
    super.initState();
    _model = TaskDetailModel(task: widget.task, project: widget.project);
    _model.setNotify(() {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addObserver(this);
    unawaited(_model.load());
    _poll = Timer.periodic(kTaskDetailPollInterval, (_) {
      if (_foreground) unawaited(_model.load());
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    // Back from another app (or the lock screen): the comment an agent wrote
    // meanwhile should already be there.
    if (_foreground) unawaited(_model.load());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    _model.dispose();
    _composer.dispose();
    _composerFocus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  dynamic get task => _model.task;

  void _openSession(String id) {
    if (id.isEmpty) return;
    Navigator.pop(context, 'session:$id');
  }

  void _snack(String message) => unawaited(SessionActions.showSnack(context, message));

  void _focusComposer() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _composerFocus.requestFocus();
    });
  }

  /// The thread being replied in, as last loaded: a poll replaces the
  /// thread objects, and the wake hint should read the current one.
  TaskThread? get _replyThread {
    final target = _replyTo;
    if (target == null) return null;
    final rootId = tutils.commentId(target.root);
    for (final entry in _model.entries) {
      if (entry is ThreadEntry && tutils.commentId(entry.thread.root) == rootId) return entry.thread;
    }
    return target;
  }

  /// Leave edit mode, putting the draft it displaced back in the box.
  void _endEdit() {
    if (_editing == null) return;
    _editing = null;
    _composer.text = _draftBeforeEdit ?? '';
    _draftBeforeEdit = null;
  }

  void _replyIn(TaskThread thread) {
    setState(() {
      _endEdit();
      _replyTo = thread;
    });
    _focusComposer();
  }

  void _edit(dynamic comment) {
    setState(() {
      if (_editing == null) _draftBeforeEdit = _composer.text;
      _editing = comment;
      _replyTo = null;
    });
    final body = tutils.commentBody(comment) ?? '';
    _composer.value = TextEditingValue(text: body, selection: TextSelection.collapsed(offset: body.length));
    _focusComposer();
  }

  void _clearTarget() => setState(() {
        _endEdit();
        _replyTo = null;
      });

  Future<void> _confirmDeleteComment(dynamic comment) async {
    final l10n = AppLocalizations.of(context);
    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(title: l10n.tasksDeleteCommentTitle, content: l10n.tasksDeleteCommentBody),
          ),
        ) ??
        false;
    if (!confirmed || !mounted) return;
    HapticFeedback.mediumImpact();
    if (_editing != null && tutils.commentId(_editing) == tutils.commentId(comment)) _clearTarget();
    final ok = await _model.deleteComment(tutils.commentId(comment));
    if (!ok && mounted) _snack(l10n.tasksCommentDeleteFailed);
  }

  Future<void> _toggleReaction(String targetType, String targetId, String emoji) async {
    final ok = await _model.toggleReaction(targetType, targetId, emoji);
    if (!ok && mounted) _snack(AppLocalizations.of(context).tasksReactionFailed);
  }

  Future<bool> _submit(String body) async {
    final l10n = AppLocalizations.of(context);
    final editing = _editing;
    if (editing != null) {
      // Saving unchanged text just closes the edit: an "(edited)" mark on a
      // comment nobody changed is a false record.
      if (body == (tutils.commentBody(editing) ?? '').trim()) {
        _clearTarget();
        return true;
      }
      final ok = await _model.editComment(tutils.commentId(editing), body);
      if (!mounted) return ok;
      if (ok) {
        _clearTarget();
      } else {
        _snack(l10n.tasksCommentSaveFailed);
      }
      return ok;
    }
    final reply = _replyThread;
    final ok = await _model.postComment(body, parentCommentId: reply == null ? null : tutils.commentId(reply.root));
    if (!mounted) return ok;
    if (!ok) {
      _snack(l10n.tasksCommentPostFailed);
      return false;
    }
    _clearTarget();
    _composerFocus.unfocus();
    // A new thread is the newest one, at the foot of the stream.
    if (reply == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _scroll.hasClients) _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      });
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final media = MediaQuery.of(context);
    final keyboard = media.viewInsets.bottom;
    // Tall enough to read a thread, and never under the keyboard or the
    // status bar. The inset comes from the window: the modal route zeroes
    // `media.padding.top` inside the sheet.
    final statusBar = MediaQueryData.fromView(View.of(context)).padding.top;
    final maxHeight = (media.size.height - keyboard - statusBar - 12.0).clamp(160.0, media.size.height * 0.9);
    final canComment = _model.canComment;

    return Padding(
      padding: EdgeInsets.only(bottom: keyboard),
      child: Container(
        constraints: BoxConstraints(maxHeight: maxHeight),
        decoration: BoxDecoration(
          color: theme.secondaryBackground,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24.0)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            // Stretch children to full width so narrow content (e.g. a leaf
            // sub-task with no sub-task list) is left-aligned rather than
            // centered.
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                heightFactor: 1.0,
                child: Container(
                  margin: const EdgeInsets.only(top: 12.0, bottom: 8.0),
                  width: 40.0,
                  height: 4.0,
                  decoration: BoxDecoration(
                    color: theme.alternate,
                    borderRadius: BorderRadius.circular(2.0),
                  ),
                ),
              ),
              Flexible(
                child: SingleChildScrollView(
                  controller: _scroll,
                  keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                  padding: const EdgeInsets.fromLTRB(16.0, 8.0, 16.0, 16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      ..._header(theme, l10n, canComment),
                      Padding(
                        padding: const EdgeInsets.only(top: 22.0),
                        child: _actionRow(l10n),
                      ),
                      if (_model.relatedSessions.isNotEmpty) ...[
                        _SectionLabel(l10n.tasksSessionsSection),
                        TaskSessionList(sessions: _model.relatedSessions, onOpenSession: _openSession),
                      ],
                      _SectionLabel(l10n.tasksTimelineActivity),
                      _timeline(theme, l10n, canComment),
                    ],
                  ),
                ),
              ),
              if (canComment)
                TaskCommentComposer(
                  controller: _composer,
                  focusNode: _composerFocus,
                  target: _editing != null
                      ? TaskComposerTarget.edit
                      : _replyTo != null
                          ? TaskComposerTarget.reply
                          : TaskComposerTarget.comment,
                  targetName: _replyThread == null ? null : principalDisplayName(l10n, tutils.commentAuthor(_replyThread!.root), _model.viewer),
                  wake: _editing != null ? null : (_replyThread != null ? _model.replyWake(_replyThread!) : _model.topLevelWake),
                  agents: _model.mentionableAgents,
                  people: _model.people,
                  agentNames: _model.agentNames,
                  viewerId: _model.viewer?.id,
                  onSubmit: _submit,
                  onClearTarget: _clearTarget,
                )
              else
                Padding(
                  padding: const EdgeInsets.fromLTRB(16.0, 10.0, 16.0, 12.0),
                  child: Text(
                    l10n.tasksCommentViewOnly,
                    style: theme.labelMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 12.5, letterSpacing: 0.0),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  /// Everything above the action row: breadcrumb, id, title, where it was
  /// created, description, reactions, chips and sub-tasks.
  List<Widget> _header(FlutterFlowTheme theme, AppLocalizations l10n, bool canComment) {
    final status = tutils.taskStatus(task);
    final priority = tutils.taskPriority(task);
    final closed = tutils.taskIsClosed(task);
    final description = tutils.taskDescription(task);
    final labels = tutils.taskLabels(task);
    final createdInId = tutils.taskCreatedInInstanceId(task);
    final createdIn = createdInId == null ? null : _model.sessionRefs[createdInId];
    final dispatch = tutils.taskDispatch(task);

    final chips = <Widget>[
      TaskMetaChip(
        glyph: TaskStatusIcon(status: status),
        label: taskStatusLabel(l10n, status),
        color: tutils.taskStatusColor(status, theme),
      ),
      TaskMetaChip(
        glyph: TaskPriorityIcon(priority: priority),
        label: taskPriorityLabel(l10n, priority),
        color: tutils.taskPriorityColor(priority, theme),
      ),
      if (tutils.taskAssignee(task) != null) TaskAssigneeChip(task: task, viewer: _model.viewer),
      if (widget.project != null)
        TaskProjectChip(project: widget.project, name: tutils.projectName(widget.project)),
      ...labels.map((l) => TaskLabelChip(label: l)),
      if (waitingOnPeople(task).isNotEmpty) WaitingOnPill.forTask(task, _model.viewer?.id),
      if (dispatchChipTone(dispatch) != null)
        TaskDispatchChip(
          dispatch: dispatch!,
          agentName: _agentName(dispatch['agent_profile_id']?.toString()),
          onOpenSession: _openSession,
          onShowReason: _snack,
        ),
    ];

    return [
      // Parent breadcrumb — "↳ <parent title>", flush with the rest (no
      // indent), the mobile analogue of the web's chip.
      if (widget.parentTask != null)
        Align(
          alignment: Alignment.centerLeft,
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8.0),
            child: _ParentChip(
              task: widget.parentTask,
              onTap: () => Navigator.pop(context, 'open:${tutils.taskId(widget.parentTask)}'),
            ),
          ),
        ),
      // Nothing when the task has no key: a placeholder would read as a
      // reference someone could quote.
      if (tutils.taskIdentifier(task) != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 4.0),
          child: Align(alignment: Alignment.centerLeft, child: TaskIdentifier(task: task, fontSize: 12.0)),
        ),
      Text(
        tutils.taskTitle(task),
        style: theme.titleLarge.override(
          font: GoogleFonts.sourceSans3(),
          color: closed ? theme.secondaryText : theme.primaryText,
          fontSize: 18.0,
          letterSpacing: 0.0,
          fontWeight: FontWeight.w600,
          decoration: closed ? TextDecoration.lineThrough : null,
        ),
      ),
      // "Created in <session>": only for a session the viewer may open.
      if (createdIn != null)
        Padding(
          padding: const EdgeInsets.only(top: 6.0),
          child: Align(
            alignment: Alignment.centerLeft,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => _openSession(createdInId!),
              child: Text.rich(
                TextSpan(children: [
                  TextSpan(text: '${l10n.tasksCreatedIn} ', style: const TextStyle(fontWeight: FontWeight.w600)),
                  TextSpan(text: sessionRefTitle(l10n, createdIn)),
                ]),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.labelMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 12.5, letterSpacing: 0.0),
              ),
            ),
          ),
        ),
      if (description != null)
        Padding(
          padding: const EdgeInsets.only(top: 14.0),
          child: TaskMarkdown(description, fontSize: 14.5),
        ),
      // The task itself is reactable, like an issue's opening post.
      if (_model.taskReactions.isNotEmpty || (canComment && _model.timelineLoaded))
        Padding(
          padding: const EdgeInsets.only(top: 12.0),
          child: TaskReactionRow(
            reactions: _model.taskReactions,
            viewer: _model.viewer,
            onToggle: canComment ? (emoji) => _toggleReaction('task', _model.taskId, emoji) : null,
          ),
        ),
      // Chips go under the description.
      Padding(
        padding: const EdgeInsets.only(top: 14.0),
        child: Wrap(
          spacing: 14.0,
          runSpacing: 8.0,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: chips,
        ),
      ),
      if (widget.subtasks.isNotEmpty) _SubtaskList(subtasks: widget.subtasks),
    ];
  }

  /// The dispatched agent's name: the viewer's own agent, else the assignee
  /// when it is that agent, else "Agent".
  String _agentName(String? profileId) {
    for (final a in _model.agentProfiles) {
      if (a is Map && a['id']?.toString() == profileId) return a['name']?.toString() ?? '';
    }
    final assignee = tutils.taskAssignee(task);
    if (assignee != null && tutils.principalId(assignee) == profileId) {
      return tutils.principalName(assignee) ?? AppLocalizations.of(context).tasksPrincipalAgent;
    }
    return AppLocalizations.of(context).tasksPrincipalAgent;
  }

  Widget _actionRow(AppLocalizations l10n) {
    return Row(
      children: [
        Expanded(
          child: _ActionButton(
            icon: Icons.play_arrow_rounded,
            label: l10n.tasksStartSession,
            onTap: () {
              HapticFeedback.mediumImpact();
              Navigator.pop(context, 'start');
            },
          ),
        ),
        const SizedBox(width: 12.0),
        _ActionButton(
          icon: Icons.edit_outlined,
          onTap: () => Navigator.pop(context, 'edit'),
        ),
        const SizedBox(width: 10.0),
        _ActionButton(
          icon: Icons.delete_outline_rounded,
          onTap: () => Navigator.pop(context, 'delete'),
        ),
      ],
    );
  }

  Widget _timeline(FlutterFlowTheme theme, AppLocalizations l10n, bool canComment) {
    if (!_model.timelineLoaded) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 20.0),
        child: Center(child: SizedBox(width: 20.0, height: 20.0, child: CircularProgressIndicator(strokeWidth: 2.0, color: theme.secondaryText))),
      );
    }
    if (_model.timelineFailed) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 12.0),
        child: Text(l10n.tasksTimelineLoadFailed, style: theme.labelMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 12.5, letterSpacing: 0.0)),
      );
    }
    return TaskTimelineView(
      entries: _model.entries,
      viewer: _model.viewer,
      sessionRefs: _model.sessionRefs,
      replyingToRootId: _replyTo == null ? null : tutils.commentId(_replyTo!.root),
      actions: TaskTimelineActions(
        onOpenSession: _openSession,
        onToggleReaction: canComment ? (commentId, emoji) => _toggleReaction('comment', commentId, emoji) : null,
        onReply: canComment ? _replyIn : null,
        onEdit: canComment ? _edit : null,
        onDelete: canComment ? _confirmDeleteComment : null,
      ),
    );
  }
}

/// A section heading in the sheet ("Sessions", "Activity"), sentence case
/// like the sub-task heading.
class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 22.0, bottom: 6.0),
      child: Text(
        label,
        style: theme.labelMedium.override(
          font: GoogleFonts.sourceSans3(),
          color: theme.secondaryText,
          fontSize: 12.0,
          letterSpacing: 0.4,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

/// "↳ VIC-12 <parent title>" pill linking the task to its parent; tap to open
/// it.
class _ParentChip extends StatelessWidget {
  const _ParentChip({required this.task, required this.onTap});

  final dynamic task;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return InkWell(
      borderRadius: BorderRadius.circular(8.0),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10.0, vertical: 5.0),
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: BorderRadius.circular(8.0),
          border: Border.all(color: theme.alternate, width: 1.0),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.subdirectory_arrow_right_rounded,
                color: theme.secondaryText, size: 15.0),
            const SizedBox(width: 6.0),
            if (tutils.taskIdentifier(task) != null) ...[
              TaskIdentifier(task: task),
              const SizedBox(width: 6.0),
            ],
            Flexible(
              child: Text(
                tutils.taskTitle(task),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.labelMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.secondaryText,
                  fontSize: 12.0,
                  letterSpacing: 0.0,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The task's sub-tasks. Each row keeps the identifier and title flush-left
/// (aligned with the rest of the sheet — no leading indent) with the status
/// glyph trailing on the right, mirroring a normal task; tap a row to open that
/// sub-task.
class _SubtaskList extends StatelessWidget {
  const _SubtaskList({required this.subtasks});

  final List<dynamic> subtasks;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final total = subtasks.length;
    final done =
        subtasks.where((s) => tutils.taskStatus(s) == 'done').length;

    return Padding(
      padding: const EdgeInsets.only(top: 18.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${l10n.tasksSubtasks} · $done/$total',
            style: theme.labelMedium.override(
              font: GoogleFonts.sourceSans3(),
              color: theme.secondaryText,
              fontSize: 12.0,
              letterSpacing: 0.4,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4.0),
          for (final st in subtasks)
            InkWell(
              onTap: () =>
                  Navigator.pop(context, 'open:${tutils.taskId(st)}'),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8.0),
                child: Row(
                  children: [
                    if (tutils.taskIdentifier(st) != null) ...[
                      TaskIdentifier(task: st),
                      const SizedBox(width: 8.0),
                    ],
                    Expanded(
                      child: Text(
                        tutils.taskTitle(st),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.bodyMedium.override(
                          font: GoogleFonts.sourceSans3(),
                          color: tutils.taskIsClosed(st)
                              ? theme.secondaryText
                              : theme.primaryText,
                          letterSpacing: 0.0,
                          decoration: tutils.taskIsClosed(st)
                              ? TextDecoration.lineThrough
                              : null,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10.0),
                    TaskStatusIcon(status: tutils.taskStatus(st), size: 15.0),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A flat, neutral outline action button. Same style whether it carries a
/// [label] (Start session) or is icon-only (Edit / Delete).
class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.onTap,
    this.label,
  });

  final IconData icon;
  final VoidCallback onTap;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final iconOnly = label == null;
    return InkWell(
      borderRadius: BorderRadius.circular(12.0),
      onTap: onTap,
      child: Container(
        padding: iconOnly
            ? const EdgeInsets.all(13.0)
            : const EdgeInsets.symmetric(vertical: 12.0, horizontal: 6.0),
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: BorderRadius.circular(12.0),
          border: Border.all(color: theme.alternate, width: 1.0),
        ),
        child: iconOnly
            ? Icon(icon, color: theme.secondaryText, size: 20.0)
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, color: theme.secondaryText, size: 19.0),
                  const SizedBox(width: 6.0),
                  Flexible(
                    child: Text(
                      label!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}
