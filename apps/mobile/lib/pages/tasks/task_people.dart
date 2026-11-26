import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/principal_avatar/principal_avatar.dart';
import '/custom_code/utils/task_questions.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'task_timeline_text.dart';

/// Who a task involves, as chips: the assignee, whom an agent's question
/// waits on, and what the agent asked to act on it is doing. Shared by the
/// task card and the detail sheet.

/// "Waiting on Nick": an agent asked someone a question on the task and it is
/// still open. For the viewer it reads "Waiting on you" in the primary tone,
/// since it is their turn; for anyone else it is muted. The twin of the web's
/// `WaitingOnPill`. Renders nothing when it waits on nobody.
class WaitingOnPill extends StatelessWidget {
  const WaitingOnPill({super.key, required this.people, required this.viewerId});

  /// Whom it waits on (`waitingOnPeople`), or one question's addressee.
  final List<dynamic> people;
  final String? viewerId;

  /// The pill for a whole task.
  factory WaitingOnPill.forTask(dynamic task, String? viewerId, {Key? key}) => WaitingOnPill(key: key, people: waitingOnPeople(task), viewerId: viewerId);

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final label = waitingOnLabel(l10n, people, viewerId);
    if (label == null) return const SizedBox.shrink();
    final theme = FlutterFlowTheme.of(context);
    final mine = viewerId != null && people.any((p) => tutils.principalId(p) == viewerId);
    final color = mine ? theme.primary : theme.secondaryText;
    return Container(
      height: 20.0,
      padding: const EdgeInsets.symmetric(horizontal: 7.0),
      decoration: BoxDecoration(
        color: mine ? theme.primary.withValues(alpha: 0.12) : theme.alternate.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(10.0),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.hourglass_empty_rounded, size: 12.0, color: color),
          const SizedBox(width: 4.0),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.labelSmall.override(font: GoogleFonts.sourceSans3(), color: color, fontSize: 11.0, letterSpacing: 0.0, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}

/// The task's assignee: their avatar and name, plain like the project chip.
/// Nothing when the task is unassigned.
class TaskAssigneeChip extends StatelessWidget {
  const TaskAssigneeChip({super.key, required this.task, this.viewer});

  final dynamic task;
  final TaskViewer? viewer;

  @override
  Widget build(BuildContext context) {
    final assignee = tutils.taskAssignee(task);
    if (assignee == null) return const SizedBox.shrink();
    final theme = FlutterFlowTheme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        PrincipalAvatar.fromResponse(assignee, size: PrincipalAvatarSize.xs),
        const SizedBox(width: 5.0),
        Flexible(
          child: Text(
            principalDisplayName(AppLocalizations.of(context), assignee, viewer),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.labelMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, fontSize: 12.0, letterSpacing: 0.0, fontWeight: FontWeight.w500),
          ),
        ),
      ],
    );
  }
}

/// How a dispatch chip reads: waiting (queued, starting), working, failed.
enum DispatchTone { waiting, working, failed }

/// The tone [dispatch]'s chip takes, or null when it shows no chip: nothing
/// once the agent's turn is over or the request was cancelled. The same
/// states as the web's `dispatchChipState`.
DispatchTone? dispatchChipTone(Map<String, dynamic>? dispatch) {
  if (dispatch == null) return null;
  final session = dispatch['session_status']?.toString();
  switch (dispatch['state']?.toString()) {
    case 'queued':
    case 'dispatching':
      return DispatchTone.waiting;
    case 'started':
      // Spawned; until the session registers there is no status to read.
      if (session == null) return DispatchTone.waiting;
      return session == 'ACTIVE' ? DispatchTone.working : null;
    case 'delivered':
    case 'resumed':
      return session == 'ACTIVE' ? DispatchTone.working : null;
    case 'failed':
      return DispatchTone.failed;
    default:
      return null;
  }
}

/// What the agent asked to act on the task is doing right now, from its
/// latest dispatch: "Queued", "Starting", "<agent> working", or a red
/// "Failed". Nothing once its turn is over or the request was cancelled; the
/// assignee and the timeline say the rest. The twin of the web's
/// `TaskDispatchChip`, with the same states.
class TaskDispatchChip extends StatelessWidget {
  const TaskDispatchChip({super.key, required this.dispatch, required this.agentName, this.onOpenSession, this.onShowReason});

  final Map<String, dynamic>? dispatch;

  /// The dispatched agent's name ("Agent" when it can't be resolved).
  final String agentName;

  /// Tapping a chip with a session behind it opens that session.
  final void Function(String sessionId)? onOpenSession;

  /// Tapping a failed chip says why.
  final void Function(String reason)? onShowReason;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final tone = dispatchChipTone(dispatch);
    if (tone == null) return const SizedBox.shrink();
    final theme = FlutterFlowTheme.of(context);
    final label = switch (tone) {
      DispatchTone.working => l10n.tasksDispatchWorking(agentName),
      DispatchTone.failed => l10n.tasksDispatchFailed,
      DispatchTone.waiting => dispatch?['state'] == 'queued' ? l10n.tasksDispatchQueued : l10n.tasksDispatchStarting,
    };
    final color = switch (tone) {
      DispatchTone.working => const Color(0xFF10B981), // emerald-500
      DispatchTone.failed => const Color(0xFFEF4444), // red-500
      DispatchTone.waiting => theme.secondaryText,
    };
    final sessionId = dispatch?['agent_instance_id']?.toString();
    final detail = dispatch?['detail']?.toString();
    VoidCallback? onTap;
    if (tone == DispatchTone.failed && onShowReason != null) {
      onTap = () => onShowReason!(detail == null || detail.isEmpty ? l10n.tasksDispatchFailedNoReason(agentName) : l10n.tasksDispatchFailedReason(agentName, detail));
    } else if (sessionId != null && sessionId.isNotEmpty && onOpenSession != null) {
      onTap = () => onOpenSession!(sessionId);
    }
    final chip = Container(
      height: 20.0,
      padding: const EdgeInsets.symmetric(horizontal: 7.0),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(10.0)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 6.0, height: 6.0, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 5.0),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.labelSmall.override(font: GoogleFonts.sourceSans3(), color: color, fontSize: 11.0, letterSpacing: 0.0, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
    if (onTap == null) return chip;
    return GestureDetector(behavior: HitTestBehavior.opaque, onTap: onTap, child: chip);
  }
}
