import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/filter_panel.dart';
import 'automations_model.dart';

/// Anchored filter dropdown for the Automations page, the same panel as the
/// Tasks filter: a single-select "Project" section first, matched against each
/// automation's derived project, then "Status" (All / Active / Paused).
Future<void> showAutomationFilterPanel({
  required BuildContext context,
  required AutomationsModel model,
  required GlobalKey anchorKey,
}) {
  return showAnchoredFilterPanel(
    context: context,
    anchorKey: anchorKey,
    builder: (_) => _AutomationFilterPanel(model: model),
  );
}

class _AutomationFilterPanel extends StatefulWidget {
  const _AutomationFilterPanel({required this.model});

  final AutomationsModel model;

  @override
  State<_AutomationFilterPanel> createState() => _AutomationFilterPanelState();
}

class _AutomationFilterPanelState extends State<_AutomationFilterPanel> {
  void _selectStatus(String value) {
    HapticFeedback.lightImpact();
    setState(() => widget.model.setFilter(value));
  }

  void _selectProject(String? id) {
    HapticFeedback.lightImpact();
    setState(() => widget.model.setProjectFilter(id));
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final m = widget.model;
    Widget statusRow(String value, IconData icon, String label) =>
        FilterOptionRow(
          label: label,
          isSelected: m.filter == value,
          onTap: () => _selectStatus(value),
          leading: Icon(icon, size: 16.0, color: theme.secondaryText),
        );

    return FilterPanelCard(
      children: [
        FilterPanelSection(
          title: l10n.filterProject,
          children: projectFilterOptions(
            l10n: l10n,
            projects: m.projects,
            selected: m.projectFilter,
            onSelect: _selectProject,
          ),
        ),
        const FilterPanelDivider(),
        FilterPanelSection(
          title: l10n.filterStatus,
          children: [
            statusRow('all', Icons.all_inclusive_rounded,
                l10n.automationsFilterAll),
            statusRow('active', Icons.circle_outlined,
                l10n.automationsFilterActive),
            statusRow('paused', Icons.pause_circle_outline_rounded,
                l10n.automationsFilterPaused),
            const SizedBox(height: 8.0),
          ],
        ),
      ],
    );
  }
}
