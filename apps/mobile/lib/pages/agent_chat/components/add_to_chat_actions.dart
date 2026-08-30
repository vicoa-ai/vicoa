import 'package:flutter/material.dart';

import '/custom_code/utils/file_mention_utils.dart';
import '/custom_code/utils/slash_command_utils.dart';
import '/l10n/app_localizations.dart';
import 'add_to_chat_sheet.dart';

/// Inserts [char] at the current cursor position in [controller], shifting the
/// cursor right by `char.length`. Falls back to appending at the end when the
/// selection is invalid. Used by the Add-to-chat callbacks so tapping an
/// option doesn't wipe the user's draft.
void _insertTriggerAtCursor(TextEditingController controller, String char) {
  final text = controller.text;
  final selection = controller.selection;
  final cursor = selection.isValid && selection.baseOffset >= 0
      ? selection.baseOffset.clamp(0, text.length)
      : text.length;
  final newText = text.substring(0, cursor) + char + text.substring(cursor);
  controller.text = newText;
  controller.selection = TextSelection.fromPosition(
    TextPosition(offset: cursor + char.length),
  );
}

/// Opens the "Add to chat" bottom sheet and wires its options to insert "@" /
/// "/" into [controller], then nudges the bound [fileMention] / [slashCommand]
/// mixins to surface the matching suggestion panel. Shared by the chat input
/// (`chat_input_area.dart`) and the new-session prompt so both surfaces behave
/// identically — the same object backs both [fileMention] and [slashCommand]
/// (each model mixes in `FileMentionMixin` + `SlashCommandMixin`).
///
/// [hasSkills] controls the Commands row label: Claude / OpenCode surface both
/// skills and commands through the same slash trigger ("Skills or Commands");
/// Codex (and ACP agents) only have commands ("Commands").
void showAddToChatMenu({
  required BuildContext context,
  required TextEditingController controller,
  required FocusNode focusNode,
  required FileMentionMixin fileMention,
  required SlashCommandMixin slashCommand,
  required bool hasSkills,
  // Attachment entries — null hides the row (surfaces without an instance to
  // upload against, e.g. the new-session prompt).
  VoidCallback? onPhotoLibrary,
  VoidCallback? onTakePhoto,
  VoidCallback? onChooseFiles,
}) {
  showAddToChatSheet(
    context: context,
    commandsLabel: hasSkills
        ? AppLocalizations.of(context).addToChatSkillsOrCommands
        : AppLocalizations.of(context).addToChatCommands,
    onPhotoLibrary: onPhotoLibrary,
    onTakePhoto: onTakePhoto,
    onChooseFiles: onChooseFiles,
    onMentionFiles: () {
      // File mentions only trigger when '@' sits at index 0 or is preceded by
      // whitespace (filterFileMentions in file_mention_utils.dart). Auto-
      // prepend a space when the char before the cursor isn't already
      // whitespace so tapping this option always opens the panel.
      final text = controller.text;
      final selection = controller.selection;
      final cursor = selection.isValid && selection.baseOffset >= 0
          ? selection.baseOffset.clamp(0, text.length)
          : text.length;
      final needsLeadingSpace =
          cursor > 0 && !' \n\t'.contains(text[cursor - 1]);
      _insertTriggerAtCursor(controller, needsLeadingSpace ? ' @' : '@');
      // Force-hide slash panel — if existing text starts with '/' the new "@"
      // mid-message wouldn't have dismissed it via filterSlashCommands alone.
      slashCommand.filterSlashCommands('');
      fileMention.filterFileMentions(controller.text);
      focusNode.requestFocus();
    },
    onCommands: () {
      // Slash commands only fire when the trimmed text starts with '/', so
      // ignore the cursor and force the trigger to position 0. Empty box → "/",
      // non-empty → "/ {existing}" (the space separates the command name from
      // prior content, keeping draft text intact while the panel opens).
      final existing = controller.text;
      final newText = existing.isEmpty ? '/' : '/ $existing';
      controller.text = newText;
      // Park the cursor right after the '/' so the next keystroke filters by
      // command name, not into the preserved draft.
      controller.selection = const TextSelection.collapsed(offset: 1);
      // Cursor may have moved past a prior "@", so the file-mention panel from
      // before is stale — hide it.
      fileMention.setFileMentionSuggestions(show: false, suggestions: const []);
      slashCommand.filterSlashCommands(newText);
      focusNode.requestFocus();
    },
  );
}
