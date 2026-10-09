import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/task_utils.dart' as tutils;
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/tasks/task_glyphs.dart';

/// Anchored filter dropdown shared by the Tasks and Automations pages, styled
/// to match the Home page's `agent_filters_panel.dart`: collapsible sections
/// with a chevron and left-check option rows. [builder] returns the panel body
/// (a [FilterPanelCard]); it should be a StatefulWidget that calls setState on
/// a pick, since the dropdown is its own route and won't rebuild with the page.
Future<void> showAnchoredFilterPanel({
  required BuildContext context,
  required GlobalKey anchorKey,
  required WidgetBuilder builder,
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
                child: builder(dialogContext),
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

/// The panel's rounded, shadowed surface; [children] scroll when tall.
class FilterPanelCard extends StatelessWidget {
  const FilterPanelCard({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
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
                child: Column(mainAxisSize: MainAxisSize.min, children: children),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A titled section that collapses under its chevron. Starts expanded each
/// time the panel opens.
class FilterPanelSection extends StatefulWidget {
  const FilterPanelSection({super.key, required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  State<FilterPanelSection> createState() => _FilterPanelSectionState();
}

class _FilterPanelSectionState extends State<FilterPanelSection> {
  bool _expanded = true;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        InkWell(
          onTap: () {
            HapticFeedback.selectionClick();
            setState(() => _expanded = !_expanded);
          },
          child: Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 16.0, vertical: 13.0),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    widget.title,
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
                  turns: _expanded ? 0.25 : 0.0,
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
            child: _expanded
                ? Column(children: widget.children)
                : const SizedBox.shrink(),
          ),
        ),
      ],
    );
  }
}

class FilterPanelDivider extends StatelessWidget {
  const FilterPanelDivider({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Divider(
      height: 1.0,
      thickness: 0.5,
      color: theme.secondaryText.withValues(alpha: 0.1),
    );
  }
}

/// One option: a check when selected, an optional [leading] glyph, the label.
class FilterOptionRow extends StatelessWidget {
  const FilterOptionRow({
    super.key,
    required this.label,
    required this.isSelected,
    required this.onTap,
    this.leading,
  });

  final String label;
  final bool isSelected;
  final VoidCallback onTap;
  final Widget? leading;

  @override
  Widget build(BuildContext context) {
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

/// The single-select project options: All projects, each project, then No
/// project pinned last like the sidebar's bucket. [selected] is null for all,
/// [tutils.kNoProjectFilter] for unfiled, otherwise a project id.
List<Widget> projectFilterOptions({
  required AppLocalizations l10n,
  required List<dynamic> projects,
  required String? selected,
  required ValueChanged<String?> onSelect,
}) {
  return [
    FilterOptionRow(
      label: l10n.tasksAllProjects,
      isSelected: selected == null,
      onTap: () => onSelect(null),
    ),
    for (final p in projects)
      FilterOptionRow(
        label: tutils.projectName(p),
        isSelected: selected == tutils.projectId(p),
        onTap: () => onSelect(tutils.projectId(p)),
        leading: TaskProjectIcon(project: p, size: 15.0),
      ),
    FilterOptionRow(
      label: l10n.tasksNoProject,
      isSelected: selected == tutils.kNoProjectFilter,
      onTap: () => onSelect(tutils.kNoProjectFilter),
      leading: const TaskProjectIcon(project: null, size: 15.0),
    ),
  ];
}

/// Keeps the rows whose [projectIdOf] matches a project filter value (see
/// [projectFilterOptions]); a null filter keeps everything.
List<T> filterByProject<T>(
    List<T> rows, String? filter, String? Function(T) projectIdOf) {
  if (filter == null) return rows;
  if (filter == tutils.kNoProjectFilter) {
    return rows.where((r) => projectIdOf(r) == null).toList();
  }
  return rows.where((r) => projectIdOf(r) == filter).toList();
}
