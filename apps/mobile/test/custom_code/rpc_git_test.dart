// Spec for the typed `rpcGitStatus` + `rpcGitDiff` wrappers.
// Covers `plans/todos/vicoa-app-git-tab.md` §Phase C RPC wrappers.
//
// Tests use an injected `RpcCaller` fake — no live WebSocket needed.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/rpc_git.dart';

void main() {
  group('rpcGitStatus', () {
    test('parses branch + per-file payload into typed sections', () async {
      Future<Map<String, dynamic>> fakeCall(
        String machineId,
        String method,
        Map<String, dynamic> params,
      ) async {
        expect(method, 'git-status');
        expect(params, {'cwd': '/proj'});
        return {
          'branch': 'main',
          'ahead': 2,
          'behind': 1,
          'upstream': 'origin/main',
          'staged': [
            {
              'path': 'a.dart',
              'status': 'A',
              'additions': 5,
              'deletions': 0,
              'content_hash': 'h-a',
            },
          ],
          'unstaged': [
            {
              'path': 'b.dart',
              'status': 'M',
              'additions': 1,
              'deletions': 1,
              'content_hash': 'h-b',
            },
          ],
          'untracked': [
            {
              'path': 'c.txt',
              'status': '??',
              'additions': 3,
              'deletions': 0,
              'content_hash': 'h-c',
            },
          ],
        };
      }

      final result = await rpcGitStatus(
        call: fakeCall,
        machineId: 'm',
        cwd: '/proj',
      );
      expect(result.branch, 'main');
      expect(result.ahead, 2);
      expect(result.behind, 1);
      expect(result.upstream, 'origin/main');
      expect(result.detachedHead, isFalse);
      expect(result.staged.single.path, 'a.dart');
      expect(result.staged.single.status, 'A');
      expect(result.staged.single.additions, 5);
      expect(result.staged.single.contentHash, 'h-a');
      expect(result.unstaged.single.status, 'M');
      expect(result.untracked.single.path, 'c.txt');
    });

    test('reads detached_head and renames', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> ___,
      ) async {
        return {
          'branch': 'abc1234',
          'ahead': 0,
          'behind': 0,
          'detached_head': true,
          'staged': [
            {
              'path': 'new.dart',
              'status': 'R',
              'additions': 0,
              'deletions': 0,
              'content_hash': 'h',
              'old_path': 'old.dart',
            },
          ],
          'unstaged': [],
          'untracked': [],
        };
      }

      final result = await rpcGitStatus(
        call: fakeCall,
        machineId: 'm',
        cwd: '/p',
      );
      expect(result.detachedHead, isTrue);
      expect(result.branch, 'abc1234');
      expect(result.staged.single.oldPath, 'old.dart');
    });

    test('null content_hash (deleted file) parses through', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> ___,
      ) async {
        return {
          'branch': 'main',
          'ahead': 0,
          'behind': 0,
          'staged': [],
          'unstaged': [
            {
              'path': 'gone.dart',
              'status': 'D',
              'additions': 0,
              'deletions': 4,
              'content_hash': null,
            },
          ],
          'untracked': [],
        };
      }

      final result = await rpcGitStatus(
        call: fakeCall,
        machineId: 'm',
        cwd: '/p',
      );
      expect(result.unstaged.single.contentHash, isNull);
      expect(result.unstaged.single.status, 'D');
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
        () => rpcGitStatus(call: fakeCall, machineId: 'm', cwd: '/p'),
        throwsA(
          isA<GitOpsException>().having((e) => e.code, 'code', 'not_a_repo'),
        ),
      );
    });
  });

  group('rpcGitDiff', () {
    test('parses hunks with typed lines', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String method,
        Map<String, dynamic> params,
      ) async {
        expect(method, 'git-diff');
        expect(params, {
          'cwd': '/p',
          'path': 'a.dart',
          'staged': false,
          'ignore_whitespace': false,
        });
        return {
          'path': 'a.dart',
          'hunks': [
            {
              'header': '@@ -1,1 +1,2 @@',
              'old_start': 1,
              'old_count': 1,
              'new_start': 1,
              'new_count': 2,
              'lines': [
                {'type': 'context', 'content': 'a'},
                {'type': 'add', 'content': 'b'},
              ],
            }
          ],
          'is_binary': false,
          'truncated': false,
          'size': 4,
        };
      }

      final result = await rpcGitDiff(
        call: fakeCall,
        machineId: 'm',
        cwd: '/p',
        path: 'a.dart',
        staged: false,
        ignoreWhitespace: false,
      );
      expect(result.path, 'a.dart');
      expect(result.isBinary, isFalse);
      expect(result.truncated, isFalse);
      expect(result.size, 4);
      expect(result.hunks, hasLength(1));
      final hunk = result.hunks.single;
      expect(hunk.oldStart, 1);
      expect(hunk.newCount, 2);
      expect(hunk.lines.first.type, 'context');
      expect(hunk.lines.first.content, 'a');
      expect(hunk.lines.last.type, 'add');
      expect(hunk.lines.last.content, 'b');
    });

    test('binary payload parses with empty hunks', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> ___,
      ) async {
        return {
          'path': 'logo.png',
          'hunks': [],
          'is_binary': true,
          'truncated': false,
          'size': 12345,
        };
      }
      final result = await rpcGitDiff(
        call: fakeCall,
        machineId: 'm',
        cwd: '/p',
        path: 'logo.png',
        staged: false,
        ignoreWhitespace: false,
      );
      expect(result.isBinary, isTrue);
      expect(result.hunks, isEmpty);
      expect(result.size, 12345);
    });

    test('daemon error surfaces as GitOpsException', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> ___,
      ) async {
        return {'error': 'outside_project'};
      }
      expect(
        () => rpcGitDiff(
          call: fakeCall,
          machineId: 'm',
          cwd: '/p',
          path: '../x',
          staged: false,
          ignoreWhitespace: false,
        ),
        throwsA(
          isA<GitOpsException>().having((e) => e.code, 'code', 'outside_project'),
        ),
      );
    });
  });
}
