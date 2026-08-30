import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/l10n/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class CustomDateRangeSheet extends StatefulWidget {
  const CustomDateRangeSheet({
    super.key,
    required this.initialStart,
    required this.initialEnd,
  });

  final DateTime initialStart;
  final DateTime initialEnd;

  @override
  State<CustomDateRangeSheet> createState() => _CustomDateRangeSheetState();
}

class _CustomDateRangeSheetState extends State<CustomDateRangeSheet> {
  late DateTime selectedStart;
  late DateTime selectedEnd;
  bool isSelectingStart = true;

  @override
  void initState() {
    super.initState();
    selectedStart = widget.initialStart;
    selectedEnd = widget.initialEnd;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.75,
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
                color: FlutterFlowTheme.of(context)
                    .secondaryText
                    .withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(20.0, 8.0, 20.0, 16.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    AppLocalizations.of(context).dateRangeXTitle,
                    style: FlutterFlowTheme.of(context).titleLarge.override(
                          fontSize: 20.0,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                  FlutterFlowIconButton(
                    borderRadius: 12.0,
                    borderWidth: 1.0,
                    buttonSize: 36.0,
                    fillColor: FlutterFlowTheme.of(context).primaryBackground,
                    icon: Icon(
                      Icons.close_rounded,
                      color: FlutterFlowTheme.of(context).secondaryText,
                      size: 18.0,
                    ),
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      Navigator.of(context).pop();
                    },
                  ),
                ],
              ),
            ),
            
            // Date range display
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20.0),
              child: Row(
                children: [
                  Expanded(
                    child: _buildDateSelector(
                      title: AppLocalizations.of(context).dateRangeXStartDate,
                      date: selectedStart,
                      isSelected: isSelectingStart,
                      onTap: () {
                        setState(() {
                          isSelectingStart = true;
                        });
                        HapticFeedback.selectionClick();
                      },
                    ),
                  ),
                  const SizedBox(width: 16.0),
                  Container(
                    width: 20.0,
                    height: 1.0,
                    color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                  ),
                  const SizedBox(width: 16.0),
                  Expanded(
                    child: _buildDateSelector(
                      title: AppLocalizations.of(context).dateRangeXEndDate,
                      date: selectedEnd,
                      isSelected: !isSelectingStart,
                      onTap: () {
                        setState(() {
                          isSelectingStart = false;
                        });
                        HapticFeedback.selectionClick();
                      },
                    ),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 16.0),
            
            // Calendar
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20.0),
                child: _CustomCalendar(
                  selectedStart: selectedStart,
                  selectedEnd: selectedEnd,
                  onDateSelected: (date) {
                    setState(() {
                      if (isSelectingStart) {
                        selectedStart = date;
                        if (selectedEnd.isBefore(selectedStart)) {
                          selectedEnd = selectedStart;
                        }
                      } else {
                        if (date.isBefore(selectedStart)) {
                          selectedStart = date;
                        }
                        selectedEnd = date;
                      }
                    });
                    HapticFeedback.selectionClick();
                  },
                ),
              ),
            ),
            
            // Action buttons
            Padding(
              padding: const EdgeInsets.fromLTRB(20.0, 20.0, 20.0, 32.0),
              child: Row(
                children: [
                  Expanded(
                    child: FFButtonWidget(
                      onPressed: () {
                        HapticFeedback.lightImpact();
                        Navigator.of(context).pop();
                      },
                      text: AppLocalizations.of(context).commonCancel,
                      options: FFButtonOptions(
                        height: 48.0,
                        padding: const EdgeInsetsDirectional.fromSTEB(0, 0, 0, 0),
                        iconPadding: const EdgeInsetsDirectional.fromSTEB(0, 0, 0, 0),
                        color: FlutterFlowTheme.of(context).primaryBackground,
                        textStyle: FlutterFlowTheme.of(context).titleMedium.override(
                              color: FlutterFlowTheme.of(context).secondaryText,
                              fontSize: 16.0,
                              fontWeight: FontWeight.w500,
                            ),
                        elevation: 0.0,
                        borderSide: BorderSide(
                          color: FlutterFlowTheme.of(context).alternate,
                          width: 1.0,
                        ),
                        borderRadius: BorderRadius.circular(12.0),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16.0),
                  Expanded(
                    child: FFButtonWidget(
                      onPressed: () {
                        HapticFeedback.lightImpact();
                        Navigator.of(context).pop(
                          DateTimeRange(start: selectedStart, end: selectedEnd),
                        );
                      },
                      text: AppLocalizations.of(context).dateRangeXApply,
                      options: FFButtonOptions(
                        height: 48.0,
                        padding: const EdgeInsetsDirectional.fromSTEB(0, 0, 0, 0),
                        iconPadding: const EdgeInsetsDirectional.fromSTEB(0, 0, 0, 0),
                        color: FlutterFlowTheme.of(context).primary,
                        textStyle: FlutterFlowTheme.of(context).titleMedium.override(
                              color: Colors.white,
                              fontSize: 16.0,
                              fontWeight: FontWeight.w600,
                            ),
                        elevation: 2.0,
                        borderSide: const BorderSide(
                          color: Colors.transparent,
                          width: 1.0,
                        ),
                        borderRadius: BorderRadius.circular(12.0),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDateSelector({
    required String title,
    required DateTime date,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16.0),
        decoration: BoxDecoration(
          color: isSelected
              ? FlutterFlowTheme.of(context).primary.withValues(alpha: 0.1)
              : FlutterFlowTheme.of(context).primaryBackground,
          borderRadius: BorderRadius.circular(12.0),
          border: Border.all(
            color: isSelected
                ? FlutterFlowTheme.of(context).primary
                : FlutterFlowTheme.of(context).alternate.withValues(alpha: 0.3),
            width: isSelected ? 2.0 : 1.0,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: FlutterFlowTheme.of(context).bodySmall.override(
                    color: isSelected
                        ? FlutterFlowTheme.of(context).primary
                        : FlutterFlowTheme.of(context).secondaryText,
                    fontSize: 12.0,
                    fontWeight: FontWeight.w500,
                  ),
            ),
            const SizedBox(height: 4.0),
            Text(
              dateTimeFormat('MMM d', date),
              style: FlutterFlowTheme.of(context).titleMedium.override(
                    color: isSelected
                        ? FlutterFlowTheme.of(context).primary
                        : FlutterFlowTheme.of(context).primaryText,
                    fontSize: 16.0,
                    fontWeight: FontWeight.w600,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CustomCalendar extends StatefulWidget {
  final DateTime selectedStart;
  final DateTime selectedEnd;
  final Function(DateTime) onDateSelected;

  const _CustomCalendar({
    required this.selectedStart,
    required this.selectedEnd,
    required this.onDateSelected,
  });

  @override
  State<_CustomCalendar> createState() => _CustomCalendarState();
}

class _CustomCalendarState extends State<_CustomCalendar> {
  late DateTime currentMonth;

  @override
  void initState() {
    super.initState();
    currentMonth = DateTime(widget.selectedStart.year, widget.selectedStart.month);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).alternate.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        children: [
          // Header with month navigation
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 10.0),
            decoration: BoxDecoration(
              color: FlutterFlowTheme.of(context).primary,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16.0),
                topRight: Radius.circular(16.0),
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                IconButton(
                  onPressed: () {
                    setState(() {
                      currentMonth = DateTime(currentMonth.year, currentMonth.month - 1);
                    });
                  },
                  icon: const Icon(Icons.chevron_left, color: Colors.white),
                ),
                Text(
                  dateTimeFormat('MMMM yyyy', currentMonth),
                  style: FlutterFlowTheme.of(context).titleMedium.override(
                        color: Colors.white,
                        fontSize: 18.0,
                        fontWeight: FontWeight.w600,
                      ),
                ),
                IconButton(
                  onPressed: () {
                    setState(() {
                      currentMonth = DateTime(currentMonth.year, currentMonth.month + 1);
                    });
                  },
                  icon: const Icon(Icons.chevron_right, color: Colors.white),
                ),
              ],
            ),
          ),
          
          // Days of week header
          Container(
            padding: const EdgeInsets.symmetric(vertical: 12.0),
            child: Row(
              children: [
                AppLocalizations.of(context).dateRangeXWeekdaySun,
                AppLocalizations.of(context).dateRangeXWeekdayMon,
                AppLocalizations.of(context).dateRangeXWeekdayTue,
                AppLocalizations.of(context).dateRangeXWeekdayWed,
                AppLocalizations.of(context).dateRangeXWeekdayThu,
                AppLocalizations.of(context).dateRangeXWeekdayFri,
                AppLocalizations.of(context).dateRangeXWeekdaySat,
              ]
                  .map((day) => Expanded(
                        child: Center(
                          child: Text(
                            day,
                            style: FlutterFlowTheme.of(context).bodySmall.override(
                                  color: FlutterFlowTheme.of(context).secondaryText,
                                  fontSize: 12.0,
                                  fontWeight: FontWeight.w500,
                                ),
                          ),
                        ),
                      ))
                  .toList(),
            ),
          ),
          
          // Calendar grid
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8.0),
              child: _buildCalendarGrid(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCalendarGrid() {
    final firstDayOfMonth = DateTime(currentMonth.year, currentMonth.month, 1);
    final lastDayOfMonth = DateTime(currentMonth.year, currentMonth.month + 1, 0);
    final firstDayOfWeek = firstDayOfMonth.weekday % 7;
    final daysInMonth = lastDayOfMonth.day;

    final List<Widget> dayWidgets = [];

    // Add empty cells for days before the first day of the month
    for (int i = 0; i < firstDayOfWeek; i++) {
      dayWidgets.add(Container());
    }

    // Add day cells
    for (int day = 1; day <= daysInMonth; day++) {
      final date = DateTime(currentMonth.year, currentMonth.month, day);
      dayWidgets.add(_buildDayCell(date));
    }

    return GridView.count(
      crossAxisCount: 7,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: dayWidgets,
    );
  }

  Widget _buildDayCell(DateTime date) {
    final normalizedDate = DateTime(date.year, date.month, date.day);
    final normalizedStart = DateTime(widget.selectedStart.year, widget.selectedStart.month, widget.selectedStart.day);
    final normalizedEnd = DateTime(widget.selectedEnd.year, widget.selectedEnd.month, widget.selectedEnd.day);
    final today = DateTime.now();
    final normalizedToday = DateTime(today.year, today.month, today.day);

    final isStart = normalizedDate == normalizedStart;
    final isEnd = normalizedDate == normalizedEnd;
    final isInRange = normalizedDate.isAfter(normalizedStart) && normalizedDate.isBefore(normalizedEnd);
    final isToday = normalizedDate == normalizedToday;
    final isSelected = isStart || isEnd;

    Color? backgroundColor;
    Color? textColor;
    Border? border;

    if (isSelected) {
      backgroundColor = FlutterFlowTheme.of(context).primary;
      textColor = Colors.white;
    } else if (isInRange) {
      backgroundColor = FlutterFlowTheme.of(context).primary.withValues(alpha: 0.15);
      textColor = FlutterFlowTheme.of(context).primary;
    } else if (isToday) {
      border = Border.all(
        color: FlutterFlowTheme.of(context).primary,
        width: 2.0,
      );
      textColor = FlutterFlowTheme.of(context).primary;
    } else {
      textColor = FlutterFlowTheme.of(context).primaryText;
    }

    return GestureDetector(
      onTap: () => widget.onDateSelected(date),
      child: Container(
        margin: const EdgeInsets.all(2.0),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(8.0),
          border: border,
        ),
        child: Center(
          child: Text(
            date.day.toString(),
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  color: textColor,
                  fontSize: 14.0,
                  fontWeight: isSelected || isToday ? FontWeight.w600 : FontWeight.w500,
                ),
          ),
        ),
      ),
    );
  }
}