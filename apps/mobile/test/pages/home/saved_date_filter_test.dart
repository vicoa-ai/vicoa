// Spec for Home's agent and date filters coming back after a relaunch:
//   - 'Today' and 'Last 7 Days' come back as they were (they count from now);
//   - a 'Custom' range comes back with its days, or as 'All Time' when the
//     days are missing, unreadable or reversed;
//   - both filters survive the preferences JSON round trip, and old prefs
//     without them load 'All' / 'All Time'.
import 'package:flutter/material.dart' show DateTimeRange;
import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/app_state.dart';
import 'package:vicoa/pages/home/saved_date_filter.dart';

void main() {
  group('restoreDateFilter', () {
    test('relative ranges come back as they were', () {
      for (final range in ['All Time', 'Today', 'Last 7 Days']) {
        expect(restoreDateFilter(range, null, null), (range: range, custom: null));
      }
    });

    test('a custom range comes back with its days', () {
      final restored = restoreDateFilter('Custom', '2026-11-01T00:00:00.000', '2026-11-07T00:00:00.000');
      expect(restored.range, 'Custom');
      expect(restored.custom, DateTimeRange(start: DateTime(2026, 11, 1), end: DateTime(2026, 11, 7)));
    });

    test('a custom range without usable days opens on All Time', () {
      expect(restoreDateFilter('Custom', null, '2026-11-07').range, 'All Time');
      expect(restoreDateFilter('Custom', 'not a date', '2026-11-07').range, 'All Time');
      expect(restoreDateFilter('Custom', '2026-11-07', '2026-11-01').range, 'All Time');
    });
  });

  group('UserPreferences home filters', () {
    test('survive the JSON round trip', () {
      final back = UserPreferences.fromJson(UserPreferences(
        homeFilterAgentType: 'Codex',
        homeFilterDateRange: 'Custom',
        homeFilterCustomStart: '2026-11-01T00:00:00.000',
        homeFilterCustomEnd: '2026-11-07T00:00:00.000',
      ).toJson());
      expect(back.homeFilterAgentType, 'Codex');
      expect(back.homeFilterDateRange, 'Custom');
      expect(back.homeFilterCustomStart, '2026-11-01T00:00:00.000');
      expect(back.homeFilterCustomEnd, '2026-11-07T00:00:00.000');
    });

    test('prefs saved before they existed load All and All Time', () {
      final back = UserPreferences.fromJson({'homeFilterGroupBy': 'Project'});
      expect(back.homeFilterAgentType, 'All');
      expect(back.homeFilterDateRange, 'All Time');
      expect(back.homeFilterCustomStart, isNull);
    });
  });
}
