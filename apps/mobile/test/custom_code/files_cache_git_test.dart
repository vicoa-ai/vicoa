// Diff + last-status cache extensions on FilesCache. See
// `plans/todos/vicoa-app-git-tab.md` §Phase C "Cache — extend
// lib/custom_code/files_cache.dart" + Foundational decision #13.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:vicoa/custom_code/actions/files_cache.dart';

void main() {
  late Directory dir;
  late FilesCache cache;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('files_cache_git_test_');
    Hive.init(dir.path);
    cache = await FilesCache.open();
  });

  tearDown(() async {
    await cache.close();
    await dir.delete(recursive: true);
  });

  // --- diff cache ---------------------------------------------------------

  test('diff put then get round-trips on matching key', () async {
    final payload = {
      'path': 'lib/foo.dart',
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
    await cache.putDiff(
      machineId: 'm1',
      cwd: '/proj',
      path: 'lib/foo.dart',
      contentHash: 'abc123',
      staged: false,
      ignoreWhitespace: false,
      payload: payload,
    );
    final got = cache.getDiff(
      machineId: 'm1',
      cwd: '/proj',
      path: 'lib/foo.dart',
      contentHash: 'abc123',
      staged: false,
      ignoreWhitespace: false,
    );
    expect(got, equals(payload));
  });

  test('getDiff returns null when content_hash changed', () async {
    // The whole point of the content_hash key: edit the file → hash changes →
    // cache miss → fresh fetch. If this regresses, stale diffs leak through.
    await cache.putDiff(
      machineId: 'm1',
      cwd: '/proj',
      path: 'a.dart',
      contentHash: 'old',
      staged: false,
      ignoreWhitespace: false,
      payload: {'hunks': []},
    );
    expect(
      cache.getDiff(
        machineId: 'm1',
        cwd: '/proj',
        path: 'a.dart',
        contentHash: 'new',
        staged: false,
        ignoreWhitespace: false,
      ),
      isNull,
    );
  });

  test('getDiff distinguishes staged from unstaged', () async {
    await cache.putDiff(
      machineId: 'm1',
      cwd: '/p',
      path: 'a.dart',
      contentHash: 'h',
      staged: true,
      ignoreWhitespace: false,
      payload: {'tag': 'staged'},
    );
    await cache.putDiff(
      machineId: 'm1',
      cwd: '/p',
      path: 'a.dart',
      contentHash: 'h',
      staged: false,
      ignoreWhitespace: false,
      payload: {'tag': 'unstaged'},
    );
    final s = cache.getDiff(
      machineId: 'm1',
      cwd: '/p',
      path: 'a.dart',
      contentHash: 'h',
      staged: true,
      ignoreWhitespace: false,
    );
    final u = cache.getDiff(
      machineId: 'm1',
      cwd: '/p',
      path: 'a.dart',
      contentHash: 'h',
      staged: false,
      ignoreWhitespace: false,
    );
    expect(s!['tag'], 'staged');
    expect(u!['tag'], 'unstaged');
  });

  test('getDiff distinguishes ignoreWhitespace flag', () async {
    await cache.putDiff(
      machineId: 'm1',
      cwd: '/p',
      path: 'a.dart',
      contentHash: 'h',
      staged: false,
      ignoreWhitespace: false,
      payload: {'ws': 'keep'},
    );
    expect(
      cache.getDiff(
        machineId: 'm1',
        cwd: '/p',
        path: 'a.dart',
        contentHash: 'h',
        staged: false,
        ignoreWhitespace: true,
      ),
      isNull,
    );
  });

  test('wipeAll clears cached diffs too', () async {
    await cache.putDiff(
      machineId: 'm1',
      cwd: '/p',
      path: 'a.dart',
      contentHash: 'h',
      staged: false,
      ignoreWhitespace: false,
      payload: {'hunks': []},
    );
    await cache.wipeAll();
    expect(
      cache.getDiff(
        machineId: 'm1',
        cwd: '/p',
        path: 'a.dart',
        contentHash: 'h',
        staged: false,
        ignoreWhitespace: false,
      ),
      isNull,
    );
  });

  // --- last-status persistence -------------------------------------------

  test('last_status put then get round-trips per (machineId, cwd)', () async {
    final payload = {
      'branch': 'main',
      'ahead': 0,
      'behind': 0,
      'staged': [],
      'unstaged': [
        {'path': 'foo.dart', 'status': 'M'}
      ],
      'untracked': [],
    };
    await cache.putLastStatus(
      machineId: 'm1',
      cwd: '/proj',
      payload: payload,
    );
    final got = cache.getLastStatus(machineId: 'm1', cwd: '/proj');
    expect(got, equals(payload));
  });

  test('last_status is overwritten — only the most recent persists', () async {
    await cache.putLastStatus(
      machineId: 'm1',
      cwd: '/p',
      payload: {'branch': 'main', 'staged': []},
    );
    await cache.putLastStatus(
      machineId: 'm1',
      cwd: '/p',
      payload: {'branch': 'feature', 'staged': []},
    );
    final got = cache.getLastStatus(machineId: 'm1', cwd: '/p');
    expect(got!['branch'], 'feature');
  });

  test('last_status keyed by machineId + cwd — no cross-talk', () async {
    await cache.putLastStatus(
      machineId: 'm1',
      cwd: '/p',
      payload: {'branch': 'a'},
    );
    await cache.putLastStatus(
      machineId: 'm2',
      cwd: '/p',
      payload: {'branch': 'b'},
    );
    expect(
      cache.getLastStatus(machineId: 'm1', cwd: '/p')!['branch'],
      'a',
    );
    expect(
      cache.getLastStatus(machineId: 'm2', cwd: '/p')!['branch'],
      'b',
    );
  });
}
