// Spec for the typed `rpcGitWorktreeList` + `rpcGitWorktreeRemove` wrappers.
// Covers `plans/todos/vicoa-app-worktree.md` §5.1 RPC wrappers.
//
// Tests use an injected `RpcCaller` fake — no live WebSocket needed.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/rpc_git.dart';

void main() {
  group('rpcGitWorktreeList', () {
    test('parses worktrees into typed list and sends cwd', () async {
      Future<Map<String, dynamic>> fakeCall(
        String machineId,
        String method,
        Map<String, dynamic> params,
      ) async {
        expect(method, 'git-worktree-list');
        expect(params, {'cwd': '/proj'});
        return {
          'worktrees': [
            {
              'path': '/Users/u/vicoa/workspaces/app-1a2b/brave-river',
              'branch': 'brave-river',
              'head': 'abc1234',
              'managed': true,
            },
            {
              'path': '/Users/u/hand-made',
              'branch': 'manual',
              'head': 'def5678',
              'managed': false,
            },
          ],
        };
      }

      final result = await rpcGitWorktreeList(
        call: fakeCall,
        machineId: 'm',
        cwd: '/proj',
      );

      expect(result, hasLength(2));
      expect(result.first.branch, 'brave-river');
      expect(result.first.managed, isTrue);
      expect(result.first.head, 'abc1234');
      expect(result.last.managed, isFalse);
    });

    test('daemon error surfaces as GitOpsException', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> ___,
      ) async {
        return {'error': 'not_a_repo'};
      }
      expect(
        () => rpcGitWorktreeList(call: fakeCall, machineId: 'm', cwd: '/p'),
        throwsA(
          isA<GitOpsException>().having((e) => e.code, 'code', 'not_a_repo'),
        ),
      );
    });
  });

  group('rpcGitWorktreeRemove', () {
    test('sends cwd/worktree_path/force and completes on ok', () async {
      var called = false;
      Future<Map<String, dynamic>> fakeCall(
        String machineId,
        String method,
        Map<String, dynamic> params,
      ) async {
        called = true;
        expect(method, 'git-worktree-remove');
        expect(params, {
          'cwd': '/proj',
          'worktree_path': '/Users/u/vicoa/workspaces/app-1a2b/brave-river',
          'force': true,
        });
        return {'ok': true};
      }

      await rpcGitWorktreeRemove(
        call: fakeCall,
        machineId: 'm',
        cwd: '/proj',
        worktreePath: '/Users/u/vicoa/workspaces/app-1a2b/brave-river',
        force: true,
      );

      expect(called, isTrue);
    });

    test('daemon error surfaces as GitOpsException', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> ___,
      ) async {
        return {'error': 'not_managed'};
      }
      expect(
        () => rpcGitWorktreeRemove(
          call: fakeCall,
          machineId: 'm',
          cwd: '/p',
          worktreePath: '/etc',
          force: true,
        ),
        throwsA(
          isA<GitOpsException>().having((e) => e.code, 'code', 'not_managed'),
        ),
      );
    });
  });
}
