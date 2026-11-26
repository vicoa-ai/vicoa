import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'task_surface.dart';
import 'task_timeline_text.dart';

/// Emoji reactions on a task and on its comments: a row of pills plus an add
/// button. A tap toggles the viewer's own; a long press says who reacted.

/// The web's reaction set (`REACTION_GROUPS` in components/ui/emoji-picker.tsx):
/// what people actually answer with. The web picker adds a search and the
/// full Unicode set behind it; the phone has only this set for now. Pills
/// still show any emoji someone added elsewhere.
const List<String> kReactionEmoji = [
  '👍', '👎', '❤️', '🎉', '🚀', '👀', '🔥', '💯', '✅', '❌', '🤔', '🙏', //
  '😄', '😂', '😍', '😮', '😢', '😡', '😅', '🙃', '🧐', '😴', //
  '🐛', '🚢', '🚨', '👏', '🤝', '💡', '⚠️', '🛑', //
];

class TaskReactionRow extends StatelessWidget {
  const TaskReactionRow({super.key, required this.reactions, required this.viewer, this.onToggle});

  final List<dynamic> reactions;
  final TaskViewer? viewer;

  /// Omitted for a viewer who can't react: pills still show who reacted, but
  /// nothing toggles and there is no add button.
  final void Function(String emoji)? onToggle;

  @override
  Widget build(BuildContext context) {
    if (reactions.isEmpty && onToggle == null) return const SizedBox.shrink();
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    return Wrap(
      spacing: 6.0,
      runSpacing: 6.0,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        for (final r in reactions)
          Tooltip(
            message: describeReactors(l10n, r, viewer),
            triggerMode: TooltipTriggerMode.longPress,
            child: _Pill(
              reacted: tutils.reactionReacted(r),
              onTap: onToggle == null
                  ? null
                  : () {
                      HapticFeedback.selectionClick();
                      onToggle!(tutils.reactionEmoji(r));
                    },
              child: Text('${tutils.reactionEmoji(r)} ${tutils.reactionCount(r)}', style: theme.labelSmall.override(font: GoogleFonts.sourceSans3(), color: theme.primaryText, fontSize: 12.0, letterSpacing: 0.0)),
            ),
          ),
        if (onToggle != null)
          Semantics(
            label: l10n.tasksAddReaction,
            button: true,
            child: _Pill(
              reacted: false,
              onTap: () async {
                final emoji = await showReactionPicker(context);
                if (emoji != null) onToggle!(emoji);
              },
              child: Icon(Icons.add_reaction_outlined, size: 15.0, color: theme.secondaryText),
            ),
          ),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.reacted, required this.child, this.onTap});

  final bool reacted;
  final Widget child;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12.0),
        onTap: onTap,
        child: Container(
          height: 26.0,
          padding: const EdgeInsets.symmetric(horizontal: 8.0),
          // A reaction you added is the same neutral pill, a step darker.
          decoration: taskChatSurface(theme, radius: 13.0, strong: reacted),
          // Not the Container's `alignment`: that widens a pill to the whole
          // row, and the Wrap then stacks them.
          child: Center(widthFactor: 1.0, child: child),
        ),
      ),
    );
  }
}

/// The add-reaction picker: the curated set, which is the web picker's first
/// screen. Returns the emoji, or null when dismissed.
Future<String?> showReactionPicker(BuildContext context) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => const _ReactionPickerSheet(),
  );
}

class _ReactionPickerSheet extends StatelessWidget {
  const _ReactionPickerSheet();

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      decoration: BoxDecoration(color: theme.secondaryBackground, borderRadius: const BorderRadius.vertical(top: Radius.circular(20.0))),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16.0, 12.0, 16.0, 16.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(child: Container(width: 40.0, height: 4.0, decoration: BoxDecoration(color: theme.alternate, borderRadius: BorderRadius.circular(2.0)))),
              const SizedBox(height: 14.0),
              GridView.count(
                crossAxisCount: 8,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  for (final e in kReactionEmoji)
                    InkWell(
                      borderRadius: BorderRadius.circular(10.0),
                      onTap: () => Navigator.pop(context, e),
                      child: Center(child: Text(e, style: const TextStyle(fontSize: 24.0, height: 1.0))),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
