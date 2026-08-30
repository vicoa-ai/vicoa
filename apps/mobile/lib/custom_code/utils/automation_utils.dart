// Field accessors + schedule draft model for automations. Dart port of the
// web dashboard's `automation/lib/frequency.ts`; the server is the source of
// truth for next_run_at — the app only edits the stored schedule shape and
// renders summaries.

import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

// --- field accessors ---------------------------------------------------------

String automationId(dynamic a) => (a is Map ? a['id'] : null)?.toString() ?? '';

String automationTitle(dynamic a) =>
    (a is Map ? a['title'] : null)?.toString() ?? '';

String automationPrompt(dynamic a) =>
    (a is Map ? a['prompt'] : null)?.toString() ?? '';

String automationMachineId(dynamic a) =>
    (a is Map ? a['machine_id'] : null)?.toString() ?? '';

String automationDirectory(dynamic a) =>
    (a is Map ? a['directory'] : null)?.toString() ?? '';

/// `{'mode': 'none'|'new'|'existing', 'path'?: ...}` or null.
Map<String, dynamic>? automationWorktree(dynamic a) {
  final w = a is Map ? a['worktree'] : null;
  return w is Map ? Map<String, dynamic>.from(w) : null;
}

Map<String, dynamic> automationSessionConfig(dynamic a) {
  final c = a is Map ? a['session_config'] : null;
  return c is Map ? Map<String, dynamic>.from(c) : <String, dynamic>{};
}

/// 'once' | 'recurring'
String automationScheduleKind(dynamic a) =>
    (a is Map ? a['schedule_kind'] : null)?.toString() ?? 'recurring';

Map<String, dynamic>? automationFrequency(dynamic a) {
  final f = a is Map ? a['frequency'] : null;
  return f is Map ? Map<String, dynamic>.from(f) : null;
}

String automationTimezone(dynamic a) =>
    (a is Map ? a['timezone'] : null)?.toString() ?? 'UTC';

bool automationEnabled(dynamic a) => a is Map && a['enabled'] == true;

DateTime? _parseDate(dynamic v) =>
    v is String && v.isNotEmpty ? DateTime.tryParse(v)?.toLocal() : null;

DateTime? automationNextRunAt(dynamic a) =>
    _parseDate(a is Map ? a['next_run_at'] : null);

DateTime? automationLastRunAt(dynamic a) =>
    _parseDate(a is Map ? a['last_run_at'] : null);

/// 'fired' | 'missed_offline' | 'failed' | 'skipped' | null
String? automationLastRunStatus(dynamic a) {
  final s = a is Map ? a['last_run_status'] : null;
  return s is String && s.isNotEmpty ? s : null;
}

// Run-history rows (GET /automations/{id}/runs).
String automationRunStatus(dynamic r) =>
    (r is Map ? r['status'] : null)?.toString() ?? 'fired';

DateTime? automationRunFiredAt(dynamic r) =>
    _parseDate(r is Map ? r['fired_at'] : null);

String? automationRunDetail(dynamic r) {
  final d = r is Map ? r['detail'] : null;
  return d is String && d.isNotEmpty ? d : null;
}

String? automationRunInstanceId(dynamic r) {
  final id = r is Map ? r['agent_instance_id'] : null;
  return id?.toString();
}

// --- schedule draft ----------------------------------------------------------

/// Repeat modes offered by the editor, in display order. `once` maps to
/// schedule_kind 'once'; everything else is 'recurring' with a frequency.
const List<String> kAutomationRepeatModes = [
  'once',
  'hourly',
  'daily',
  'weekdays',
  'weekly',
  'custom',
];

/// Units for the custom repeat editor, in display order.
const List<String> kAutomationCustomUnits = [
  'minutely',
  'hourly',
  'daily',
  'weekly',
  'monthly',
];

/// Floor on "every N minutes" — each fire spawns a full agent session, so guard
/// against runaway schedules. Mirrors the web + backend minimum.
const int kMinMinutelyInterval = 5;

/// Custom units that are sub-daily (interval-based) and can carry a daily window.
bool isSubDailyUnit(String unit) => unit == 'minutely' || unit == 'hourly';

/// Mutable editor state for an automation's schedule. Weekday convention is
/// 0=Sunday … 6=Saturday (matches the wire format / JS getDay()).
class AutomationScheduleDraft {
  AutomationScheduleDraft({
    this.repeat = 'daily',
    this.runAt,
    this.timeHour = 9,
    this.timeMinute = 0,
    this.minuteOfHour = 0,
    Set<int>? weekdays,
    this.customUnit = 'daily',
    this.interval = 1,
    Set<int>? monthdays,
    this.windowEnabled = false,
    this.windowStartHour = 9,
    this.windowStartMinute = 0,
    this.windowEndHour = 17,
    this.windowEndMinute = 0,
    String? timezone,
  })  : weekdays = weekdays ?? {1},
        monthdays = monthdays ?? {1},
        timezone = timezone ?? deviceIanaTimezone();

