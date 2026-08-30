import 'dart:async';

import 'package:flutter/material.dart';

import '/constants/slash_commands.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/file_mention_utils.dart';
import '/custom_code/utils/slash_command_utils.dart';
import '/custom_code/widgets/file_mention_suggestions.dart';
import '/pages/agent_chat/components/slash_commands.dart';

/// Backing controller for [MentionPromptField]. Mixes the shared `@`
/// file-mention and `/` slash-command behavior so any plain text field — not
/// just the chat / new-session models — can offer both. The mobile counterpart
/// of the web `MentionPromptField`.
///
/// `@` reads the live daemon index (falling back to the CLI-synced DB copy)
/// when a machine + project path are bound; `/` reads the agent's command and
/// skill set (live RPC or DB copy). With no project path, `@` simply yields no
/// matches while `/` still works from the DB copy.
class MentionPromptController with FileMentionMixin, SlashCommandMixin {
  MentionPromptController({
    required this.controller,
    required VoidCallback onStateChanged,
    String? machineId,
    String? projectPath,
    String agentType = 'claude',
  })  : _onStateChanged = onStateChanged,
        _machineId = machineId,
        _projectPath = projectPath,
        _agentType = agentType;

  final TextEditingController controller;
  final VoidCallback _onStateChanged;
  String? _machineId;
  String? _projectPath;
  String _agentType;

  @override
  TextEditingController get fileMentionTextController => controller;
  @override
  VoidCallback? get fileMentionOnStateChanged => _onStateChanged;
  @override
  TextEditingController get slashCommandTextController => controller;
  @override
  VoidCallback? get slashCommandOnStateChanged => _onStateChanged;
  @override
  String? resolveSlashCommandRawAgentType() => _agentType;
  @override
  String? resolveSlashCommandMachineId() => _machineId;
  @override
  String? resolveSlashCommandProjectPath() => _projectPath;

  void start() {
    unawaited(loadSlashCommands());
  }

  @override
  Future<void> ensureFileMentionsLoaded() => _loadFileMentions();

  Future<void> _loadFileMentions() async {
    final path = _projectPath;
    if (path == null || path.isEmpty) {
      fileMentions = const [];
      return;
    }
    if (isLoadingFileMentions) return;
    isLoadingFileMentions = true;
    try {
      final fetch = await actions.fetchFileMentions(
        projectPath: path,
        machineId: _machineId,
      );
      // Null files means "unchanged" — keep what we have.
      if (fetch.files != null) fileMentions = fetch.files!;
    } catch (e) {
      debugPrint('MentionPromptController: file-mention load failed: $e');
    } finally {
      isLoadingFileMentions = false;
      _onStateChanged();
    }
  }

  /// Re-scope when the bound machine / directory / agent changes (e.g. the
  /// automation sheet's machine dropdown, or the task sheet's project pill).
  void updateContext({
    required String? machineId,
    required String? projectPath,
    required String agentType,
  }) {
    var changed = false;
    if (agentType != _agentType) {
      _agentType = agentType;
      changed = true;
      // Re-scope the command/skill set to the new agent.
      unawaited(loadSlashCommands());
    }
    if (machineId != _machineId || projectPath != _projectPath) {
      _machineId = machineId;
      _projectPath = projectPath;
      changed = true;
      // The file index is per-machine + path; drop it and reload lazily on the
      // next `@` (or immediately if a mention panel is currently open).
      fileMentions = const [];
      if (showFileMentionSuggestions) unawaited(_loadFileMentions());
    }
    if (changed) _onStateChanged();
  }

  void handleTextChanged(String text) {
    filterSlashCommands(text);
    filterFileMentions(text);
  }

  /// Force both suggestion panels closed (e.g. the field lost focus).
  void hideSuggestions() {
    showSlashCommandSuggestions = false;
    filteredSlashCommands = [];
    showFileMentionSuggestions = false;
    filteredFileMentions = [];
    _onStateChanged();
  }

  void insertCommand(SlashCommand command) {
    insertSlashCommand(command.command, insertText: command.insert);
  }

  void dispose() {
    disposeFileMentionMixin();
  }
}

/// A multiline text field that supports `@` file mentions and `/` slash
/// commands + skills. Drop-in for a plain [TextField]: pass the same
/// [controller], [decoration] and [style], plus the bound [machineId] /
/// [projectPath] (absolute) / [agentType] so the two indexes can scope
/// themselves. The suggestion panels render just below the field while typing.
class MentionPromptField extends StatefulWidget {
  const MentionPromptField({
    super.key,
    required this.controller,
    this.focusNode,
    this.machineId,
    this.projectPath,
    this.agentType = 'claude',
    this.decoration,
    this.style,
    this.minLines = 2,
    this.maxLines = 5,
    this.autofocus = false,
    this.textCapitalization = TextCapitalization.sentences,
    this.onChanged,
  });

  final TextEditingController controller;
  final FocusNode? focusNode;

  /// Machine the project lives on. Null → `@` reads the DB copy (or nothing).
  final String? machineId;

  /// Absolute project path — scopes `@` search and project-local `/` commands.
  final String? projectPath;

  /// Agent whose command/skill set the `/` menu offers. Defaults to Claude.
  final String agentType;

  final InputDecoration? decoration;
  final TextStyle? style;
  final int minLines;
  final int maxLines;
  final bool autofocus;
  final TextCapitalization textCapitalization;

  /// Extra change callback (e.g. to drive a Save button's enabled state).
  final ValueChanged<String>? onChanged;

  @override
  State<MentionPromptField> createState() => _MentionPromptFieldState();
}

