// Spec for the PR helpers behind the branch icons (pr_status.dart), the
// mobile twin of the web's `pr-status.test.ts`:
//   - a checkout's PR is found by local branch, upstream or head commit, and
//     the newest of those wins;
//   - the icon and color follow the PR state, the plain branch with no PR;
//   - the checks dot is suppressed once a PR is merged or closed.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:vicoa/custom_code/actions/rpc_github.dart';
import 'package:vicoa/custom_code/utils/pr_status.dart';

PrInfo pr(int number, PrState state, {String? head, PrChecks checks = PrChecks.none}) => PrInfo(
      number: number,
      title: 'PR $number',
      state: state,
      url: 'https://github.com/o/r/pull/$number',
      checks: checks,
      head: head,
    );

void main() {
  group('prForCheckout', () {
    test('finds the PR by the local branch', () {
      final prs = {'feat': pr(7, PrState.open)};
      expect(prForCheckout(prs, branch: 'feat')?.number, 7);
    });

    test('a branch pushed under another name: the newer PR under its upstream wins', () {
      final prs = {'happy-thistle': pr(204, PrState.merged), 'cli-version': pr(208, PrState.open)};
      final found = prForCheckout(prs, branch: 'happy-thistle', upstream: 'cli-version');
      expect(found?.number, 208);
      expect(found?.state, PrState.open);
    });

    test('the newest wins whichever name found it', () {
      final prs = {'local': pr(30, PrState.open), 'remote': pr(12, PrState.merged)};
      expect(prForCheckout(prs, branch: 'local', upstream: 'remote')?.number, 30);
    });

    test('pushed without -u: the PR whose head is this checkout\'s commit', () {
      final prs = {
        'happy-thistle': pr(204, PrState.merged, head: 'aaa'),
        'cli-version': pr(208, PrState.open, head: 'bbb'),
      };
      expect(prForCheckout(prs, branch: 'happy-thistle', head: 'bbb')?.number, 208);
    });

    test('a detached checkout still matches by commit', () {
      final prs = {'feat': pr(9, PrState.draft, head: 'ccc')};
      expect(prForCheckout(prs, branch: '', head: 'ccc')?.number, 9);
    });

    test('null when nothing ties a PR to the checkout', () {
      final prs = {'other': pr(5, PrState.open, head: 'ddd')};
      expect(prForCheckout(prs, branch: 'feat', upstream: '', head: 'eee'), isNull);
      expect(prForCheckout(const {}, branch: 'feat'), isNull);
    });
  });

  group('presentation', () {
    test('icon follows the state; no PR keeps the branch glyph', () {
      expect(prIcon(null), FontAwesomeIcons.codeBranch);
      expect(prIcon(pr(1, PrState.open)), FontAwesomeIcons.codePullRequest);
      expect(prIcon(pr(1, PrState.draft)), FontAwesomeIcons.codePullRequest);
      expect(prIcon(pr(1, PrState.closed)), FontAwesomeIcons.codePullRequest);
      expect(prIcon(pr(1, PrState.merged)), FontAwesomeIcons.codeMerge);
    });

    test('GitHub colors per state and theme, the caller\'s color with no PR', () {
      const fallback = Color(0xFF123456);
      expect(prIconColor(null, Brightness.light, noPr: fallback), fallback);
      // The web's `--pr-open` / `--pr-merged` (light): hsl(137 66% 30%) and
      // hsl(261 69% 59%), i.e. Primer's #1a7f37 and #8250df give or take a
      // rounding step.
      expect(prIconColor(pr(1, PrState.open), Brightness.light, noPr: fallback).toARGB32(),
          0xFF1A7F37);
      expect(prIconColor(pr(1, PrState.merged), Brightness.light, noPr: fallback).toARGB32(),
          0xFF814EDF);
      expect(PrColors.state(PrState.open, Brightness.dark),
          isNot(PrColors.state(PrState.open, Brightness.light)));
    });

    test('checks dot: shown while open or draft, never once merged or closed', () {
      expect(checksDotColor(pr(1, PrState.open, checks: PrChecks.fail), Brightness.light),
          PrColors.state(PrState.closed, Brightness.light));
      expect(checksDotColor(pr(1, PrState.draft, checks: PrChecks.pending), Brightness.light),
          PrColors.pending(Brightness.light));
      expect(checksDotColor(pr(1, PrState.merged, checks: PrChecks.fail), Brightness.light),
          isNull);
      expect(checksDotColor(pr(1, PrState.closed, checks: PrChecks.pass), Brightness.light),
          isNull);
      expect(checksDotColor(pr(1, PrState.open), Brightness.light), isNull);
    });
  });
}
