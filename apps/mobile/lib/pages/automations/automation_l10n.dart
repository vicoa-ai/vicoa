// Localized labels + schedule summaries for automations. Kept separate from
// automation_utils.dart so the pure schedule logic stays free of l10n deps
// (mirrors task_l10n.dart).

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '/custom_code/utils/automation_utils.dart' as autils;
import '/l10n/app_localizations.dart';

String automationRepeatLabel(AppLocalizations l10n, String mode) {
  switch (mode) {
    case 'once':
      return l10n.automationsRepeatOnce;
    case 'minutely':
      return l10n.automationsRepeatMinutely;
    case 'hourly':
      return l10n.automationsRepeatHourly;
    case 'daily':
      return l10n.automationsRepeatDaily;
    case 'weekdays':
      return l10n.automationsRepeatWeekdays;
    case 'weekly':
      return l10n.automationsRepeatWeekly;
    case 'monthly':
      return l10n.automationsRepeatMonthly;
    case 'custom':
      return l10n.automationsRepeatCustom;
    default:
      return mode;
  }
}

/// Pluralized unit noun for the custom "Every N …" stepper, e.g. "days" /
/// "week" / "个月". [unit] is a custom-schedule unit ('hourly'/'daily'/…).
String automationEveryUnitLabel(AppLocalizations l10n, String unit, int count) {
  switch (unit) {
    case 'minutely':
      return l10n.automationsEveryUnitMinutes(count);
    case 'hourly':
      return l10n.automationsEveryUnitHours(count);
    case 'weekly':
      return l10n.automationsEveryUnitWeeks(count);
    case 'monthly':
      return l10n.automationsEveryUnitMonths(count);
    case 'daily':
    default:
      return l10n.automationsEveryUnitDays(count);
  }
}

String automationRunStatusLabel(AppLocalizations l10n, String status) {
  switch (status) {
    case 'fired':
      return l10n.automationsRunStatusFired;
    case 'missed_offline':
      return l10n.automationsRunStatusMissedOffline;
    case 'failed':
      return l10n.automationsRunStatusFailed;
    case 'skipped':
      return l10n.automationsRunStatusSkipped;
    default:
      return status;
  }
}

/// Short weekday label for wire index 0=Sunday … 6=Saturday, in the current
/// locale (e.g. "Mon" / "周一"). 2023-01-01 was a Sunday.
String automationWeekdayLabel(BuildContext context, int weekday) {
  final locale = Localizations.localeOf(context).toString();
  return DateFormat.E(locale).format(DateTime(2023, 1, 1 + weekday));
}

String _formatTime(BuildContext context, int hour, int minute) =>
    TimeOfDay(hour: hour, minute: minute).format(context);

String _formatWhen(BuildContext context, DateTime dt) {
  final locale = Localizations.localeOf(context).toString();
  return '${DateFormat.MMMd(locale).format(dt)}, ${DateFormat.jm(locale).format(dt)}';
}

String _pad2(int v) => v.toString().padLeft(2, '0');

/// Human summary of a frequency object, e.g. "Daily at 9:00 AM",
/// "Every 2 weeks on Mon, Wed at 9:00 AM".
String summarizeAutomationFrequency(
    BuildContext context, Map<String, dynamic>? frequency) {
  final l10n = AppLocalizations.of(context);
  if (frequency == null) return l10n.automationsSummaryRecurring;

  String timeOf(dynamic v) {
    if (v is String) {
      final parts = v.split(':');
      if (parts.length == 2) {
        final h = int.tryParse(parts[0]);
        final m = int.tryParse(parts[1]);
        if (h != null && m != null) return _formatTime(context, h, m);
      }
    }
    return _formatTime(context, 9, 0);
  }

  String daysOf(dynamic v) {
    if (v is! List || v.isEmpty) return '';
    final days = v
        .map((e) => e is int ? e : int.tryParse('$e'))
        .whereType<int>()
        .toList()
      ..sort();
    return days.map((d) => automationWeekdayLabel(context, d)).join(', ');
  }

  final minute = frequency['minute'];
  final minuteLabel = _pad2(minute is int ? minute : 0);

  // Append " · 9:00 AM–12:00 PM" to a sub-daily summary when a window is set.
  String withWindow(String base) {
    final w = frequency['window'];
    if (w is Map && w['start'] is String && w['end'] is String) {
      return '$base · ${timeOf(w['start'])}–${timeOf(w['end'])}';
    }
    return base;
  }

  switch (frequency['kind']) {
    case 'hourly':
      return l10n.automationsSummaryHourly(minuteLabel);
    case 'daily':
      return l10n.automationsSummaryDaily(timeOf(frequency['time']));
    case 'weekdays':
      return l10n.automationsSummaryWeekdays(timeOf(frequency['time']));
    case 'weekly':
      return l10n.automationsSummaryWeekly(
          daysOf(frequency['weekdays']), timeOf(frequency['time']));
    case 'custom':
      final n = frequency['interval'] is int ? frequency['interval'] as int : 1;
      final hasWindow = frequency['window'] is Map;
      switch (frequency['unit']) {
        case 'minutely':
          return withWindow(l10n.automationsSummaryEveryMinutes('$n'));
        case 'hourly':
          // A window supersedes the ":MM" phase (fires align to the window
          // start), so drop it and append the span instead.
          if (hasWindow) {
            return withWindow(n == 1
                ? l10n.automationsSummaryHourlyPlain
                : l10n.automationsSummaryEveryHoursPlain('$n'));
          }
          return n == 1
              ? l10n.automationsSummaryHourly(minuteLabel)
              : l10n.automationsSummaryEveryHours('$n', minuteLabel);
        case 'daily':
          return n == 1
              ? l10n.automationsSummaryDaily(timeOf(frequency['time']))
              : l10n.automationsSummaryEveryDays(
                  '$n', timeOf(frequency['time']));
        case 'weekly':
          return l10n.automationsSummaryEveryWeeks('$n',
              daysOf(frequency['weekdays']), timeOf(frequency['time']));
        case 'monthly':
          final days = frequency['monthdays'];
          final dayList = days is List ? days.join(', ') : '1';
          return l10n.automationsSummaryEveryMonths(
              '$n', dayList, timeOf(frequency['time']));
      }
      return l10n.automationsRepeatCustom;
    default:
      return l10n.automationsSummaryRecurring;
  }
}

/// One-line schedule summary for a stored automation (list row subtitle).
String summarizeAutomationSchedule(BuildContext context, dynamic automation) {
  final l10n = AppLocalizations.of(context);
  if (autils.automationScheduleKind(automation) == 'once') {
    final at = autils.automationNextRunAt(automation);
    return at == null
        ? l10n.automationsRepeatOnce
        : l10n.automationsScheduleOnceAt(_formatWhen(context, at));
  }
  return summarizeAutomationFrequency(
      context, autils.automationFrequency(automation));
}

/// "Next · Aug 10, 9:00 AM" line for enabled automations with a future run.
String? nextRunLabel(BuildContext context, dynamic automation) {
  if (!autils.automationEnabled(automation)) return null;
  final next = autils.automationNextRunAt(automation);
  if (next == null) return null;
  return AppLocalizations.of(context)
      .automationsNextRun(_formatWhen(context, next));
}
