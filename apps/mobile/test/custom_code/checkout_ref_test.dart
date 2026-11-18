// Spec for `checkoutRefLabel`: how a checkout's ref reads on a worktree row,
// in the worktree picker and on the Git tab's branch strip, and for the
// `rebasing_branch` field it reads off the daemon's answers.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/rpc_git.dart';
import 'package:vicoa/custom_code/utils/checkout_ref.dart';
import 'package:vicoa/l10n/app_localizations.dart';

void main() {
  final en = lookupAppLocalizations(const Locale('en'));
  const sha = '760f39ad1ee1e86e966bd721ca1e65ed6d3f4f70';

  String label({String branch = '', String head = '', String rebasing = ''}) =>
      checkoutRefLabel(
        en,
        branch: branch,
        head: head,
        rebasingBranch: rebasing,
        unknownCommit: en.worktreesDetached,
      );

  group('checkoutRefLabel', () {
    test('a branch reads as its name', () {
      expect(label(branch: 'feat/x', head: sha), 'feat/x');
    });

    test('a detached HEAD reads as its short commit', () {
      expect(label(head: sha), '760f39a (detached)');
    });

    test('a short commit from git status is kept as is', () {
      expect(label(head: '760f39a'), '760f39a (detached)');
    });

    test('a checkout mid-rebase reads as the branch it is rebasing', () {
      expect(label(head: sha, rebasing: 'feat/x'), 'feat/x (rebasing)');
    });

    test('a detached HEAD with no commit (older daemon) falls back', () {
      expect(label(), en.worktreesDetached);
    });
  });

  group('rebasing_branch', () {
    test('WorktreeInfo reads it and exposes the branch the user is on', () {
      final rebasing = WorktreeInfo.fromJson({
        'path': '/w',
        'branch': '',
        'head': sha,
        'rebasing_branch': 'feat/x',
        'managed': true,
      });
      expect(rebasing.rebasingBranch, 'feat/x');
      expect(rebasing.currentBranch, 'feat/x');

      final older = WorktreeInfo.fromJson({
        'path': '/w',
        'branch': '',
        'head': sha,
        'managed': true,
      });
      expect(older.rebasingBranch, '');
      expect(older.currentBranch, '');
    });

    test('GitStatusResult reads it', () {
      final status = GitStatusResult.fromJson({
        'branch': '760f39a',
        'detached_head': true,
        'rebasing_branch': 'main',
      });
      expect(status.detachedHead, isTrue);
      expect(status.rebasingBranch, 'main');
    });
  });
}
