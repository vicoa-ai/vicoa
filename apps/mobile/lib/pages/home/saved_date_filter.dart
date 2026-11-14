// The Home date filter as saved in preferences, and back.

import 'package:flutter/material.dart' show DateTimeRange;

/// The date filter to open Home with, from what was saved. 'Today' and
/// 'Last 7 Days' count from now, so they come back as they were. A 'Custom'
/// filter needs both of its days; without them (or with days that don't parse)
/// Home opens on 'All Time' rather than filtering on nothing.
({String range, DateTimeRange? custom}) restoreDateFilter(String saved, String? start, String? end) {
  if (saved != 'Custom') return (range: saved, custom: null);
  final from = start == null ? null : DateTime.tryParse(start);
  final to = end == null ? null : DateTime.tryParse(end);
  if (from == null || to == null || to.isBefore(from)) return (range: 'All Time', custom: null);
  return (range: 'Custom', custom: DateTimeRange(start: from, end: to));
}
