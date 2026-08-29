import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/widgets/index.dart';
import 'home_model.dart';

class HomeFilterToggleButton extends StatelessWidget {
  const HomeFilterToggleButton({
    super.key,
    required this.model,
    required this.onToggle,
  });

  final HomeModel model;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    return FlutterFlowIconButton(
      borderRadius: 10.0,
      borderWidth: 0,
      buttonSize: 40.0,
      fillColor: Colors.transparent,
      icon: Icon(
        model.showFilters
            ? Icons.filter_list_off_outlined
            : Icons.filter_list_rounded,
        color: FlutterFlowTheme.of(context).primaryText,
        size: 22.0,
      ),
      onPressed: () {
        logFirebaseEvent('HOME_PAGE_filter_ICN_ON_TAP');
        HapticFeedback.lightImpact();
        onToggle();
      },
    );
  }
}

class HomeFilterBar extends StatelessWidget {
  const HomeFilterBar({
    super.key,
    required this.model,
    required this.onStateChanged,
  });

  final HomeModel model;
  final VoidCallback onStateChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 44.0,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16.0),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              buildFilterChip(
                context: context,
                label: localizedFilterLabel('Group By'),
                onTap: () async {
                  HapticFeedback.lightImpact();
                  await showFilterModal(
                    context: context,
                    title: 'Group By',
                    options: const ['Project', 'Status', 'Time'],
                    selectedValue: model.selectedGroupBy,
                    onSelected: (value) async {
                      model.selectGroupBy(value);
                      onStateChanged();
                    },
                  );
                },
              ),
              const SizedBox(width: 12.0),
              buildFilterChip(
                context: context,
                label: model.selectedTab == 'All'
                    ? localizedFilterLabel('Status')
                    : localizedFilterLabel(model.selectedTab),
                onTap: () async {
                  HapticFeedback.lightImpact();
                  await showFilterModal(
                    context: context,
                    title: 'Status',
                    options: const ['All', 'Not closed', 'In progress', 'In review', 'Done', 'Closed'],
                    selectedValue: model.selectedTab,
                    onSelected: (value) async {
                      model.selectTab(value);
                      onStateChanged();
                    },
                  );
                },
              ),
              const SizedBox(width: 12.0),
              buildFilterChip(
                context: context,
                label: model.dateRangeChipLabel,
                onTap: () async {
                  HapticFeedback.lightImpact();
                  await showFilterModal(
                    context: context,
                    title: 'Date Range',
                    options: const ['All Time', 'Today', 'Last 7 Days', 'Custom Range'],
                    selectedValue: model.selectedDateRange == 'Custom'
                        ? 'Custom Range'
                        : model.selectedDateRange,
                    onSelected: (value) async {
                      if (value == 'Custom Range') {
                        final now = DateTime.now();
                        final initialStart =
                            model.customDateRange?.start ?? now.subtract(const Duration(days: 6));
                        final initialEnd = model.customDateRange?.end ?? now;
                        final normalizedEnd =
                            initialEnd.isBefore(initialStart) ? initialStart : initialEnd;

                        final pickedRange = await showCustomDateRangePicker(
                          context: context,
                          initialStart: initialStart,
                          initialEnd: normalizedEnd,
                        );

                        if (pickedRange != null) {
                          model.selectCustomDateRange(pickedRange);
                          onStateChanged();
                        }
                      } else {
                        model.selectDateRange(value);
                        onStateChanged();
                      }
                    },
                  );
                },
              ),
              const SizedBox(width: 12.0),
              buildFilterChip(
                context: context,
                label: model.selectedAgentType == 'All'
                    ? localizedFilterLabel('Type')
                    : localizedFilterLabel(model.selectedAgentType),
                onTap: () async {
                  HapticFeedback.lightImpact();
                  await showFilterModal(
                    context: context,
                    title: 'Agent Type',
                    options: const ['All', 'Claude Code', 'Codex', 'OpenCode'],
                    selectedValue: model.selectedAgentType,
                    onSelected: (value) async {
                      model.selectAgentType(value);
                      onStateChanged();
                    },
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Widget buildFilterChip({
  required BuildContext context,
  required String label,
  required VoidCallback onTap,
}) {
  return GestureDetector(
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 18.0, vertical: 10.0),
      decoration: BoxDecoration(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(24.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
                  color: FlutterFlowTheme.of(context).secondaryText,
                  fontSize: 14.0,
                ),
          ),
          const SizedBox(width: 8.0),
          Icon(
            Icons.keyboard_arrow_down_rounded,
            color: FlutterFlowTheme.of(context).secondaryText,
            size: 20.0,
          ),
        ],
      ),
    ),
  );
}

