import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/project_paths.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/tasks/task_glyphs.dart' show TaskProjectIcon;

/// Bottom-sheet for picking the project folder. Styled to match the
/// message_selection_sheet pattern: full-bleed container (65% screen height)
/// with a handle bar, Close / Title / Done header, and a scrollable body. With
/// the keyboard up it collapses to the header + path input and sits on top of
/// the keyboard.
///
/// Two callers, two lists. The new-session screen passes [projects] — the
/// projects linked to a folder on the selected machine, newest activity first
/// — and the sheet shows them on top, the path input beneath for any other
/// folder (a project's subfolder, or a brand-new one the backend mints a
/// project for on the first spawn). The automation editor passes plain
/// [recentDirectories] instead. The screen renders only a click-target
/// container that opens this sheet.
///
/// Returns the chosen directory (or `null` on cancel).
Future<String?> showDirectoryPickerSheet({
  required BuildContext context,
  required String initial,
  List<ProjectPickerEntry> projects = const [],
  String? selectedProjectId,
  List<String> recentDirectories = const [],
}) async {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    useSafeArea: false,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _DirectoryPickerSheet(
      initial: initial,
      projects: projects,
      selectedProjectId: selectedProjectId,
      recent: recentDirectories,
    ),
  );
}

class _DirectoryPickerSheet extends StatefulWidget {
  const _DirectoryPickerSheet({required this.initial, required this.projects, required this.selectedProjectId, required this.recent});
  final String initial;
  final List<ProjectPickerEntry> projects;
  final String? selectedProjectId;
  final List<String> recent;

  @override
  State<_DirectoryPickerSheet> createState() => _DirectoryPickerSheetState();
}

class _DirectoryPickerSheetState extends State<_DirectoryPickerSheet> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initial)
      ..selection = TextSelection.collapsed(offset: widget.initial.length);
    _focusNode = FocusNode();
    _controller.addListener(_onTextChanged);
    // Open with the keyboard down so the recent-directories list is reachable;
    // the field only focuses when the user taps it.
  }

  void _onTextChanged() => setState(() {});

  @override
  void dispose() {
    _controller.removeListener(_onTextChanged);
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  bool get _canConfirm => _controller.text.trim().isNotEmpty;

  void _confirm() {
    if (!_canConfirm) return;
    HapticFeedback.lightImpact();
    Navigator.of(context).pop(_controller.text.trim());
  }

  void _pickRecent(String dir) {
    HapticFeedback.lightImpact();
    Navigator.of(context).pop(dir);
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final media = MediaQuery.of(context);
    // While a path is being typed the lists are dead weight: they collapse and
    // the sheet shrinks to header + input, riding on top of the keyboard,
    // instead of squeezing a fixed-height column into whatever is left above
    // it (which is where a sub-pixel overflow came from on tall keyboards).
    final keyboardUp = media.viewInsets.bottom > 0;
    final showProjects = widget.projects.isNotEmpty && !keyboardUp;
    final showRecent = widget.recent.isNotEmpty && !keyboardUp;
    return Padding(
      padding: EdgeInsets.only(bottom: media.viewInsets.bottom),
      // Slide the header down as the keyboard rises (and back up once it is
      // gone) rather than snapping between the two heights.
      child: AnimatedSize(
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
        alignment: Alignment.bottomCenter,
        child: Container(
          width: double.infinity,
          height: keyboardUp ? null : media.size.height * 0.65,
          decoration: BoxDecoration(
            color: theme.secondaryBackground,
            borderRadius: const BorderRadius.only(topLeft: Radius.circular(24.0), topRight: Radius.circular(24.0)),
          ),
          // Tap anywhere outside the text field to dismiss the keyboard.
          child: GestureDetector(
            onTap: () => FocusScope.of(context).unfocus(),
            behavior: HitTestBehavior.translucent,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              _SheetHandle(),
              _SheetHeader(
                title: l10n.directoryPickerProject,
                canConfirm: _canConfirm,
                onClose: () { HapticFeedback.lightImpact(); Navigator.pop(context); },
                onConfirm: _confirm,
              ),
              // Projects first (the common case is picking one), the path input
              // for everything else beneath. When the caller passes plain recent
              // folders instead (the automation editor), those take the list slot.
              if (showProjects) ...[
                Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 8.0),
                  child: Align(alignment: AlignmentDirectional.centerStart, child: _sectionLabel(context, l10n.directoryPickerProjects)),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
                    child: _ProjectList(projects: widget.projects, selectedProjectId: widget.selectedProjectId, onTap: _pickRecent),
                  ),
                ),
              ],
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 8.0),
                child: Align(alignment: AlignmentDirectional.centerStart, child: _sectionLabel(context, l10n.directoryPickerFolder)),
              ),
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
                child: _DirectoryTextField(controller: _controller, focusNode: _focusNode, onSubmit: (_) => _confirm()),
              ),
              if (showRecent) ...[
                Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(16.0, 20.0, 16.0, 8.0),
                  child: Align(alignment: AlignmentDirectional.centerStart, child: _sectionLabel(context, l10n.directoryPickerRecent)),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
                    child: _RecentDirectoryList(directories: widget.recent, onTap: _pickRecent),
                  ),
                ),
              ] else if (!keyboardUp && widget.projects.isEmpty)
                const Expanded(child: SizedBox.shrink()),
              // Clear of the home indicator; `padding.bottom` is already 0 once
              // the keyboard covers it, so this never double-counts.
              SizedBox(height: 16.0 + media.padding.bottom),
            ]),
          ),
        ),
      ),
    );
  }
}