  String repeat;

  /// One-time fire instant (local). Null until the user picks a date.
  DateTime? runAt;

  /// Time-of-day for daily/weekdays/weekly + custom daily/weekly/monthly.
  int timeHour;
  int timeMinute;

  /// Minute past the hour for hourly + custom hourly.
  int minuteOfHour;

  Set<int> weekdays;
  String customUnit;
  int interval;
  Set<int> monthdays;

  /// Optional daily window for sub-daily custom units (minutely/hourly): fire
  /// only within [windowStart, windowEnd] local time, realigned to the start
  /// each day. Overnight spans (end <= start) are not supported.
  bool windowEnabled;
  int windowStartHour;
  int windowStartMinute;
  int windowEndHour;
  int windowEndMinute;

  String timezone;

  String get _hhmm =>
      '${timeHour.toString().padLeft(2, '0')}:${timeMinute.toString().padLeft(2, '0')}';

  static String _fmt(int h, int m) =>
      '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}';

  int get _windowStartMinutes => windowStartHour * 60 + windowStartMinute;
  int get _windowEndMinutes => windowEndHour * 60 + windowEndMinute;

  /// Whether the current window is a usable forward span.
  bool get windowValid => _windowEndMinutes > _windowStartMinutes;

  /// The wire `window` object, or null when disabled/degenerate (→ all-day).
  Map<String, dynamic>? _windowJson() => (windowEnabled && windowValid)
      ? {
          'start': _fmt(windowStartHour, windowStartMinute),
          'end': _fmt(windowEndHour, windowEndMinute),
        }
      : null;

  bool get isComplete {
    if (repeat == 'once') return runAt != null;
    if (repeat == 'weekly') return weekdays.isNotEmpty;
    if (repeat == 'custom') {
      if (customUnit == 'weekly') return weekdays.isNotEmpty;
      if (customUnit == 'monthly') return monthdays.isNotEmpty;
      // A window is optional, but an enabled one must be a valid span.
      if (isSubDailyUnit(customUnit) && windowEnabled && !windowValid) {
        return false;
      }
    }
    return true;
  }

  /// The wire `frequency` object, or null for one-time schedules.
  Map<String, dynamic>? toFrequency() {
    final sortedWeekdays = weekdays.toList()..sort();
    final sortedMonthdays = monthdays.toList()..sort();
    switch (repeat) {
      case 'once':
        return null;
      case 'hourly':
        return {'kind': 'hourly', 'minute': minuteOfHour};
      case 'daily':
        return {'kind': 'daily', 'time': _hhmm};
      case 'weekdays':
        return {'kind': 'weekdays', 'time': _hhmm};
      case 'weekly':
        return {'kind': 'weekly', 'weekdays': sortedWeekdays, 'time': _hhmm};
      case 'custom':
        switch (customUnit) {
          case 'minutely':
            return {
              'kind': 'custom',
              'unit': 'minutely',
              'interval':
                  interval < kMinMinutelyInterval ? kMinMinutelyInterval : interval,
              'window': _windowJson(),
            };
          case 'hourly':
            return {
              'kind': 'custom',
              'unit': 'hourly',
              'interval': interval,
              'minute': minuteOfHour,
              'window': _windowJson(),
            };
          case 'weekly':
            return {
              'kind': 'custom',
              'unit': 'weekly',
              'interval': interval,
              'weekdays': sortedWeekdays,
              'time': _hhmm,
            };
          case 'monthly':
            return {
              'kind': 'custom',
              'unit': 'monthly',
              'interval': interval,
              'monthdays': sortedMonthdays,
              'time': _hhmm,
            };
          default:
            return {
              'kind': 'custom',
              'unit': 'daily',
              'interval': interval,
              'time': _hhmm,
            };
        }
      default:
        return {'kind': 'daily', 'time': _hhmm};
    }
  }

  /// The schedule fields of a create/update request:
  /// `{schedule_kind, run_at?, frequency?, timezone}`.
  Map<String, dynamic> toScheduleApi() {
    if (repeat == 'once') {
      return {
        'schedule_kind': 'once',
        'run_at': runAt?.toUtc().toIso8601String(),
        'frequency': null,
        'timezone': timezone,
      };
    }
    return {
      'schedule_kind': 'recurring',
      'frequency': toFrequency(),
      'timezone': timezone,
    };
  }
}

int _asInt(dynamic v, int fallback) =>
    v is int ? v : (v is num ? v.toInt() : int.tryParse('$v') ?? fallback);

(int, int) _parseHhmm(dynamic v, {int fallbackHour = 9}) {
  if (v is String) {
    final parts = v.split(':');
    if (parts.length == 2) {
      final h = int.tryParse(parts[0]);
      final m = int.tryParse(parts[1]);
      if (h != null && m != null) return (h.clamp(0, 23), m.clamp(0, 59));
    }
  }
  return (fallbackHour, 0);
}

