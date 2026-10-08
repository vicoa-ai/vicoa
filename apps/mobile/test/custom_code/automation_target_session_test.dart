// An automation can run every fire in one existing session instead of a new
// one (`agent_instance_id`). The app reads the target to show "Runs in" and to
// send Run now into that session.
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/automation_utils.dart';

void main() {
  group('automationTargetSessionId', () {
    test('is the session an automation runs in', () {
      expect(automationTargetSessionId({'agent_instance_id': 's-1'}), 's-1');
    });

    test('is null for a new session each run, and on older backends', () {
      expect(automationTargetSessionId({'agent_instance_id': null}), isNull);
      expect(automationTargetSessionId({'agent_instance_id': ''}), isNull);
      expect(automationTargetSessionId(<String, dynamic>{}), isNull);
    });
  });

  group('automationTargetSessionName', () {
    test('is the session name when it has one', () {
      expect(automationTargetSessionName({'agent_instance_name': 'Fix CI'}), 'Fix CI');
    });

    test('is null for a blank or missing name', () {
      expect(automationTargetSessionName({'agent_instance_name': '  '}), isNull);
      expect(automationTargetSessionName(<String, dynamic>{}), isNull);
    });
  });
}
