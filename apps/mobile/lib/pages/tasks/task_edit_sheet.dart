import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/app_state.dart';
import '/custom_code/utils/keyboard_utils.dart';
import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/mention_prompt_field.dart';
import 'task_glyphs.dart';
import 'task_l10n.dart';
import 'task_pickers.dart';

/// Bottom-sheet editor for creating and editing a task. Compact, web-style:
/// borderless title/description (placeholders, no field labels) and a row of
/// property pills (status, priority, project, labels) that each open a picker.
/// Returns {title, description, status, priority, project_id, label_ids} on
/// save, or null if dismissed. Does NOT call the API — the caller decides
/// create vs. update.
Future<Map<String, dynamic>?> showTaskEditSheet({
  required BuildContext context,
  dynamic task,
  required List<dynamic> projects,
  required List<dynamic> labels,
  String? defaultProjectId,
}) {
  return showModalBottomSheet<Map<String, dynamic>>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    enableDrag: true,
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
      child: _TaskEditSheet(
        task: task,
        projects: projects,
        labels: labels,
        defaultProjectId: defaultProjectId,
      ),
    ),
  );
}

class _TaskEditSheet extends StatefulWidget {
  const _TaskEditSheet({
    required this.task,
    required this.projects,
    required this.labels,
    required this.defaultProjectId,
  });

  final dynamic task;
  final List<dynamic> projects;
  final List<dynamic> labels;
  final String? defaultProjectId;

  @override
  State<_TaskEditSheet> createState() => _TaskEditSheetState();
}

class _TaskEditSheetState extends State<_TaskEditSheet> {
  late final TextEditingController _titleController;
  late final TextEditingController _descController;
  late String _status;
  late String _priority;
  String? _projectId;
  late Set<String> _labelIds;
  bool _titleError = false;

  final _statusKey = GlobalKey();
  final _priorityKey = GlobalKey();
  final _projectKey = GlobalKey();
  final _labelsKey = GlobalKey();

  bool get _isEditing => widget.task != null;

  @override
  void initState() {
    super.initState();
    final t = widget.task;
    _titleController =
        TextEditingController(text: t != null ? tutils.taskTitle(t) : '');
    _descController = TextEditingController(
        text: t != null ? (tutils.taskDescription(t) ?? '') : '');
    _status = t != null ? tutils.taskStatus(t) : 'backlog';
    _priority = t != null ? tutils.taskPriority(t) : 'none';
    _projectId = t != null ? tutils.taskProjectId(t) : widget.defaultProjectId;
    _labelIds = t != null
        ? {for (final l in tutils.taskLabels(t)) tutils.labelId(l)}
        : <String>{};
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descController.dispose();
    super.dispose();
  }

  dynamic get _selectedProject {
    for (final p in widget.projects) {
      if (tutils.projectId(p) == _projectId) return p;
    }
    return null;
  }

  /// The selected project's linked directories (machine_id + absolute
  /// local_path), used to scope the description field's `@` file search and
  /// project-local `/` commands. Empty for the Inbox or an unlinked project.
  List<dynamic> get _projectDirectories {
    final p = _selectedProject;
    if (p is Map) {
      final dirs = p['directories'];
      if (dirs is List) return dirs;
    }
    return const [];
  }

  /// Pick the directory link to mention against: the machine last used for a
  /// new session if the project is linked there, else the first link. Mirrors
  /// the web task dialog's resolution.
  Map? get _mentionLink {
    final dirs = _projectDirectories;
    if (dirs.isEmpty) return null;
    final lastMachine = FFAppState().userPreferences.newSessionMachineId;
    for (final d in dirs) {
      if (d is Map && d['machine_id'] == lastMachine) return d;
    }
    final first = dirs.first;
    return first is Map ? first : null;
  }

  String? get _mentionMachineId => _mentionLink?['machine_id'] as String?;
  String? get _mentionProjectPath => _mentionLink?['local_path'] as String?;

  void _save() {
    final title = _titleController.text.trim();
    if (title.isEmpty) {
      setState(() => _titleError = true);
      return;
    }
    final desc = _descController.text.trim();
    Navigator.pop(context, <String, dynamic>{
      'title': title,
      'description': desc.isEmpty ? null : desc,
      'status': _status,
      'priority': _priority,
      'project_id': _projectId,
      'label_ids': _labelIds.toList(),
    });
  }

  Future<void> _pickStatus(AppLocalizations l10n) async {
    final picked = await showAnchoredSingleSelect<String>(
      context: context,
      anchorKey: _statusKey,
      selected: _status,
      options: [
        for (final s in tutils.kTaskStatusOrder)
          PickerOption(
            value: s,
            leading: TaskStatusIcon(status: s, size: 16.0),
            label: taskStatusLabel(l10n, s),
          ),
      ],
    );
    if (picked != null) setState(() => _status = picked);
  }

  Future<void> _pickPriority(AppLocalizations l10n) async {
    final picked = await showAnchoredSingleSelect<String>(
      context: context,
      anchorKey: _priorityKey,
      selected: _priority,
      options: [
        for (final p in tutils.kTaskPriorityOrder)
          PickerOption(
            value: p,
            leading: TaskPriorityIcon(priority: p, size: 16.0),
            label: taskPriorityLabel(l10n, p),
          ),
      ],
    );
    if (picked != null) setState(() => _priority = picked);
  }

  Future<void> _pickProject(AppLocalizations l10n) async {
    if (widget.projects.isEmpty) return;
    final picked = await showAnchoredSingleSelect<String>(
      context: context,
      anchorKey: _projectKey,
      selected: _projectId,
      options: [
        for (final p in widget.projects)
          PickerOption(
            value: tutils.projectId(p),
            leading: TaskProjectIcon(project: p, size: 16.0),
            label:
                tutils.projectIsInbox(p) ? l10n.tasksInbox : tutils.projectName(p),
          ),
      ],
    );
    if (picked != null) setState(() => _projectId = picked);
  }

