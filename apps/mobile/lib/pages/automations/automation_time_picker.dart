// Wheel-style time/date pickers in the app's standard bottom-sheet chrome
// (handle bar + Close / Title / Confirm header, like the directory picker) —
// replaces the stock Material dialog pickers, which clash with the rest of
// the app's look.

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/keyboard_utils.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';

/// Wheel time-of-day picker. Returns the chosen time, or null on cancel.
Future<TimeOfDay?> showWheelTimePicker({
  required BuildContext context,
  required String title,
  required TimeOfDay initial,
}) async {
  final now = DateTime.now();
  final picked = await _showWheelPickerSheet(
    context: context,
    title: title,
    initial:
        DateTime(now.year, now.month, now.day, initial.hour, initial.minute),
    mode: CupertinoDatePickerMode.time,
  );
  if (picked == null) return null;
  return TimeOfDay(hour: picked.hour, minute: picked.minute);
}

/// Wheel calendar-date picker (time of the returned value is meaningless).
/// Returns the chosen date, or null on cancel.
Future<DateTime?> showWheelDatePicker({
  required BuildContext context,
  required String title,
  required DateTime initial,
  DateTime? minimum,
  DateTime? maximum,
}) {
  return _showWheelPickerSheet(
    context: context,
    title: title,
    initial: initial,
    mode: CupertinoDatePickerMode.date,
    minimum: minimum,
    maximum: maximum,
  );
}

/// Wheel integer picker over [min, max] inclusive, in the same bottom-sheet
/// chrome. Returns the chosen value, or null on cancel. `itemLabel` formats each
/// row (e.g. zero-padded minutes); defaults to the plain number.
Future<int?> showWheelNumberPicker({
  required BuildContext context,
  required String title,
  required int initial,
  required int min,
  required int max,
  String Function(int)? itemLabel,
}) {
  dismissKeyboard();
  return showModalBottomSheet<int>(
    context: context,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _WheelNumberSheet(
      title: title,
      initial: initial.clamp(min, max),
      min: min,
      max: max,
      itemLabel: itemLabel,
    ),
  );
}

Future<DateTime?> _showWheelPickerSheet({
  required BuildContext context,
  required String title,
  required DateTime initial,
  required CupertinoDatePickerMode mode,
  DateTime? minimum,
  DateTime? maximum,
}) {
  // Drop the keyboard so it doesn't sit behind the picker and pop back up when
  // the picker closes.
  dismissKeyboard();
  return showModalBottomSheet<DateTime>(
    context: context,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _WheelPickerSheet(
      title: title,
      initial: initial,
      mode: mode,
      minimum: minimum,
      maximum: maximum,
    ),
  );
}

class _WheelPickerSheet extends StatefulWidget {
  const _WheelPickerSheet({
    required this.title,
    required this.initial,
    required this.mode,
    this.minimum,
    this.maximum,
  });

  final String title;
  final DateTime initial;
  final CupertinoDatePickerMode mode;
  final DateTime? minimum;
  final DateTime? maximum;

  @override
  State<_WheelPickerSheet> createState() => _WheelPickerSheetState();
}

class _WheelPickerSheetState extends State<_WheelPickerSheet> {
  late DateTime _value = widget.initial;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
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
              margin: const EdgeInsets.only(top: 12.0),
              width: 40.0,
              height: 4.0,
              decoration: BoxDecoration(
                color: theme.alternate,
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
            Padding(
              padding:
                  const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
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
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context);
                    },
                  ),
                  Text(
                    widget.title,
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
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
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context, _value);
                    },
                  ),
                ],
              ),
            ),
            SizedBox(
              height: 216.0,
              child: CupertinoTheme(
                data: CupertinoThemeData(
                  brightness: Theme.of(context).brightness,
                  textTheme: CupertinoTextThemeData(
                    dateTimePickerTextStyle: GoogleFonts.sourceSans3(
                      fontSize: 21.0,
                      color: theme.primaryText,
                    ),
                  ),
                ),
                child: CupertinoDatePicker(
                  mode: widget.mode,
                  initialDateTime: widget.initial,
                  minimumDate: widget.minimum,
                  maximumDate: widget.maximum,
                  use24hFormat:
                      MediaQuery.of(context).alwaysUse24HourFormat,
                  onDateTimeChanged: (v) {
                    HapticFeedback.selectionClick();
                    _value = v;
                  },
                ),
              ),
            ),
            const SizedBox(height: 8.0),
          ],
        ),
      ),
    );
  }
}

class _WheelNumberSheet extends StatefulWidget {
  const _WheelNumberSheet({
    required this.title,
    required this.initial,
    required this.min,
    required this.max,
    this.itemLabel,
  });

  final String title;
  final int initial;
  final int min;
  final int max;
  final String Function(int)? itemLabel;

  @override
  State<_WheelNumberSheet> createState() => _WheelNumberSheetState();
}

class _WheelNumberSheetState extends State<_WheelNumberSheet> {
  late int _value = widget.initial;
  late final FixedExtentScrollController _controller =
      FixedExtentScrollController(initialItem: widget.initial - widget.min);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
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
              margin: const EdgeInsets.only(top: 12.0),
              width: 40.0,
              height: 4.0,
              decoration: BoxDecoration(
                color: theme.alternate,
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
            Padding(
              padding:
                  const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
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
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context);
                    },
                  ),
                  Text(
                    widget.title,
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
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
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context, _value);
                    },
                  ),
                ],
              ),
            ),
            SizedBox(
              height: 216.0,
              child: CupertinoPicker.builder(
                itemExtent: 36.0,
                scrollController: _controller,
                childCount: widget.max - widget.min + 1,
                onSelectedItemChanged: (i) {
                  HapticFeedback.selectionClick();
                  _value = widget.min + i;
                },
                itemBuilder: (ctx, i) {
                  final v = widget.min + i;
                  return Center(
                    child: Text(
                      widget.itemLabel?.call(v) ?? '$v',
                      style: GoogleFonts.sourceSans3(
                        fontSize: 21.0,
                        color: theme.primaryText,
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 8.0),
          ],
        ),
      ),
    );
  }
}
