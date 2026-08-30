import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/custom_code/widgets/index.dart';
import 'home_model.dart';

const List<String> _kGroupByOptions = ['Project', 'Status', 'Time'];
const Map<String, IconData> _kGroupByIcons = {
  'Project': Icons.folder_outlined,
  'Status': Icons.adjust_rounded,
  'Time': Icons.access_time_rounded,
};
const List<String> _kStatusOptions = [
  'All',
  'Not closed',
  'In progress',
  'In review',
  'Done',
  'Closed',
];
const List<String> _kDateRangeOptions = [
  'All Time',
  'Today',
  'Last 7 Days',
  'Custom Range',
];
const List<String> _kAgentTypeOptions = [
  'All',
  'Claude Code',
  'Codex',
  'OpenCode',
];

Future<void> showAgentFiltersPanel({
  required BuildContext context,
  required HomeModel model,
  required VoidCallback onStateChanged,
  required GlobalKey anchorKey,
}) async {
  final renderBox =
      anchorKey.currentContext?.findRenderObject() as RenderBox?;
  if (renderBox == null) return;

  final buttonOffset = renderBox.localToGlobal(Offset.zero);
  final buttonSize = renderBox.size;
  final screenWidth = MediaQuery.of(context).size.width;

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
                child: AgentFiltersPanel(
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

class AgentFiltersPanel extends StatefulWidget {
  const AgentFiltersPanel({
    super.key,
    required this.model,
    required this.onStateChanged,
  });

  final HomeModel model;
  final VoidCallback onStateChanged;

  @override
  State<AgentFiltersPanel> createState() => _AgentFiltersPanelState();
}

class _AgentFiltersPanelState extends State<AgentFiltersPanel> {
  bool _groupByExpanded = false;
  bool _filterExpanded = false;

  void _onGroupBySelected(String value) {
    HapticFeedback.lightImpact();
    setState(() {
      widget.model.selectGroupBy(value);
    });
    widget.onStateChanged();
  }

  void _onStatusSelected(String value) {
    HapticFeedback.lightImpact();
    setState(() {
      widget.model.selectTab(value);
    });
    widget.onStateChanged();
  }

  Future<void> _onDateRangeSelected(String value) async {
    HapticFeedback.lightImpact();
    if (value == 'Custom Range') {
      final now = DateTime.now();
      final initialStart = widget.model.customDateRange?.start ??
          now.subtract(const Duration(days: 6));
      final initialEnd = widget.model.customDateRange?.end ?? now;
      final normalizedEnd =
          initialEnd.isBefore(initialStart) ? initialStart : initialEnd;

      final pickedRange = await showModalBottomSheet<DateTimeRange?>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        isDismissible: true,
        enableDrag: true,
        builder: (context) => CustomDateRangeSheet(
          initialStart: initialStart,
          initialEnd: normalizedEnd,
        ),
      );

      if (pickedRange != null) {
        setState(() {
          widget.model.selectCustomDateRange(pickedRange);
        });
        widget.onStateChanged();
      }
    } else {
      setState(() {
        widget.model.selectDateRange(value);
      });
      widget.onStateChanged();
    }
  }

  void _onAgentTypeSelected(String value) {
    HapticFeedback.lightImpact();
    setState(() {
      widget.model.selectAgentType(value);
    });
    widget.onStateChanged();
  }

  String _selectedDateRangeOption() {
    return widget.model.selectedDateRange == 'Custom'
        ? 'Custom Range'
        : widget.model.selectedDateRange;
  }

  bool _hasActiveFilter() {
    return widget.model.selectedTab != 'All' ||
        widget.model.selectedDateRange != 'All Time' ||
        widget.model.selectedAgentType != 'All';
  }

  bool _hasNonDefaultGroupBy() {
    return widget.model.selectedGroupBy != 'Time';
  }

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
                padding: const EdgeInsets.symmetric(vertical: 0.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _buildCollapsibleSection(
                      title: 'Group By',
                      isExpanded: _groupByExpanded,
                      hasActive: _hasNonDefaultGroupBy(),
                      onToggle: () => setState(
                          () => _groupByExpanded = !_groupByExpanded),
                      content: Column(
                        children: [
                          for (final opt in _kGroupByOptions)
                            _buildOptionRow(
                              label: opt,
                              isSelected:
                                  widget.model.selectedGroupBy == opt,
                              onTap: () => _onGroupBySelected(opt),
                              icon: _kGroupByIcons[opt],
                            ),
                        ],
                      ),
                    ),
                    _buildHorizontalDivider(),
                    _buildCollapsibleSection(
                      title: 'Filter',
                      isExpanded: _filterExpanded,
                      hasActive: _hasActiveFilter(),
                      onToggle: () => setState(
                          () => _filterExpanded = !_filterExpanded),
                      content: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildSectionHeader('STATUS'),
                          for (final opt in _kStatusOptions)
                            _buildOptionRow(
                              label: opt,
                              isSelected: widget.model.selectedTab == opt,
                              onTap: () => _onStatusSelected(opt),
                            ),
                          _buildHorizontalDivider(),
                          _buildSectionHeader('DATE RANGE'),
                          for (final opt in _kDateRangeOptions)
                            _buildOptionRow(
                              label: opt == 'Custom Range' &&
                                      widget.model.selectedDateRange ==
                                          'Custom' &&
                                      widget.model.customDateRange != null
                                  ? widget.model.selectedDateFilterLabel
                                  : opt,
                              isSelected: _selectedDateRangeOption() == opt,
                              onTap: () => _onDateRangeSelected(opt),
                              trailingChevron: opt == 'Custom Range',
                            ),
                          _buildHorizontalDivider(),
                          _buildSectionHeader('AGENT TYPE'),
                          for (final opt in _kAgentTypeOptions)
                            _buildOptionRow(
                              label: opt,
                              isSelected:
                                  widget.model.selectedAgentType == opt,
                              onTap: () => _onAgentTypeSelected(opt),
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
    required bool hasActive,
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
            padding: const EdgeInsets.symmetric(
                horizontal: 16.0, vertical: 13.0),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    localizedFilterLabel(title),
                    style: theme.bodyLarge.override(
                      font: GoogleFonts.sourceSans3(
                          fontWeight: FontWeight.w500),
                      fontSize: 16.0,
                      color: theme.primaryText,
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

  Widget _buildSectionHeader(String title) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16.0, 10.0, 16.0, 3.0),
      child: Text(
        localizedFilterLabel(title),
        style: theme.bodySmall.override(
          font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500),
          fontSize: 10.5,
          color: theme.secondaryText.withValues(alpha: 0.75),
          letterSpacing: 0.8,
        ),
      ),
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
    bool trailingChevron = false,
    IconData? icon,
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
                child: Icon(Icons.check_rounded, color: theme.primaryText, size: 17.0),
              )
            else
              const SizedBox(width: 25.0),
            if (icon != null)
              Padding(
                padding: const EdgeInsets.only(right: 7.0),
                child: Icon(
                  icon,
                  color: theme.secondaryText.withValues(alpha: 0.55),
                  size: 15.0,
                ),
              ),
            Expanded(
              child: Text(
                localizedFilterLabel(label),
                style: theme.bodyMedium.override(
                  fontWeight: FontWeight.w400,
                  color: theme.primaryText,
                  fontSize: 15.0,
                ),
              ),
            ),
            if (trailingChevron)
              Icon(
                Icons.chevron_right_rounded,
                color: theme.secondaryText.withValues(alpha: 0.45),
                size: 17.0,
              ),
          ],
        ),
      ),
    );
  }
}
