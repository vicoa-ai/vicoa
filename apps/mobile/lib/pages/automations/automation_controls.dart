// Small reusable controls for the Automations feature: the frequency editor's
// weekday chips / monthday grid / number stepper, and the labeled field rows
// used by the editor's section cards.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import 'automation_l10n.dart';
import 'automation_time_picker.dart';

/// Sun–Sat toggle chips. Weekday convention: 0=Sunday … 6=Saturday.
class WeekdayChips extends StatelessWidget {
  const WeekdayChips({
    super.key,
    required this.selected,
    required this.onToggle,
  });

  final Set<int> selected;
  final ValueChanged<int> onToggle;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Row(
      children: [
        for (var d = 0; d < 7; d++) ...[
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {
                HapticFeedback.selectionClick();
                onToggle(d);
              },
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                height: 34.0,
                decoration: BoxDecoration(
                  color: selected.contains(d)
                      ? theme.primary
                      : theme.secondaryBackground,
                  borderRadius: BorderRadius.circular(10.0),
                  border: Border.all(
                    color:
                        selected.contains(d) ? theme.primary : theme.alternate,
                  ),
                ),
                child: Center(
                  child: Text(
                    automationWeekdayLabel(context, d),
                    maxLines: 1,
                    style: theme.bodySmall.override(
                      font: GoogleFonts.sourceSans3(),
                      fontSize: 12.0,
                      letterSpacing: 0.0,
                      fontWeight: FontWeight.w600,
                      color: selected.contains(d)
                          ? Colors.white
                          : theme.secondaryText,
                    ),
                  ),
                ),
              ),
            ),
          ),
          if (d < 6) const SizedBox(width: 6.0),
        ],
      ],
    );
  }
}

/// 1–31 toggle grid for custom monthly schedules.
class MonthdayGrid extends StatelessWidget {
  const MonthdayGrid({
    super.key,
    required this.selected,
    required this.onToggle,
  });

