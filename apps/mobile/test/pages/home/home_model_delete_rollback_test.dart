// Spec for rolling back the home list's optimistic delete when the API fails:
//   - restoreInstance puts the session back where removeInstance took it from,
//     locally (a refetch can't bring it back while offline) and in the cache;
//   - a refresh no longer filters the restored id out;
//   - restoring a session a refresh already brought back doesn't duplicate it.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:vicoa/app_state.dart';
import 'package:vicoa/pages/home/home_model.dart';

List<String?> _ids(List<dynamic> instances) =>
    instances.map((i) => (i as Map)['id']?.toString()).toList();

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FFAppState().prefs = await SharedPreferences.getInstance();
  });

  test('a failed delete puts the session back where it was', () {
    final model = HomeModel();
    final b = <String, dynamic>{'id': 'b'};
    model.agentInstances = <dynamic>[{'id': 'a'}, b, {'id': 'c'}];

    final at = model.removeInstance('b');
    expect(at, 1);
    expect(_ids(model.agentInstances), ['a', 'c']);

    model.restoreInstance(b, index: at);
    expect(_ids(model.agentInstances), ['a', 'b', 'c']);
    expect(_ids(FFAppState().cachedAgentInstances), ['a', 'b', 'c']);
  });

  test('a refresh keeps a restored session instead of filtering it out', () {
    final model = HomeModel();
    final b = <String, dynamic>{'id': 'b'};
    model.agentInstances = <dynamic>[{'id': 'a'}, b];
    final server = <dynamic>[{'id': 'a'}, {'id': 'b'}];

    final at = model.removeInstance('b');
    expect(_ids(model.mergeRefreshedInstances(server, preserveExistingTail: false)), ['a']);

    model.restoreInstance(b, index: at);
    expect(_ids(model.mergeRefreshedInstances(server, preserveExistingTail: false)), ['a', 'b']);
  });

  test('restoring a session that is already back does not duplicate it', () {
    final model = HomeModel();
    final b = <String, dynamic>{'id': 'b'};
    model.agentInstances = <dynamic>[{'id': 'a'}, b];

    final at = model.removeInstance('b');
    model.agentInstances = <dynamic>[{'id': 'a'}, {'id': 'b'}];
    model.restoreInstance(b, index: at);
    expect(_ids(model.agentInstances), ['a', 'b']);
  });
}
