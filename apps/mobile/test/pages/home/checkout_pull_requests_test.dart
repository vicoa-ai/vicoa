// Spec for CheckoutPullRequests — the home page's PR lookup behind each git
// session's branch icon:
//   - a session folder is resolved to its repo with `git-worktree-list`, and
//     its PR matched by the checkout's branch / upstream / head;
//   - a main checkout uses `main_branch`; a daemon that can't say falls back
//     to the card's own branch;
//   - one `github-pr-list` per repo, not per session;
//   - a transient `gh` failure keeps the colors shown;
//   - persisted state paints before any RPC;
//   - onlyUnknown leaves known repos alone; the poll only re-reads repos with
//     a linked worktree; turn-end refreshes are throttled per repo.
//
// Uses an injected `RpcCaller` fake — no live WebSocket needed.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/rpc_github.dart';
import 'package:vicoa/pages/home/checkout_pull_requests.dart';

Map<String, dynamic> prJson(int number, String state, {String? head}) => {
      'number': number,
      'title': 'PR $number',
      'state': state,
      'url': 'https://github.com/o/r/pull/$number',
      'checks': 'none',
      if (head != null) 'head': head,
    };

/// A daemon with one repo: main checkout at `~/app` on `main`, and the given
/// linked worktrees.
class FakeDaemon {
  FakeDaemon({this.worktrees = const [], Map<String, dynamic>? prs}) : prs = prs ?? {};

  List<Map<String, dynamic>> worktrees;
  Map<String, dynamic> prs;
  String mainBranch = 'main';
  bool listHasMainPath = true;
  String? prError;
  final calls = <String>[];

  int count(String method) => calls.where((c) => c == method).length;

  Future<Map<String, dynamic>> call(
      String machineId, String method, Map<String, dynamic> params) async {
    calls.add(method);
    if (method == 'git-worktree-list') {
      return {
        if (listHasMainPath) ...{
          'main_path': '/Users/u/app',
          'main_display_path': '~/app',
          'main_branch': mainBranch,
        },
        'worktrees': worktrees,
      };
    }
    if (method == 'github-pr-list') {
      if (prError != null) return {'error': prError};
      return {'prs': prs};
    }
    throw StateError('unexpected $method');
  }
}

Map<String, dynamic> worktree(String name, {String upstream = '', String head = '', bool prunable = false}) => {
      'path': '/Users/u/vicoa/workspaces/app/$name',
      'display_path': '~/vicoa/workspaces/app/$name',
      'branch': name,
      'upstream': upstream,
      'head': head,
      'managed': true,
      'prunable': prunable,
    };

const mainTarget = (machineId: 'm1', path: '~/app');
const wtTarget = (machineId: 'm1', path: '~/vicoa/workspaces/app/feat');