  Future<void> _pickLabels(AppLocalizations l10n) async {
    if (widget.labels.isEmpty) return;
    await showAnchoredMultiSelect(
      context: context,
      anchorKey: _labelsKey,
      labels: widget.labels,
      selected: _labelIds,
      onToggle: (id) => setState(() {
        if (!_labelIds.remove(id)) _labelIds.add(id);
      }),
    );
  }

  String _projectPillLabel(AppLocalizations l10n) {
    final p = _selectedProject;
    if (p == null) return l10n.tasksInbox;
    return tutils.projectIsInbox(p) ? l10n.tasksInbox : tutils.projectName(p);
  }

  String _labelsPillLabel(AppLocalizations l10n) {
    if (_labelIds.isEmpty) return l10n.tasksLabelsButton;
    final names = <String>[];
    for (final l in widget.labels) {
      if (_labelIds.contains(tutils.labelId(l))) names.add(tutils.labelName(l));
    }
    if (names.length <= 2) return names.join(', ');
    return '${names.take(2).join(', ')} +${names.length - 2}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final maxHeight = MediaQuery.of(context).size.height * 0.9;

    return Container(
      constraints: BoxConstraints(maxHeight: maxHeight),
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24.0)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              margin: const EdgeInsets.only(top: 12.0, bottom: 4.0),
              width: 40.0,
              height: 4.0,
              decoration: BoxDecoration(
                color: theme.alternate,
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
            Padding(
              padding:
                  const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 8.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  FlutterFlowIconButton(
                    borderColor: theme.alternate,
                    borderRadius: 10.0,
                    borderWidth: 1.0,
                    buttonSize: 40.0,
                    icon: Icon(Icons.close_rounded,
                        color: theme.secondaryText, size: 20.0),
                    onPressed: () => Navigator.pop(context),
                  ),
                  Text(
                    _isEditing ? l10n.tasksEditTask : l10n.tasksNewTask,
                    style: theme.titleLarge.override(
                      font: GoogleFonts.sourceSans3(),
                      color: theme.primaryText,
                      fontSize: 19.0,
                      letterSpacing: 0.0,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  FlutterFlowIconButton(
                    borderColor: theme.primary,
                    borderRadius: 10.0,
                    borderWidth: 1.0,
                    buttonSize: 40.0,
                    fillColor: theme.primary,
                    icon: Icon(Icons.check_rounded,
                        color: theme.info, size: 20.0),
                    onPressed: _save,
                  ),
                ],
              ),
            ),
            Flexible(
              // Tapping empty space in the form drops the keyboard.
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: dismissKeyboard,
                child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20.0, 16.0, 20.0, 24.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      controller: _titleController,
                      autofocus: !_isEditing,
                      textCapitalization: TextCapitalization.sentences,
                      onChanged: (_) {
                        if (_titleError) setState(() => _titleError = false);
                      },
                      style: theme.titleLarge.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        fontSize: 19.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w600,
                      ),
                      decoration: InputDecoration(
                        isCollapsed: true,
                        border: InputBorder.none,
                        hintText: l10n.tasksTitlePlaceholder,
                        hintStyle: theme.titleLarge.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText.withValues(alpha: 0.5),
                          fontSize: 19.0,
                          letterSpacing: 0.0,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    if (_titleError)
                      Padding(
                        padding: const EdgeInsets.only(top: 6.0),
                        child: Text(
                          l10n.tasksTitleRequired,
                          style: theme.labelSmall.override(
                            font: GoogleFonts.sourceSans3(),
                            color: const Color(0xFFEF4444),
                            letterSpacing: 0.0,
                          ),
                        ),
                      ),
                    const SizedBox(height: 12.0),
                    MentionPromptField(
                      controller: _descController,
                      machineId: _mentionMachineId,
                      projectPath: _mentionProjectPath,
                      // Tasks have no agent of their own; Claude's command +
                      // skill set is the sensible default for the `/` menu.
                      agentType: 'claude',
                      maxLines: 5,
                      minLines: 2,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        letterSpacing: 0.0,
                      ),
                      decoration: InputDecoration(
                        isCollapsed: true,
                        border: InputBorder.none,
                        hintText: l10n.tasksDescriptionPlaceholder,
                        hintStyle: theme.bodyMedium.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText.withValues(alpha: 0.6),
                          letterSpacing: 0.0,
                        ),
                      ),
                    ),
                    const SizedBox(height: 20.0),
                    Wrap(
                      spacing: 8.0,
                      runSpacing: 8.0,
                      children: [
                        PillButton(
                          key: _statusKey,
                          leading: TaskStatusIcon(status: _status, size: 14.0),
                          label: taskStatusLabel(l10n, _status),
                          onTap: () => _pickStatus(l10n),
                        ),
                        PillButton(
                          key: _priorityKey,
                          leading:
                              TaskPriorityIcon(priority: _priority, size: 14.0),
                          label: taskPriorityLabel(l10n, _priority),
                          onTap: () => _pickPriority(l10n),
                        ),
                        if (widget.projects.isNotEmpty)
                          PillButton(
                            key: _projectKey,
                            leading: TaskProjectIcon(
                                project: _selectedProject, size: 14.0),
                            label: _projectPillLabel(l10n),
                            onTap: () => _pickProject(l10n),
                          ),
                        if (widget.labels.isNotEmpty)
                          PillButton(
                            key: _labelsKey,
                            leading: Icon(Icons.sell_outlined,
                                size: 14.0, color: theme.secondaryText),
                            label: _labelsPillLabel(l10n),
                            onTap: () => _pickLabels(l10n),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
