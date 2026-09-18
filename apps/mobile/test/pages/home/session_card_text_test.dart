// Spec for the session card's two text lines (lib/pages/home/session_card_text.dart):
//   - a session's branch (its own `worktree_name`, else the checkout branch
//     the home model resolved) takes over line 2 under "Group by project" and
//     follows the project name under Time/Status;
//   - `worktree_name` is read top-level first, then from instance_metadata
//     (older rows); a main checkout / plain folder has none;
//   - sessions without a branch keep the previous line-2 rules.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/home/session_card_text.dart';

Map<String, dynamic> session({
  String? name,
  String? latestMessage,
  String agentType = 'claude',
  String? project = '~/code/app',
  String? worktreeName,
  bool worktreeInMetadataOnly = false,
}) =>
    {
      'id': 'x',
      if (name != null) 'name': name,
      if (latestMessage != null) 'latest_message': latestMessage,
      'agent_type_name': agentType,
      'project': project,
      if (worktreeName != null && !worktreeInMetadataOnly) 'worktree_name': worktreeName,
      'instance_metadata': {
        if (worktreeName != null) 'worktree_name': worktreeName,
      },
    };

void main() {
  group('sessionWorktreeBranch', () {
    test('top-level worktree_name, else instance_metadata, else null', () {
      expect(sessionWorktreeBranch(session(worktreeName: 'feat/x')), 'feat/x');
      expect(sessionWorktreeBranch(session(worktreeName: 'feat/y', worktreeInMetadataOnly: true)), 'feat/y');
      expect(sessionWorktreeBranch(session()), isNull);
      expect(sessionWorktreeBranch({'worktree_name': ''}), isNull);
      expect(sessionWorktreeBranch({'instance_metadata': 'not a map'}), isNull);
    });
  });

  group('sessionCardRow2 / Project view', () {
    test('branch replaces the line for a worktree session, even a titled one', () {
      final s = session(name: 'Fix login', latestMessage: 'done', worktreeName: 'feat/login');
      expect(sessionCardRow2(s, 'Project'), (text: '', branch: 'feat/login'));
    });

    test('main checkout: the resolved checkout branch takes the line; worktree_name wins over it', () {
      final main = session(name: 'T', latestMessage: 'hi');
      expect(sessionCardRow2(main, 'Project', checkoutBranch: 'main'), (text: '', branch: 'main'));
      expect(sessionCardRow2(session(worktreeName: 'feat/x'), 'Project', checkoutBranch: 'main'), (text: '', branch: 'feat/x'));
      // Unresolved or detached → nothing to show yet, previous line stays.
      expect(sessionCardRow2(main, 'Project', checkoutBranch: null), (text: 'hi', branch: null));
      expect(sessionCardRow2(main, 'Project', checkoutBranch: ''), (text: 'hi', branch: null));
    });

    test('no branch: titled → latest message, else agent type (unchanged)', () {
      expect(sessionCardRow2(session(name: 'T', latestMessage: 'hi'), 'Project'), (text: 'hi', branch: null));
      expect(sessionCardRow2(session(name: 'T'), 'Project'), (text: 'Claude Code', branch: null));
      expect(sessionCardRow2(session(latestMessage: 'hi'), 'Project'), (text: 'Claude Code', branch: null));
      expect(sessionCardRow2(session(name: 'T', latestMessage: 'API Error x'), 'Project'), (text: 'Claude Code', branch: null));
    });
  });

  group('sessionCardRow2 / Time & Status views', () {
    test('project name, then the branch', () {
      final s = session(worktreeName: 'feat/x', project: '~/vicoa/workspaces/app-worktrees/feat-x/app/');
      expect(sessionCardRow2(s, 'Time'), (text: 'app', branch: 'feat/x'));
      expect(sessionCardRow2(s, 'Status'), (text: 'app', branch: 'feat/x'));
    });

    test('main checkout: project name, then the resolved branch', () {
      expect(sessionCardRow2(session(), 'Time', checkoutBranch: 'main'), (text: 'app', branch: 'main'));
    });

    test('branch alone when there is no project path', () {
      expect(sessionCardRow2(session(worktreeName: 'b', project: null), 'Time'), (text: '', branch: 'b'));
    });

    test('no branch: project name, else agent type (unchanged)', () {
      expect(sessionCardRow2(session(), 'Time'), (text: 'app', branch: null));
      expect(sessionCardRow2(session(project: '', agentType: 'codex'), 'Time'), (text: 'codex', branch: null));
    });
  });

  group('sessionCardRow1', () {
    test('title, else latest message, else agent type', () {
      expect(sessionCardRow1(session(name: 'T', latestMessage: 'm')), 'T');
      expect(sessionCardRow1(session(latestMessage: 'm')), 'm');
      expect(sessionCardRow1(session(agentType: 'codex')), 'codex');
      expect(sessionCardRow1(session(agentType: 'Claude')), 'Claude Code');
    });
  });
}