Widget _sectionLabel(BuildContext context, String label) {
  final theme = FlutterFlowTheme.of(context);
  return Text(
    label,
    style: theme.labelMedium.override(
      font: GoogleFonts.sourceSans3(),
      fontSize: 15.0,
      fontWeight: FontWeight.w500,
      color: theme.secondaryText,
    ),
  );
}

class _SheetHandle extends StatelessWidget {
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
  const _SheetHeader({required this.title, required this.canConfirm, required this.onClose, required this.onConfirm});
  final String title;
  final bool canConfirm;
  final VoidCallback onClose;
  final VoidCallback onConfirm;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
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
        FlutterFlowIconButton(
          borderColor: canConfirm ? theme.primary : theme.alternate,
          borderRadius: 10.0,
          borderWidth: 1.0,
          buttonSize: 40.0,
          fillColor: canConfirm ? theme.primary : null,
          icon: Icon(
            Icons.check_rounded,
            color: canConfirm ? theme.info : theme.secondaryText,
            size: 20.0,
          ),
          onPressed: canConfirm ? onConfirm : null,
        ),
      ]),
    );
  }
}

class _DirectoryTextField extends StatelessWidget {
  const _DirectoryTextField({required this.controller, required this.focusNode, required this.onSubmit});
  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onSubmit;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 4.0),
        child: TextField(
          controller: controller,
          focusNode: focusNode,
          textInputAction: TextInputAction.done,
          onSubmitted: onSubmit,
          decoration: InputDecoration(
            hintText: '~/projects/my-app',
            hintStyle: theme.bodyMedium.override(color: theme.secondaryText.withValues(alpha: 0.5), fontSize: 15.0),
            border: InputBorder.none,
          ),
          style: theme.bodyMedium.override(font: GoogleFonts.firaCode(), fontSize: 15.0),
        ),
      ),
    );
  }
}

/// The projects linked to a folder on the selected machine: icon + name, the
/// folder in muted mono beneath, a check on the one the current folder falls
/// under. Tapping picks the project's folder.
class _ProjectList extends StatelessWidget {
  const _ProjectList({required this.projects, required this.selectedProjectId, required this.onTap});
  final List<ProjectPickerEntry> projects;
  final String? selectedProjectId;
  final ValueChanged<String> onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return ListView.separated(
      padding: EdgeInsets.zero,
      itemCount: projects.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8.0),
      itemBuilder: (context, index) {
        final entry = projects[index];
        final selected = entry.id == selectedProjectId;
        return InkWell(
          onTap: () => onTap(entry.path),
          borderRadius: BorderRadius.circular(12.0),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 10.0),
            decoration: BoxDecoration(
              color: theme.primaryBackground,
              borderRadius: BorderRadius.circular(12.0),
              border: selected ? Border.all(color: theme.primary, width: 1.0) : null,
            ),
            child: Row(children: [
              TaskProjectIcon(project: entry.project, size: 18.0),
              const SizedBox(width: 10.0),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                  Text(
                    entry.name,
                    style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500), fontSize: 15.0, fontWeight: FontWeight.w500, color: theme.primaryText),
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    entry.path,
                    style: theme.bodySmall.override(font: GoogleFonts.firaCode(), fontSize: 12.0, color: theme.secondaryText),
                    overflow: TextOverflow.ellipsis,
                  ),
                ]),
              ),
              if (selected) ...[
                const SizedBox(width: 8.0),
                Icon(Icons.check_rounded, color: theme.primary, size: 18.0),
              ],
            ]),
          ),
        );
      },
    );
  }
}

class _RecentDirectoryList extends StatelessWidget {
  const _RecentDirectoryList({required this.directories, required this.onTap});
  final List<String> directories;
  final ValueChanged<String> onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return ListView.separated(
      // Bottom inset so the last directory isn't flush against the sheet edge /
      // home indicator (the sheet renders without safe-area padding).
      padding: EdgeInsets.only(bottom:12.0 + MediaQuery.of(context).padding.bottom),
      itemCount: directories.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8.0),
      itemBuilder: (context, index) {
        final dir = directories[index];
        return InkWell(
          onTap: () => onTap(dir),
          borderRadius: BorderRadius.circular(12.0),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 12.0),
            decoration: BoxDecoration(
              color: theme.primaryBackground,
              borderRadius: BorderRadius.circular(12.0),
            ),
            child: Row(children: [
              Icon(Icons.folder_open_outlined, color: theme.secondaryText, size: 16.0),
              const SizedBox(width: 10.0),
              Expanded(
                child: Text(
                  dir,
                  style: theme.bodySmall.override(font: GoogleFonts.firaCode(), fontSize: 13.0, color: theme.primaryText),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ]),
          ),
        );
      },
    );
  }
}