class _MentionPromptFieldState extends State<MentionPromptField> {
  late final MentionPromptController _mention;
  // Links the floating suggestion panel to the field so it tracks it on scroll.
  final LayerLink _link = LayerLink();
  // On the field wrapper so the overlay can read the field's width.
  final GlobalKey _fieldKey = GlobalKey();
  // A focus node we own iff the caller didn't pass one — needed to dismiss the
  // floating panel when the field loses focus.
  late final FocusNode _focusNode;
  late final bool _ownsFocusNode;
  OverlayEntry? _overlayEntry;

  @override
  void initState() {
    super.initState();
    _ownsFocusNode = widget.focusNode == null;
    _focusNode = widget.focusNode ?? FocusNode();
    _focusNode.addListener(_onFocusChanged);
    _mention = MentionPromptController(
      controller: widget.controller,
      onStateChanged: () {
        if (mounted) setState(() {});
      },
      machineId: widget.machineId,
      projectPath: widget.projectPath,
      agentType: widget.agentType,
    );
    _mention.start();
  }

  @override
  void didUpdateWidget(covariant MentionPromptField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.machineId != widget.machineId ||
        oldWidget.projectPath != widget.projectPath ||
        oldWidget.agentType != widget.agentType) {
      _mention.updateContext(
        machineId: widget.machineId,
        projectPath: widget.projectPath,
        agentType: widget.agentType,
      );
    }
  }

  @override
  void dispose() {
    _removeOverlay();
    _focusNode.removeListener(_onFocusChanged);
    if (_ownsFocusNode) _focusNode.dispose();
    _mention.dispose();
    super.dispose();
  }

  void _onFocusChanged() {
    // Dropping focus (tapping elsewhere in the sheet) hides the panel. Tapping
    // a suggestion doesn't steal focus, so selection still lands.
    if (!_focusNode.hasFocus) {
      _mention.hideSuggestions();
      _removeOverlay();
    }
  }

  void _onChanged(String text) {
    _mention.handleTextChanged(text);
    widget.onChanged?.call(text);
  }

  bool get _shouldShowPanel =>
      (_mention.showSlashCommandSuggestions && _mention.filteredSlashCommands.isNotEmpty) ||
      (_mention.showFileMentionSuggestions && _mention.filteredFileMentions.isNotEmpty);

  void _syncOverlay() {
    if (!mounted) return;
    if (!_shouldShowPanel) {
      _removeOverlay();
      return;
    }
    if (_overlayEntry == null) {
      _overlayEntry = OverlayEntry(builder: _buildOverlay);
      Overlay.of(context, rootOverlay: true).insert(_overlayEntry!);
    } else {
      _overlayEntry!.markNeedsBuild();
    }
  }

  void _removeOverlay() {
    _overlayEntry?.remove();
    _overlayEntry = null;
  }

  // Panel max height (185 slash / 210 file) plus a small gap — the room the
  // panel needs to sit fully on-screen above the field.
  static const double _panelReserve = 220.0;

  Widget _buildOverlay(BuildContext context) {
    final box = _fieldKey.currentContext?.findRenderObject() as RenderBox?;
    final media = MediaQuery.of(context);
    final width = box?.size.width ?? (media.size.width - 32.0);
    // Float the panel above the field (its bottom-left pinned to the field's
    // top-left), so it overlays content without changing the sheet's height.
    // Prefer above per the design; flip to below only when the field sits too
    // high for the panel to fit above (e.g. keyboard up), so the top matches
    // never clip off-screen. Both positions float and follow the field.
    final fieldTop = box?.localToGlobal(Offset.zero).dy ?? 0.0;
    final openAbove = (fieldTop - media.padding.top) >= _panelReserve;
    // Align + CompositedTransformFollower is the RawAutocomplete pattern for a
    // field-anchored overlay; the SizedBox matches the panel to the field width.
    // TextFieldTapRegion keeps a tap on a suggestion from being treated as a
    // tap-outside that would unfocus the field before the selection lands.
    return Align(
      alignment: Alignment.topLeft,
      child: CompositedTransformFollower(
        link: _link,
        showWhenUnlinked: false,
        targetAnchor: openAbove ? Alignment.topLeft : Alignment.bottomLeft,
        followerAnchor: openAbove ? Alignment.bottomLeft : Alignment.topLeft,
        offset: Offset(0, openAbove ? -6 : 6),
        child: SizedBox(
          width: width,
          child: TextFieldTapRegion(
            child: Material(
              type: MaterialType.transparency,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SlashCommandSuggestions(
                    visible: _mention.showSlashCommandSuggestions,
                    commands: _mention.filteredSlashCommands,
                    margin: EdgeInsets.zero,
                    onCommandSelected: (command) async {
                      _mention.insertCommand(command);
                      widget.onChanged?.call(widget.controller.text);
                      if (mounted) setState(() {});
                    },
                  ),
                  FileMentionSuggestions(
                    mixin: _mention,
                    margin: EdgeInsets.zero,
                    onFileSelected: (_) =>
                        widget.onChanged?.call(widget.controller.text),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Keep the floating panel in sync with the latest state + layout after each
    // rebuild. Done post-frame so the field's RenderBox (width) is available
    // and we never mutate the overlay mid-build.
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncOverlay());
    return CompositedTransformTarget(
      link: _link,
      child: TextField(
        key: _fieldKey,
        controller: widget.controller,
        focusNode: _focusNode,
        autofocus: widget.autofocus,
        minLines: widget.minLines,
        maxLines: widget.maxLines,
        keyboardType: TextInputType.multiline,
        textCapitalization: widget.textCapitalization,
        style: widget.style,
        decoration: widget.decoration,
        onChanged: _onChanged,
      ),
    );
  }
}
