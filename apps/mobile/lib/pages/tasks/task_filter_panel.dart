import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'task_glyphs.dart';
import 'tasks_model.dart';

/// Anchored filter/display dropdown for the Tasks page, styled to match the
/// Home page's `agent_filters_panel.dart`: collapsible sections with a chevron
/// and left-check option rows. "Project" is single-select; "Display" is a set
/// of multi-select toggles (status / priority / project / labels) controlling
/// which chips the cards show.
Future<void> showTaskFilterPanel({
  required BuildContext context,
  required TasksModel model,
  required VoidCallback onStateChanged,
  required GlobalKey anchorKey,
}) async {
  final renderBox = anchorKey.currentContext?.findRenderObject() as RenderBox?;
  if (renderBox == null) return;

  final buttonOffset = renderBox.localToGlobal(Offset.zero);
  final buttonSize = renderBox.size;
  final screenWidth = MediaQuery.of(context).size.width;

  // Match the Home agent-filters panel width (agent_filters_panel.dart).
  const dropdownWidth = 180.0;
  const gap = 6.0;

  final top = buttonOffset.dy + buttonSize.height + gap;
  final right = screenWidth - buttonOffset.dx - buttonSize.width - 16.0;
  final clampedRight = right.clamp(8.0, screenWidth - dropdownWidth - 8.0);

  await showGeneralDialog<void>(
    context: context,
    barrierDismissible: true,
    barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
    barrierColor: Colors.transparent,
    transitionDuration: const Duration(milliseconds: 180),
    pageBuilder: (dialogContext, _, __) {
      return Stack(
        children: [
          Positioned(
            top: top,
            right: clampedRight,
            width: dropdownWidth,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16.0),
              child: Material(
                type: MaterialType.transparency,
                child: TaskFilterPanel(
                  model: model,
                  onStateChanged: onStateChanged,
                ),
              ),
            ),
          ),
        ],
      );
    },
    transitionBuilder: (ctx, animation, _, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: Curves.easeOutCubic,
        reverseCurve: Curves.easeInCubic,
      );
      return FadeTransition(
        opacity: curved,
        child: ScaleTransition(
          scale: Tween<double>(begin: 0.88, end: 1.0).animate(curved),
          alignment: Alignment.topRight,
          child: child,
        ),
      );
    },
  );
}

class TaskFilterPanel extends StatefulWidget {
  const TaskFilterPanel({
    super.key,
    required this.model,
    required this.onStateChanged,
  });

  final TasksModel model;
  final VoidCallback onStateChanged;

  @override
  State<TaskFilterPanel> createState() => _TaskFilterPanelState();
}

class _TaskFilterPanelState extends State<TaskFilterPanel> {
  bool _projectExpanded = true;
  bool _displayExpanded = true;

  void _selectProject(String? id) {
    HapticFeedback.lightImpact();
    setState(() => widget.model.setProjectFilter(id));
    widget.onStateChanged();
  }

  void _toggleDisplay({bool? status, bool? priority, bool? project, bool? labels}) {
    HapticFeedback.lightImpact();
    setState(() => widget.model.setDisplay(
        status: status, priority: priority, project: project, labels: labels));
    widget.onStateChanged();
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final m = widget.model;

    return Container(
      constraints: const BoxConstraints(maxHeight: 540.0),
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
        border: Border.all(
          color: theme.secondaryText.withValues(alpha: 0.25),
          width: 0.75,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.14),
            blurRadius: 28.0,
            offset: const Offset(0, 10),
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 8.0,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _buildCollapsibleSection(
                      title: l10n.tasksPropProject,
                      isExpanded: _projectExpanded,
                      onToggle: () => setState(
                          () => _projectExpanded = !_projectExpanded),
                      content: Column(
                        children: [
                          _buildOptionRow(
                            label: l10n.tasksAllProjects,
                            isSelected: m.projectFilter == null,
                            onTap: () => _selectProject(null),
                          ),
                          for (final p in m.projects)
                            _buildOptionRow(
                              label: tutils.projectIsInbox(p)
                                  ? l10n.tasksInbox
                                  : tutils.projectName(p),
                              isSelected:
                                  m.projectFilter == tutils.projectId(p),
                              onTap: () =>
                                  _selectProject(tutils.projectId(p)),
                              leading: TaskProjectIcon(project: p, size: 15.0),
                            ),
                        ],
                      ),
                    ),
                    _buildHorizontalDivider(),
                    _buildCollapsibleSection(
                      title: l10n.tasksDisplay,
                      isExpanded: _displayExpanded,
                      onToggle: () => setState(
                          () => _displayExpanded = !_displayExpanded),
                      content: Column(
                        children: [
                          _buildOptionRow(
                            label: l10n.tasksPropStatus,
                            isSelected: m.showStatus,
                            onTap: () =>
                                _toggleDisplay(status: !m.showStatus),
                          ),
                          _buildOptionRow(
                            label: l10n.tasksPropPriority,
                            isSelected: m.showPriority,
                            onTap: () =>
                                _toggleDisplay(priority: !m.showPriority),
                          ),
                          _buildOptionRow(
                            label: l10n.tasksPropProject,
                            isSelected: m.showProject,
                            onTap: () =>
                                _toggleDisplay(project: !m.showProject),
                          ),
                          _buildOptionRow(
                            label: l10n.tasksLabelsButton,
                            isSelected: m.showLabels,
                            onTap: () =>
                                _toggleDisplay(labels: !m.showLabels),
                          ),
                          const SizedBox(height: 8.0),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCollapsibleSection({
    required String title,
    required bool isExpanded,
    required VoidCallback onToggle,
    required Widget content,
  }) {
    final theme = FlutterFlowTheme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        InkWell(
          onTap: () {
            HapticFeedback.selectionClick();
            onToggle();
          },
          child: Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 16.0, vertical: 13.0),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: theme.bodyLarge.override(
                      font:
                          GoogleFonts.sourceSans3(fontWeight: FontWeight.w500),
                      fontSize: 16.0,
                      color: theme.primaryText,
                      letterSpacing: 0.0,
                    ),
                  ),
                ),
                AnimatedRotation(
                  turns: isExpanded ? 0.25 : 0.0,
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeInOut,
                  child: Icon(
                    Icons.chevron_right_rounded,
                    color: theme.secondaryText.withValues(alpha: 0.5),
                    size: 20.0,
                  ),
                ),
              ],
            ),
          ),
        ),
        ClipRect(
          child: AnimatedSize(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: isExpanded ? content : const SizedBox.shrink(),
          ),
        ),
      ],
    );
  }

  Widget _buildHorizontalDivider() {
    final theme = FlutterFlowTheme.of(context);
    return Divider(
      height: 1.0,
      thickness: 0.5,
      color: theme.secondaryText.withValues(alpha: 0.1),
    );
  }

  Widget _buildOptionRow({
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
    Widget? leading,
  }) {
    final theme = FlutterFlowTheme.of(context);
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding:
            const EdgeInsets.symmetric(horizontal: 16.0, vertical: 10.0),
        child: Row(
          children: [
            if (isSelected)
              Padding(
                padding: const EdgeInsets.only(right: 8.0),
                child: Icon(Icons.check_rounded,
                    color: theme.primaryText, size: 17.0),
              )
            else
              const SizedBox(width: 25.0),
            if (leading != null)
              Padding(
                padding: const EdgeInsets.only(right: 7.0),
                child: leading,
              ),
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  fontWeight: FontWeight.w400,
                  color: theme.primaryText,
                  fontSize: 15.0,
                  letterSpacing: 0.0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
