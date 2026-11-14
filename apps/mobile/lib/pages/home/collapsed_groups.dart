// Which home groups stay folded across launches.

import 'project_groups.dart';

/// Key of the pinned group, which leads every grouping (see `getGroupedSessions`).
const String kPinnedGroupKey = 'Pinned';

/// How many folded groups are remembered. Past it the oldest fold is
/// forgotten, so the ids of long-gone projects don't pile up in preferences.
const int kMaxRememberedCollapsedGroups = 200;

/// The key a folded [group] is remembered under while grouped by [groupBy], or
/// null when the fold only lasts until the app closes: a day of the Time
/// grouping ("Today", "Monday") is a different day on the next launch. Pinned
/// is the same group in every grouping, so it's remembered once.
String? collapsedGroupMemoryKey(String groupBy, SessionGroup group) {
  if (group.key == kPinnedGroupKey) return 'pinned';
  switch (groupBy) {
    case 'Project':
      return 'project:${group.key}';
    case 'Status':
      return 'status:${group.key}';
    default:
      return null;
  }
}

/// [remembered] with [key] folded or unfolded. A fold moves to the end, so the
/// cap drops the folds made longest ago.
List<String> withCollapsedGroup(List<String> remembered, String key, bool collapsed) {
  final next = remembered.where((k) => k != key).toList();
  if (collapsed) next.add(key);
  if (next.length <= kMaxRememberedCollapsedGroups) return next;
  return next.sublist(next.length - kMaxRememberedCollapsedGroups);
}
