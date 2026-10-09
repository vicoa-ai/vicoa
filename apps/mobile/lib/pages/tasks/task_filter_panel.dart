import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/l10n/app_localizations.dart';
import '/pages/common/filter_panel.dart';
import 'tasks_model.dart';

/// Anchored filter/display dropdown for the Tasks page (chrome shared with the
/// Automations page, see `filter_panel.dart`). "Project" is single-select;
/// "Display" is a set of multi-select toggles (status / priority / project /
/// labels) controlling which chips the cards show.
Future<void> showTaskFilterPanel({
  required BuildContext context,
  required TasksModel model,
  required VoidCallback onStateChanged,
  required GlobalKey anchorKey,
}) {
  return showAnchoredFilterPanel(
    context: context,
    anchorKey: anchorKey,
    builder: (_) =>
        TaskFilterPanel(model: model, onStateChanged: onStateChanged),
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
    final l10n = AppLocalizations.of(context);
    final m = widget.model;

    return FilterPanelCard(
      children: [
        FilterPanelSection(
          title: l10n.tasksPropProject,
          children: projectFilterOptions(
            l10n: l10n,
            projects: m.projects,
            selected: m.projectFilter,
            onSelect: _selectProject,
          ),
        ),
        const FilterPanelDivider(),
        FilterPanelSection(
          title: l10n.tasksDisplay,
          children: [
            FilterOptionRow(
              label: l10n.tasksPropStatus,
              isSelected: m.showStatus,
              onTap: () => _toggleDisplay(status: !m.showStatus),
            ),
            FilterOptionRow(
              label: l10n.tasksPropPriority,
              isSelected: m.showPriority,
              onTap: () => _toggleDisplay(priority: !m.showPriority),
            ),
            FilterOptionRow(
              label: l10n.tasksPropProject,
              isSelected: m.showProject,
              onTap: () => _toggleDisplay(project: !m.showProject),
            ),
            FilterOptionRow(
              label: l10n.tasksLabelsButton,
              isSelected: m.showLabels,
              onTap: () => _toggleDisplay(labels: !m.showLabels),
            ),
            const SizedBox(height: 8.0),
          ],
        ),
      ],
    );
  }
}
