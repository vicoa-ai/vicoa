// The "Runs in" picker lists the sessions an automation can run in. Rows come
// from both the session list and search, and the scheduler needs a computer
// and a folder to resume a session in.
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/automations/session_target.dart';

Map<String, dynamic> _session([Map<String, dynamic> overrides = const {}]) => {
      'id': 's-1',
      'name': 'Fix CI',
      'machine_id': 'm-1',
      'project': '~/projects/vicoa',
      'status': 'COMPLETED',
      'agent_type_name': 'Claude Code',
      'started_at': '2026-10-01T08:00:00Z',
      ...overrides,
    };

void main() {
  group('automationSessionTargetFrom', () {
    test('carries what the editor needs from the session', () {
      final target = automationSessionTargetFrom(_session())!;
      expect(target.id, 's-1');
      expect(target.title, 'Fix CI');
      expect(target.machineId, 'm-1');
      expect(target.project, '~/projects/vicoa');
      expect(target.agent, 'claude');
    });

    test('leaves out sessions the scheduler could never resume', () {
      expect(automationSessionTargetFrom(_session({'machine_id': null})), isNull);
      expect(automationSessionTargetFrom(_session({'project': ''})), isNull);
      expect(automationSessionTargetFrom(_session({'status': 'DELETED'})), isNull);
      expect(automationSessionTargetFrom('not a session'), isNull);
    });

    test('titles an unnamed session like its Home card', () {
      final target = automationSessionTargetFrom(
          _session({'name': null, 'latest_message': 'Run the tests'}))!;
      expect(target.title, 'Run the tests');
    });

    test('takes the agent from the session config, else the agent type', () {
      expect(
        automationSessionTargetFrom(_session({'session_config': {'agent': 'codex'}}))!.agent,
        'codex',
      );
      // Search results carry no session config.
      expect(automationSessionTargetFrom(_session({'agent_type_name': 'OpenCode'}))!.agent, 'opencode');
    });

    test('dates the row by the latest message, else the start', () {
      expect(
        automationSessionTargetFrom(_session({'latest_message_at': '2026-10-05T09:30:00Z'}))!.at,
        DateTime.utc(2026, 10, 5, 9, 30).toLocal(),
      );
      expect(automationSessionTargetFrom(_session())!.at, DateTime.utc(2026, 10, 1, 8).toLocal());
    });
  });

  test('automationSessionTargets keeps the pickable sessions in order', () {
    final targets = automationSessionTargets([
      _session({'id': 'a'}),
      _session({'id': 'b', 'machine_id': null}),
      _session({'id': 'c'}),
    ]);
    expect(targets.map((t) => t.id), ['a', 'c']);
  });
}
