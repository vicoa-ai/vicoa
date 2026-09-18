// Spec for CheckoutBranchResolver — the home page's per-checkout branch cache
// fed by `git-status`:
//   - seeded from the persisted map, so a card paints before any RPC;
//   - a resolved branch notifies + persists only when it actually changed;
//   - detached HEAD is stored as '' (known, nameless);
//   - a daemon verdict (not_a_repo / path_not_found) forgets the entry, a
//     transport failure keeps the last-known label;
//   - a target already in flight is not asked twice; onlyUnknown skips cached
//     targets; the cache is bounded.
//
// Uses an injected `RpcCaller` fake — no live WebSocket needed.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/home/checkout_branches.dart';

void main() {
  group('CheckoutBranchResolver', () {
    test('seed answers before any RPC; key ignores trailing slash', () {
      final r = CheckoutBranchResolver(
        call: (m, method, p) async => fail('no RPC expected'),
        onChanged: () {},
        seed: {branchCacheKey('m1', '~/app'): 'feat/seeded'},
      );
      expect(r.branchFor('m1', '~/app'), 'feat/seeded');
      expect(r.branchFor('m1', '~/app/'), 'feat/seeded');
      expect(r.branchFor('m2', '~/app'), isNull);
    });

    test('resolves, notifies and persists a changed branch; silent when unchanged', () async {
      var branch = 'main';
      var changed = 0;
      Map<String, String>? persisted;
      final r = CheckoutBranchResolver(
        call: (m, method, p) async {
          expect(method, 'git-status');
          expect(p, {'cwd': '~/app'});
          return {'branch': branch};
        },
        onChanged: () => changed++,
        persist: (b) => persisted = b,
      );
      const target = (machineId: 'm1', path: '~/app');

      await r.refresh([target]);
      expect(r.branchFor('m1', '~/app'), 'main');
      expect(changed, 1);
      expect(persisted, {branchCacheKey('m1', '~/app'): 'main'});

      await r.refresh([target]);
      expect(changed, 1, reason: 'same branch → no rebuild, no write');

      branch = 'feat/x';
      await r.refresh([target]);
      expect(r.branchFor('m1', '~/app'), 'feat/x');
      expect(changed, 2);
      expect(persisted![branchCacheKey('m1', '~/app')], 'feat/x');
    });

    test('detached HEAD is stored as an empty branch', () async {
      final r = CheckoutBranchResolver(
        call: (m, method, p) async => {'branch': '', 'detached_head': true},
        onChanged: () {},
      );
      await r.refresh([(machineId: 'm1', path: '~/app')]);
      expect(r.branchFor('m1', '~/app'), '');
    });

    test('daemon says not_a_repo → entry forgotten (and that change notifies)', () async {
      var changed = 0;
      final r = CheckoutBranchResolver(
        call: (m, method, p) async => {'error': 'not_a_repo'},
        onChanged: () => changed++,
        seed: {branchCacheKey('m1', '~/plain'): 'stale'},
      );
      await r.refresh([(machineId: 'm1', path: '~/plain')]);
      expect(r.branchFor('m1', '~/plain'), isNull);
      expect(changed, 1);
      await r.refresh([(machineId: 'm1', path: '~/plain')]);
      expect(changed, 1, reason: 'already absent → no-op');
    });

    test('transport failure keeps the last-known branch and stays quiet', () async {
      var changed = 0;
      final r = CheckoutBranchResolver(
        call: (m, method, p) async => throw StateError('no_handler'),
        onChanged: () => changed++,
        seed: {branchCacheKey('m1', '~/app'): 'main'},
      );
      await r.refresh([(machineId: 'm1', path: '~/app')]);
      expect(r.branchFor('m1', '~/app'), 'main');
      expect(changed, 0);
    });

    test('each target notifies as it lands; a slow one does not hold the rest', () async {
      final slow = Completer<Map<String, dynamic>>();
      var changed = 0;
      final r = CheckoutBranchResolver(
        call: (m, method, p) => p['cwd'] == '~/slow' ? slow.future : Future.value({'branch': 'fast'}),
        onChanged: () => changed++,
      );
      final done = r.refresh([
        (machineId: 'm1', path: '~/slow'),
        (machineId: 'm1', path: '~/fast'),
      ]);
      await Future<void>.delayed(Duration.zero);
      expect(r.branchFor('m1', '~/fast'), 'fast');
      expect(changed, 1);
      slow.complete({'branch': 'eventually'});
      await done;
      expect(r.branchFor('m1', '~/slow'), 'eventually');
      expect(changed, 2);
    });

    test('a target in flight is not asked twice', () async {
      final gate = Completer<Map<String, dynamic>>();
      var calls = 0;
      final r = CheckoutBranchResolver(
        call: (m, method, p) { calls++; return gate.future; },
        onChanged: () {},
      );
      const target = (machineId: 'm1', path: '~/app');
      final first = r.refresh([target]);
      final second = r.refresh([target]);
      gate.complete({'branch': 'main'});
      await Future.wait([first, second]);
      expect(calls, 1);
      await r.refresh([target]);
      expect(calls, 2, reason: 'once settled, a later refresh asks again');
    });

    test('onlyUnknown skips targets that already have a branch', () async {
      final asked = <String>[];
      final r = CheckoutBranchResolver(
        call: (m, method, p) async { asked.add(p['cwd'] as String); return {'branch': 'b'}; },
        onChanged: () {},
        seed: {branchCacheKey('m1', '~/known'): 'main'},
      );
      await r.refresh(
        [(machineId: 'm1', path: '~/known'), (machineId: 'm1', path: '~/new')],
        onlyUnknown: true,
      );
      expect(asked, ['~/new']);
      await r.refresh([(machineId: 'm1', path: '~/known')]);
      expect(asked, ['~/new', '~/known'], reason: 'a plain refresh re-asks');
    });

    test('cache is bounded: oldest-touched entries fall off first', () async {
      Map<String, String>? persisted;
      final r = CheckoutBranchResolver(
        call: (m, method, p) async => {'branch': 'b'},
        onChanged: () {},
        persist: (b) => persisted = b,
      );
      for (var i = 0; i <= CheckoutBranchResolver.maxEntries; i++) {
        await r.refresh([(machineId: 'm', path: '~/p$i')]);
      }
      expect(persisted, hasLength(CheckoutBranchResolver.maxEntries));
      expect(r.branchFor('m', '~/p0'), isNull);
      expect(r.branchFor('m', '~/p${CheckoutBranchResolver.maxEntries}'), 'b');
    });
  });
}