Future<void> showFilterModal({
  required BuildContext context,
  required String title,
  required List<String> options,
  required String selectedValue,
  required Future<void> Function(String) onSelected,
}) async {
  final selected = await showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    isDismissible: true,
    enableDrag: true,
    builder: (context) => FilterOptionsSheet(
      title: title,
      options: options,
      selectedValue: selectedValue,
    ),
  );

  if (selected != null) {
    await onSelected(selected);
  }
}

Future<DateTimeRange?> showCustomDateRangePicker({
  required BuildContext context,
  required DateTime initialStart,
  required DateTime initialEnd,
}) async {
  return await showModalBottomSheet<DateTimeRange?>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    isDismissible: true,
    enableDrag: true,
    builder: (context) => CustomDateRangeSheet(
      initialStart: initialStart,
      initialEnd: initialEnd,
    ),
  );
}

class FilterOptionsSheet extends StatelessWidget {
  const FilterOptionsSheet({
    super.key,
    required this.title,
    required this.options,
    required this.selectedValue,
  });

  final String title;
  final List<String> options;
  final String selectedValue;

  @override
  Widget build(BuildContext context) {
    final sheetHeight = title == 'Status' ? 560.0 : title == 'Group By' ? 360.0 : 420.0;
    return Container(
      height: sheetHeight,
      child: Container(
        decoration: BoxDecoration(
          color: FlutterFlowTheme.of(context).secondaryBackground,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(20.0),
            topRight: Radius.circular(20.0),
          ),
        ),
        child: Column(
          children: [
            Container(
              width: 40.0,
              height: 4.0,
              margin: const EdgeInsets.only(top: 12.0, bottom: 8.0),
              decoration: BoxDecoration(
                color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(20.0, 8.0, 20.0, 20.0),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  localizedFilterLabel(title),
                  style: FlutterFlowTheme.of(context).titleLarge.override(
                        fontSize: 22.0,
                      ),
                ),
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsetsDirectional.fromSTEB(20.0, 0.0, 20.0, 32.0),
                children: options.map((option) {
                  final isSelected = selectedValue == option;
                  return Container(
                    margin: const EdgeInsets.only(bottom: 16.0),
                    child: Material(
                      color: Colors.transparent,
                      child: InkWell(
                        borderRadius: BorderRadius.circular(12.0),
                        onTap: () {
                          HapticFeedback.lightImpact();
                          Navigator.of(context).pop(option);
                        },
                        child: Container(
                          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 16.0),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? FlutterFlowTheme.of(context).primary.withValues(alpha: 0.1)
                                : FlutterFlowTheme.of(context).primaryBackground,
                            borderRadius: BorderRadius.circular(12.0),
                            border: Border.all(
                              color: isSelected
                                  ? FlutterFlowTheme.of(context).primary
                                  : FlutterFlowTheme.of(context)
                                      .secondaryText
                                      .withValues(alpha: 0.2),
                              width: isSelected ? 2.0 : 1.0,
                            ),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  localizedFilterLabel(option),
                                  style: FlutterFlowTheme.of(context).bodyLarge.override(
                                        fontWeight:
                                            isSelected ? FontWeight.w600 : FontWeight.w500,
                                        color: isSelected
                                            ? FlutterFlowTheme.of(context).primary
                                            : FlutterFlowTheme.of(context).primaryText,
                                        fontSize: 16.0,
                                      ),
                                ),
                              ),
                              if (isSelected)
                                Icon(
                                  Icons.check_rounded,
                                  color: FlutterFlowTheme.of(context).primary,
                                  size: 20.0,
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
