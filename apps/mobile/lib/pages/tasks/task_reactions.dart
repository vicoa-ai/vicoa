import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'task_timeline_text.dart';

/// Emoji reactions on a task and on its comments: a row of pills plus an add
/// button. A tap toggles the viewer's own; a long press says who reacted.

/// The web's reaction set (`REACTION_GROUPS` in components/ui/emoji-picker.tsx):
/// what people actually answer with. It is only the picker's first screen;
/// the field under it takes any emoji the keyboard has, since the server
/// accepts any emoji and a fixed strip is exactly what this is not.
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
          decoration: BoxDecoration(
            color: reacted ? theme.primary.withValues(alpha: 0.12) : theme.alternate.withValues(alpha: 0.35),
            borderRadius: BorderRadius.circular(13.0),
            border: Border.all(color: reacted ? theme.primary.withValues(alpha: 0.45) : theme.alternate, width: 1.0),
          ),
          // Not the Container's `alignment`: that widens a pill to the whole
          // row, and the Wrap then stacks them.
          child: Center(widthFactor: 1.0, child: child),
        ),
      ),
    );
  }
}

/// The add-reaction picker: the curated set, then a field for any emoji the
/// keyboard has. Returns the emoji, or null when dismissed.
Future<String?> showReactionPicker(BuildContext context) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => const _ReactionPickerSheet(),
  );
}

class _ReactionPickerSheet extends StatefulWidget {
  const _ReactionPickerSheet();

  @override
  State<_ReactionPickerSheet> createState() => _ReactionPickerSheetState();
}

class _ReactionPickerSheetState extends State<_ReactionPickerSheet> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// The keyboard's emoji page writes the emoji into the field; the first one
  /// that is really an emoji (not a letter typed by mistake) is the pick.
  void _onTyped(String value) {
    final chars = value.characters;
    if (chars.isEmpty) return;
    final last = chars.last;
    if (tutils.isReactionEmoji(last)) {
      Navigator.pop(context, last);
    } else {
      _controller.clear();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: Container(
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
                const SizedBox(height: 12.0),
                Text(l10n.tasksAddReaction, style: theme.titleSmall.override(font: GoogleFonts.sourceSans3(), color: theme.primaryText, letterSpacing: 0.0, fontWeight: FontWeight.w600)),
                const SizedBox(height: 10.0),
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
                const SizedBox(height: 10.0),
                TextField(
                  controller: _controller,
                  onChanged: _onTyped,
                  autocorrect: false,
                  enableSuggestions: false,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 20.0),
                  decoration: InputDecoration(
                    isDense: true,
                    labelText: l10n.tasksAnyEmoji,
                    hintText: l10n.tasksAnyEmojiHint,
                    floatingLabelBehavior: FloatingLabelBehavior.never,
                    prefixIcon: Icon(Icons.emoji_emotions_outlined, color: theme.secondaryText, size: 20.0),
                    filled: true,
                    fillColor: theme.primaryBackground,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12.0), borderSide: BorderSide(color: theme.alternate)),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12.0), borderSide: BorderSide(color: theme.alternate)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