void main() {
  setUp(resetGithubPrListCache);

  test('resolves worktree and main-checkout sessions with one PR call per repo', () async {
    final daemon = FakeDaemon(
      worktrees: [worktree('feat')],
      prs: {'feat': prJson(7, 'open'), 'main': prJson(1, 'merged')},
    );
    var changed = 0;
    final r = CheckoutPullRequests(call: daemon.call, onChanged: () => changed++);

    await r.refresh([mainTarget, wtTarget]);
    expect(r.prFor('m1', '~/vicoa/workspaces/app/feat', branch: 'feat')?.number, 7);
    expect(r.prFor('m1', '~/app', branch: 'main')?.state, PrState.merged);
    expect(r.prFor('m1', '~/app/sub/dir', branch: 'main'), isNull,
        reason: 'a folder never resolved is unknown');
    expect(daemon.count('github-pr-list'), 1);
    expect(changed, greaterThan(0));
  });

  test('a reused worktree: the newer PR under its upstream wins', () async {
    final daemon = FakeDaemon(
      worktrees: [worktree('feat', upstream: 'cli-version')],
      prs: {'feat': prJson(204, 'merged'), 'cli-version': prJson(208, 'open')},
    );
    final r = CheckoutPullRequests(call: daemon.call, onChanged: () {});
    await r.refresh([wtTarget]);
    expect(r.prFor('m1', wtTarget.path, branch: 'feat')?.number, 208);
  });

  test('a daemon without main_path falls back to the card branch', () async {
    final daemon = FakeDaemon(prs: {'topic': prJson(3, 'draft')})..listHasMainPath = false;
    final r = CheckoutPullRequests(call: daemon.call, onChanged: () {});
    await r.refresh([mainTarget]);
    expect(r.prFor('m1', '~/app', branch: 'topic')?.state, PrState.draft);
  });

  test('a transient gh failure keeps the colors shown', () async {
    final daemon = FakeDaemon(worktrees: [worktree('feat')], prs: {'feat': prJson(7, 'open')});
    final r = CheckoutPullRequests(call: daemon.call, onChanged: () {});
    await r.refresh([wtTarget]);
    daemon.prError = 'gh_unavailable';
    await r.refresh([wtTarget], maxAge: Duration.zero);
    expect(r.prFor('m1', wtTarget.path, branch: 'feat')?.number, 7);

    daemon.prError = 'gh_missing';
    await r.refresh([wtTarget], maxAge: Duration.zero);
    expect(r.prFor('m1', wtTarget.path, branch: 'feat'), isNull,
        reason: 'a settled answer (no gh) does clear them');
  });

  test('persisted state paints before any RPC', () async {
    final daemon = FakeDaemon(
      worktrees: [worktree('feat')],
      prs: {'feat': prJson(7, 'open'), 'unrelated': prJson(99, 'closed')},
    );
    Map<String, dynamic>? persisted;
    final r = CheckoutPullRequests(
      call: daemon.call,
      onChanged: () {},
      persist: (s) => persisted = s,
    );
    await r.refresh([wtTarget]);
    expect(persisted, isNotNull);

    final restored = CheckoutPullRequests(
      call: (m, method, p) async => fail('no RPC expected'),
      onChanged: () {},
      seed: persisted!,
    );
    expect(restored.prFor('m1', wtTarget.path, branch: 'feat')?.number, 7);
    final repos = persisted!['repos'] as Map;
    final prs = (repos.values.single as Map)['r'] as Map;
    expect(prs.keys, ['feat'], reason: 'only PRs some checkout resolves to are kept');
  });

  test('onlyUnknown leaves known repos alone', () async {
    final daemon = FakeDaemon(worktrees: [worktree('feat')]);
    final r = CheckoutPullRequests(call: daemon.call, onChanged: () {});
    await r.refresh([wtTarget]);
    final before = daemon.calls.length;
    await r.refresh([wtTarget], onlyUnknown: true, maxAge: Duration.zero);
    expect(daemon.calls.length, before);
  });

  test('poll re-reads only repos with a live linked worktree', () async {
    final daemon = FakeDaemon();
    final r = CheckoutPullRequests(call: daemon.call, onChanged: () {});
    await r.refresh([mainTarget]);
    resetGithubPrListCache();
    final before = daemon.calls.length;
    await r.poll([mainTarget]);
    expect(daemon.calls.length, before, reason: 'main checkout only: not polled');

    daemon.worktrees = [worktree('feat')];
    await r.refresh([mainTarget], maxAge: Duration.zero);
    resetGithubPrListCache();
    final polled = daemon.count('github-pr-list');
    await r.poll([mainTarget]);
    expect(daemon.count('github-pr-list'), polled + 1);
  });

  testWidgets('turn-end refreshes collapse into one per repo', (tester) async {
    final daemon = FakeDaemon(worktrees: [worktree('feat')], prs: {'feat': prJson(7, 'open')});
    final r = CheckoutPullRequests(call: daemon.call, onChanged: () {});
    await r.refresh([wtTarget]);
    expect(daemon.count('github-pr-list'), 1);

    daemon.prs = {'feat': prJson(7, 'merged')};
    r.requestTurnRefresh(wtTarget);
    r.requestTurnRefresh(mainTarget);
    await tester.pump(const Duration(seconds: 5));
    expect(daemon.count('github-pr-list'), 1, reason: 'within 30s of the last request');

    await tester.pump(const Duration(seconds: 30));
    await tester.pump();
    expect(daemon.count('github-pr-list'), 2, reason: 'one trailing refresh for both turns');
    expect(r.prFor('m1', wtTarget.path, branch: 'feat')?.state, PrState.merged);
    r.dispose();
  });
}
