// Spec for the `github-pr-list` wrapper and its shared cache (rpc_github.dart):
//   - parses the daemon's `{prs: {branch: {...}}}` into typed PRs;
//   - "this repo has no PRs to show" errors resolve to an empty map, a
//     transient one throws so callers keep what they show;
//   - a request within maxAge is reused (also while in flight), a failure is
//     never cached, and the last answer stays peekable during a refresh.
//
// Uses an injected `RpcCaller` fake — no live WebSocket needed.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/rpc_git.dart';
import 'package:vicoa/custom_code/actions/rpc_github.dart';

Map<String, dynamic> prJson(int number, String state, {String checks = 'none', String? head}) => {
      'number': number,
      'title': 'PR $number',
      'state': state,
      'url': 'https://github.com/o/r/pull/$number',
      'checks': checks,
      if (head != null) 'head': head,
    };

void main() {
  setUp(resetGithubPrListCache);

  group('rpcGithubPrList', () {
    test('parses PRs keyed by branch and sends cwd', () async {
      final prs = await rpcGithubPrList(
        call: (m, method, p) async {
          expect(method, 'github-pr-list');
          expect(p, {'cwd': '~/app'});
          return {
            'prs': {
              'feat': prJson(7, 'open', checks: 'pass', head: 'abc'),
              'old': prJson(3, 'merged'),
              'bad': {'title': 'no number'},
            },
          };
        },
        machineId: 'm1',
        cwd: '~/app',
      );
      expect(prs.keys, unorderedEquals(['feat', 'old']));
      expect(prs['feat']!.state, PrState.open);
      expect(prs['feat']!.checks, PrChecks.pass);
      expect(prs['feat']!.head, 'abc');
      expect(prs['old']!.state, PrState.merged);
      expect(prs['old']!.head, isNull);
    });

    test('settled errors are an empty map; a transient one throws', () async {
      for (final code in kSettledPrErrors) {
        final prs = await rpcGithubPrList(
          call: (m, method, p) async => {'error': code},
          machineId: 'm1',
          cwd: '~/app',
        );
        expect(prs, isEmpty, reason: code);
      }
      expect(
        rpcGithubPrList(
          call: (m, method, p) async => {'error': 'gh_unavailable'},
          machineId: 'm1',
          cwd: '~/app',
        ),
        throwsA(isA<GitOpsException>().having((e) => e.code, 'code', 'gh_unavailable')),
      );
    });

    test('PrInfo survives a JSON round trip', () {
      final pr = PrInfo.fromJson(prJson(5, 'draft', checks: 'pending', head: 'h'))!;
      expect(PrInfo.fromJson(pr.toJson()), pr);
    });
  });

  group('rpcGithubPrListCached', () {
    test('reuses a request within maxAge, in flight or settled', () async {
      var calls = 0;
      final gate = Completer<void>();
      Future<Map<String, dynamic>> call(String m, String method, Map<String, dynamic> p) async {
        calls++;
        await gate.future;
        return {'prs': {'feat': prJson(1, 'open')}};
      }

      final a = rpcGithubPrListCached(call: call, machineId: 'm1', repoPath: '~/app');
      final b = rpcGithubPrListCached(call: call, machineId: 'm1', repoPath: '~/app/');
      gate.complete();
      expect((await a).prs['feat']!.number, 1);
      expect(identical(await a, await b), isTrue);
      await rpcGithubPrListCached(call: call, machineId: 'm1', repoPath: '~/app');
      expect(calls, 1);

      await rpcGithubPrListCached(
          call: call, machineId: 'm1', repoPath: '~/app', maxAge: Duration.zero);
      expect(calls, 2, reason: 'maxAge zero always asks');

      await rpcGithubPrListCached(call: call, machineId: 'm2', repoPath: '~/app');
      expect(calls, 3, reason: 'another machine is another repo');
    });

    test('a failure is not cached, and the last answer stays peekable', () async {
      var fail = false;
      Future<Map<String, dynamic>> call(String m, String method, Map<String, dynamic> p) async {
        if (fail) return {'error': 'gh_unavailable'};
        return {'prs': {'feat': prJson(1, 'merged')}};
      }

      expect(peekGithubPrList('m1', '~/app'), isNull);
      await rpcGithubPrListCached(call: call, machineId: 'm1', repoPath: '~/app');
      expect(peekGithubPrList('m1', '~/app')!.prs['feat']!.state, PrState.merged);

      fail = true;
      await expectLater(
        rpcGithubPrListCached(call: call, machineId: 'm1', repoPath: '~/app', maxAge: Duration.zero),
        throwsA(isA<GitOpsException>()),
      );
      expect(githubPrListRequestedAt('m1', '~/app'), isNull,
          reason: 'the failed request leaves no cache entry behind');
      expect(peekGithubPrList('m1', '~/app')!.prs['feat']!.state, PrState.merged,
          reason: 'the last good answer survives a failed refresh');
    });
  });
}