  final Set<int> selected;
  final ValueChanged<int> onToggle;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return GridView.count(
      crossAxisCount: 7,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 6.0,
      crossAxisSpacing: 6.0,
      children: [
        for (var day = 1; day <= 31; day++)
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              HapticFeedback.selectionClick();
              onToggle(day);
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              decoration: BoxDecoration(
                color: selected.contains(day)
                    ? theme.primary
                    : theme.secondaryBackground,
                borderRadius: BorderRadius.circular(10.0),
                border: Border.all(
                  color:
                      selected.contains(day) ? theme.primary : theme.alternate,
                ),
              ),
              child: Center(
                child: Text(
                  '$day',
                  style: theme.bodySmall.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 12.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w600,
                    color: selected.contains(day)
                        ? Colors.white
                        : theme.secondaryText,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// A "− value +" stepper for intervals and minutes.
class NumberStepper extends StatelessWidget {
  const NumberStepper({
    super.key,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
    this.displayValue,
    this.pickerTitle,
    this.wheelItemLabel,
  });

  final int value;
  final int min;
  final int max;
  final ValueChanged<int> onChanged;

  /// Optional formatted value (e.g. ":05"); defaults to the raw number.
  final String? displayValue;

  /// When set, tapping the number opens a wheel picker with this title — fast
  /// entry for large ranges the −/+ buttons would take many taps to reach.
  final String? pickerTitle;

  /// Optional formatter for each wheel row (e.g. zero-padded minutes).
  final String Function(int)? wheelItemLabel;

  Widget _button(BuildContext context, IconData icon, bool enabled,
      VoidCallback onTap) {
    final theme = FlutterFlowTheme.of(context);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: enabled
          ? () {
              HapticFeedback.selectionClick();
              onTap();
            }
          : null,
      child: Container(
        width: 30.0,
        height: 30.0,
        decoration: BoxDecoration(
          color: theme.secondaryBackground,
          borderRadius: BorderRadius.circular(8.0),
          border: Border.all(color: theme.alternate),
        ),
        child: Icon(
          icon,
          size: 16.0,
          color: enabled ? theme.primaryText : theme.alternate,
        ),
      ),
    );
  }

  Future<void> _openWheel(BuildContext context) async {
    final picked = await showWheelNumberPicker(
      context: context,
      title: pickerTitle!,
      initial: value,
      min: min,
      max: max,
      itemLabel: wheelItemLabel,
    );
    if (picked != null && picked != value) onChanged(picked);
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    // The number reads as a tappable field (same chrome as the buttons) when a
    // wheel picker is wired up; otherwise it's plain centered text.
    Widget number = Container(
      height: 30.0,
      constraints: const BoxConstraints(minWidth: 48.0),
      alignment: Alignment.center,
      padding: pickerTitle == null
          ? null
          : const EdgeInsets.symmetric(horizontal: 10.0),
      decoration: pickerTitle == null
          ? null
          : BoxDecoration(
              color: theme.secondaryBackground,
              borderRadius: BorderRadius.circular(8.0),
              border: Border.all(color: theme.alternate),
            ),
      child: Text(
        displayValue ?? '$value',
        style: theme.bodyMedium.override(
          font: GoogleFonts.sourceSans3(),
          letterSpacing: 0.0,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
    if (pickerTitle != null) {
      number = GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          HapticFeedback.selectionClick();
          _openWheel(context);
        },
        child: number,
      );
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _button(context, Icons.remove_rounded, value > min,
            () => onChanged(value - 1)),
        const SizedBox(width: 6.0),
        number,
        const SizedBox(width: 6.0),
        _button(context, Icons.add_rounded, value < max,
            () => onChanged(value + 1)),
      ],
    );
  }
}

/// A labeled row inside an editor section card: label left, value/control
/// right, optional chevron + tap. Rows are separated by hairline dividers.
class AutomationFieldRow extends StatelessWidget {
  const AutomationFieldRow({
    super.key,
    required this.label,
    this.value,
    this.valueWidget,
    this.onTap,
    this.showChevron = true,
    this.valueColor,
  });

  final String label;
  final String? value;
  final Widget? valueWidget;
  final VoidCallback? onTap;
  final bool showChevron;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final row = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 12.0),
      child: Row(
        children: [
          Text(
            label,
            style: theme.bodyMedium.override(
              font: GoogleFonts.sourceSans3(),
              letterSpacing: 0.0,
              color: theme.primaryText,
            ),
          ),
          const SizedBox(width: 12.0),
          Expanded(
            child: valueWidget ??
                Text(
                  value ?? '',
                  textAlign: TextAlign.end,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    letterSpacing: 0.0,
                    color: valueColor ?? theme.secondaryText,
                  ),
                ),
          ),
          if (onTap != null && showChevron) ...[
            const SizedBox(width: 4.0),
            Icon(Icons.chevron_right_rounded,
                size: 18.0, color: theme.secondaryText),
          ],
        ],
      ),
    );
    if (onTap == null) return row;
    return InkWell(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap!();
      },
      child: row,
    );
  }
}

/// Section card wrapper: a muted section label above a primaryBackground card
/// with hairline dividers between rows.
class AutomationSectionCard extends StatelessWidget {
  const AutomationSectionCard({
    super.key,
    required this.label,
    required this.children,
  });

  final String label;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 12.0),
          child: Text(
            label,
            // Matches the New Session page's section-label style.
            style: theme.labelMedium.override(
              font: GoogleFonts.sourceSans3(),
              fontSize: 15.0,
              letterSpacing: 0.0,
              fontWeight: FontWeight.w500,
              color: theme.secondaryText,
            ),
          ),
        ),
        Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: theme.primaryBackground,
            borderRadius: BorderRadius.circular(14.0),
            border: Border.all(color: theme.alternate),
          ),
          child: Column(
            children: [
              for (var i = 0; i < children.length; i++) ...[
                if (i > 0)
                  Divider(
                    height: 1.0,
                    thickness: 1.0,
                    indent: 14.0,
                    color: theme.alternate.withValues(alpha: 0.6),
                  ),
                children[i],
              ],
            ],
          ),
        ),
      ],
    );
  }
}
