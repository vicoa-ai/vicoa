import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

/// Bottom sheet surfaced by the "+" button next to the gear pill in the chat
/// input area. Each option inserts a trigger character ("@" / "/") into the
/// message box and closes the sheet — the chat input's onChanged then runs
/// `filterFileMentions` / `filterSlashCommands` to surface the panel.
///
/// Header shape mirrors `agent_config_sheet.dart` (handle + close + centred
/// title) so the sheet reads as a sibling surface. Body is intrinsic-height
/// since there are only two rows.
Future<void> showAddToChatSheet({
  required BuildContext context,
  required VoidCallback onMentionFiles,
  required VoidCallback onCommands,
  VoidCallback? onPhotoLibrary,
  VoidCallback? onTakePhoto,
  VoidCallback? onChooseFiles,
  String commandsLabel = 'Commands',
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: false,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _AddToChatSheet(
      onMentionFiles: onMentionFiles,
      onCommands: onCommands,
      onPhotoLibrary: onPhotoLibrary,
      onTakePhoto: onTakePhoto,
      onChooseFiles: onChooseFiles,
      commandsLabel: commandsLabel,
    ),
  );
}

class _AddToChatSheet extends StatelessWidget {
  const _AddToChatSheet({
    required this.onMentionFiles,
    required this.onCommands,
    required this.onPhotoLibrary,
    required this.onTakePhoto,
    required this.onChooseFiles,
    required this.commandsLabel,
  });

  final VoidCallback onMentionFiles;
  final VoidCallback onCommands;
  // Attachment entries — null hides the row (e.g. surfaces that haven't wired
  // the picker yet).
  final VoidCallback? onPhotoLibrary;
  final VoidCallback? onTakePhoto;
  final VoidCallback? onChooseFiles;
  // Claude / OpenCode surface both "skills" and "commands" via the same
  // slash trigger, so the call site passes "Skills or Commands" for them.
  // Codex has no skills concept, so it stays as "Commands".
  final String commandsLabel;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(24.0),
          topRight: Radius.circular(24.0),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _SheetHandle(),
            _SheetHeader(
              title: AppLocalizations.of(context).agentChatAddToChat,
              onClose: () {
                HapticFeedback.lightImpact();
                Navigator.pop(context);
              },
            ),
            Padding(
              // Top 24 gives the header a clear breathing gap from the
              // option rows; bottom 32 lifts the sheet a touch taller than
              // its intrinsic two-row content so it doesn't feel cramped
              // against the home indicator.
              padding: const EdgeInsetsDirectional.fromSTEB(12.0, 24.0, 8.0, 32.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _AddToChatOption(
                    leading: Icon(
                      Icons.alternate_email,
                      color: theme.secondaryText,
                      size: 20.0,
                    ),
                    label: AppLocalizations.of(context).agentChatMentionFiles,
                    onTap: () {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context);
                      onMentionFiles();
                    },
                  ),
                  const SizedBox(height: 8.0),
                  _AddToChatOption(
                    // Mirrors the bordered "/" glyph from SlashCommandTrigger
                    // so the sheet's Commands row reads as the same affordance
                    // that used to sit inline next to the input box.
                    leading: const _SlashGlyph(),
                    label: commandsLabel,
                    onTap: () {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context);
                      onCommands();
                    },
                  ),
                  if (onPhotoLibrary != null) ...[
                    const SizedBox(height: 8.0),
                    _AddToChatOption(
                      leading: Icon(
                        Icons.photo_library_outlined,
                        color: theme.secondaryText,
                        size: 20.0,
                      ),
                      label: AppLocalizations.of(context).addToChatPhotoLibrary,
                      onTap: () {
                        HapticFeedback.lightImpact();
                        Navigator.pop(context);
                        onPhotoLibrary!();
                      },
                    ),
                  ],
                  if (onTakePhoto != null) ...[
                    const SizedBox(height: 8.0),
                    _AddToChatOption(
                      leading: Icon(
                        Icons.photo_camera_outlined,
                        color: theme.secondaryText,
                        size: 20.0,
                      ),
                      label: AppLocalizations.of(context).addToChatTakePhoto,
                      onTap: () {
                        HapticFeedback.lightImpact();
                        Navigator.pop(context);
                        onTakePhoto!();
                      },
                    ),
                  ],
                  if (onChooseFiles != null) ...[
                    const SizedBox(height: 8.0),
                    _AddToChatOption(
                      leading: Icon(
                        Icons.attach_file_rounded,
                        color: theme.secondaryText,
                        size: 20.0,
                      ),
                      label: AppLocalizations.of(context).addToChatChooseFiles,
                      onTap: () {
                        HapticFeedback.lightImpact();
                        Navigator.pop(context);
                        onChooseFiles!();
                      },
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AddToChatOption extends StatelessWidget {
  const _AddToChatOption({
    required this.leading,
    required this.label,
    required this.onTap,
  });

  final Widget leading;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(16.0),
      child: InkWell(
        borderRadius: BorderRadius.circular(16.0),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(8.0, 10.0, 16.0, 10.0),
          child: Row(
            children: [
              // Fixed leading slot so the Mentions and Commands labels line
              // up even though the @ icon and the bordered "/" glyph have
              // different intrinsic widths.
              SizedBox(
                width: 24.0,
                height: 24.0,
                child: Center(child: leading),
              ),
              const SizedBox(width: 16.0),
              Expanded(
                child: Text(
                  label,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 18.0,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Bordered "/" glyph lifted from `SlashCommandTrigger` so the Commands row
/// in this sheet reads as the same affordance as the trigger that used to
/// sit inline next to the chat input.
class _SlashGlyph extends StatelessWidget {
  const _SlashGlyph();

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      width: 20.0,
      height: 20.0,
      decoration: BoxDecoration(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(6.0),
        border: Border.all(
          color: theme.secondaryText.withValues(alpha: 0.8),
          width: 1.0,
        ),
      ),
      child: Transform.translate(
        offset: const Offset(0, -0.8),
        child: Text(
          '/',
          textAlign: TextAlign.center,
          style: theme.bodyMedium.override(
            color: theme.secondaryText,
            fontSize: 12.0,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _SheetHandle extends StatelessWidget {
  const _SheetHandle();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
      child: Container(
        width: 50.0,
        height: 4.0,
        decoration: BoxDecoration(
          color: FlutterFlowTheme.of(context).alternate,
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({required this.title, required this.onClose});
  final String title;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          FlutterFlowIconButton(
            borderColor: theme.alternate,
            borderRadius: 10.0,
            borderWidth: 1.0,
            buttonSize: 40.0,
            icon: Icon(Icons.close_rounded, color: theme.secondaryText, size: 20.0),
            onPressed: onClose,
          ),
          Text(
            title,
            style: theme.bodyMedium.override(
              font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
              fontSize: 19.0,
              fontWeight: FontWeight.w600,
            ),
          ),
          // Empty 40×40 placeholder balances the close button so the title
          // stays optically centred (matches agent_config_sheet's
          // close/confirm symmetry without needing a confirm action here).
          const SizedBox(width: 40.0, height: 40.0),
        ],
      ),
    );
  }
}
