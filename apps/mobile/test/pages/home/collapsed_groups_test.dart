// Spec for which home groups stay folded across launches:
//   - Project, Status and Pinned folds are remembered; a Time grouping's day
//     ("Today", "Monday") is not, as it names a different day next launch;
//   - Pinned is remembered once for every grouping;
//   - the remembered list is capped, dropping the oldest fold first;
//   - the list survives the preferences JSON round trip, and old prefs
//     without it load with every group open.
import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/app_state.dart';
import 'package:vicoa/pages/home/collapsed_groups.dart';
import 'package:vicoa/pages/home/project_groups.dart';

SessionGroup _group(String key) => SessionGroup(key: key, label: key, sessions: const []);

void main() {
  group('collapsedGroupMemoryKey', () {
    test('remembers project and status groups under their grouping', () {
      expect(collapsedGroupMemoryKey('Project', _group('p-1')), 'project:p-1');
      expect(collapsedGroupMemoryKey('Status', _group('Done')), 'status:Done');
    });

    test('does not remember a day of the Time grouping', () {
      expect(collapsedGroupMemoryKey('Time', _group('Today')), isNull);
    });

    test('remembers Pinned once for every grouping', () {
      for (final groupBy in ['Project', 'Status', 'Time']) {
        expect(collapsedGroupMemoryKey(groupBy, _group(kPinnedGroupKey)), 'pinned');
      }
    });
  });

  group('withCollapsedGroup', () {
    test('folds and unfolds a group', () {
      final folded = withCollapsedGroup(const [], 'project:a', true);
      expect(folded, ['project:a']);
      expect(withCollapsedGroup(folded, 'project:a', false), isEmpty);
    });

    test('folding again does not duplicate and moves it last', () {
      expect(withCollapsedGroup(['project:a', 'project:b'], 'project:a', true), ['project:b', 'project:a']);
    });

    test('drops the oldest folds past the cap', () {
      final full = [for (var i = 0; i < kMaxRememberedCollapsedGroups; i++) 'project:$i'];
      final next = withCollapsedGroup(full, 'project:new', true);
      expect(next.length, kMaxRememberedCollapsedGroups);
      expect(next.first, 'project:1');
      expect(next.last, 'project:new');
    });
  });

  group('UserPreferences.homeCollapsedGroups', () {
    test('survives the JSON round trip', () {
      final prefs = UserPreferences(homeCollapsedGroups: ['project:a', 'pinned']);
      final back = UserPreferences.fromJson(prefs.toJson());
      expect(back.homeCollapsedGroups, ['project:a', 'pinned']);
    });

    test('prefs saved before it existed load with every group open', () {
      final back = UserPreferences.fromJson({'homeFilterGroupBy': 'Project'});
      expect(back.homeCollapsedGroups, isEmpty);
      expect(back.toJson().containsKey('homeCollapsedGroups'), isFalse);
    });
  });
}