Set<int> _asIntSet(dynamic v, Set<int> fallback) {
  if (v is List) {
    final out = v.map((e) => _asInt(e, -1)).where((e) => e >= 0).toSet();
    if (out.isNotEmpty) return out;
  }
  return fallback;
}

/// Apply a stored `{start,end}` window onto the draft (leaves it disabled when
/// absent). Only meaningful for sub-daily custom units.
void _applyWindow(AutomationScheduleDraft draft, dynamic w) {
  if (w is! Map) return;
  final (sh, sm) = _parseHhmm(w['start'], fallbackHour: 9);
  final (eh, em) = _parseHhmm(w['end'], fallbackHour: 17);
  draft.windowEnabled = true;
  draft.windowStartHour = sh;
  draft.windowStartMinute = sm;
  draft.windowEndHour = eh;
  draft.windowEndMinute = em;
}

/// Rebuild the editor draft from a stored automation.
AutomationScheduleDraft automationToDraft(dynamic a) {
  final draft = AutomationScheduleDraft(timezone: automationTimezone(a));
  if (automationScheduleKind(a) == 'once') {
    draft.repeat = 'once';
    draft.runAt = automationNextRunAt(a);
    return draft;
  }
  final f = automationFrequency(a);
  if (f == null) return draft;
  final kind = f['kind']?.toString();
  switch (kind) {
    case 'hourly':
      draft.repeat = 'hourly';
      draft.minuteOfHour = _asInt(f['minute'], 0).clamp(0, 59);
      break;
    case 'daily':
    case 'weekdays':
      draft.repeat = kind!;
      final (h, m) = _parseHhmm(f['time']);
      draft.timeHour = h;
      draft.timeMinute = m;
      break;
    case 'weekly':
      draft.repeat = 'weekly';
      draft.weekdays = _asIntSet(f['weekdays'], {1});
      final (h, m) = _parseHhmm(f['time']);
      draft.timeHour = h;
      draft.timeMinute = m;
      break;
    case 'custom':
      draft.repeat = 'custom';
      draft.customUnit = kAutomationCustomUnits.contains(f['unit'])
          ? f['unit'] as String
          : 'daily';
      draft.interval = _asInt(f['interval'], 1).clamp(1, 999);
      if (draft.customUnit == 'minutely') {
        draft.interval = draft.interval.clamp(kMinMinutelyInterval, 1439);
        _applyWindow(draft, f['window']);
      } else if (draft.customUnit == 'hourly') {
        draft.minuteOfHour = _asInt(f['minute'], 0).clamp(0, 59);
        _applyWindow(draft, f['window']);
      } else {
        final (h, m) = _parseHhmm(f['time']);
        draft.timeHour = h;
        draft.timeMinute = m;
      }
      if (draft.customUnit == 'weekly') {
        draft.weekdays = _asIntSet(f['weekdays'], {1});
      }
      if (draft.customUnit == 'monthly') {
        draft.monthdays = _asIntSet(f['monthdays'], {1});
      }
      break;
  }
  return draft;
}

// --- device timezone ---------------------------------------------------------

bool _tzInitialized = false;
String? _cachedDeviceZone;

/// Best-effort IANA name for the device's timezone, e.g. `Asia/Shanghai`.
///
/// Dart has no direct API for this (DateTime.timeZoneName is an abbreviation),
/// so match the device's UTC offset at four points across the year against the
/// bundled tz database and take the first zone that agrees at all of them. A
/// functionally equivalent zone (same rules, different name) is fine — the
/// server only uses the name to compute wall-clock fire times. Falls back to
/// 'UTC' if nothing matches.
String deviceIanaTimezone() {
  final cached = _cachedDeviceZone;
  if (cached != null) return cached;
  try {
    if (!_tzInitialized) {
      tzdata.initializeTimeZones();
      _tzInitialized = true;
    }
    final now = DateTime.now();
    // Sample across the year so DST rules (either hemisphere) must line up.
    final samples = [
      now,
      DateTime(now.year, 1, 15, 12),
      DateTime(now.year, 4, 15, 12),
      DateTime(now.year, 7, 15, 12),
      DateTime(now.year, 10, 15, 12),
    ];
    final offsets = [for (final s in samples) s.timeZoneOffset.inMilliseconds];
    final names = tz.timeZoneDatabase.locations.keys.toList()..sort();
    for (final name in names) {
      // Skip alias-style zones so a real region name wins.
      if (!name.contains('/') || name.startsWith('Etc/')) continue;
      final location = tz.getLocation(name);
      var matches = true;
      for (var i = 0; i < samples.length; i++) {
        final utcMs = samples[i].toUtc().millisecondsSinceEpoch;
        if (location.timeZone(utcMs).offset != offsets[i]) {
          matches = false;
          break;
        }
      }
      if (matches) {
        _cachedDeviceZone = name;
        return name;
      }
    }
  } catch (_) {
    // Fall through to UTC.
  }
  _cachedDeviceZone = 'UTC';
  return 'UTC';
}
