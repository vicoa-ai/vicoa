// Hive-backed SWR cache for the Files tab. See
// `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers + §2 #13.
//
// Each test gets its own tmp dir + box to isolate Hive state.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:vicoa/custom_code/actions/files_cache.dart';

void main() {
  late Directory dir;
  late FilesCache cache;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('files_cache_test_');
    Hive.init(dir.path);
    cache = await FilesCache.open();
  });

  tearDown(() async {
    await cache.close();
    await dir.delete(recursive: true);
  });

  test('listing put then get round-trips', () async {
    final entries = [
      {'name': 'src', 'type': 'dir'},
      {'name': 'readme.md', 'type': 'file', 'size': 42},
    ];
    await cache.putListing(
      machineId: 'm1',
      cwd: '/proj',
      path: '',
      entries: entries,
    );
    final got = cache.getListing(machineId: 'm1', cwd: '/proj', path: '');
    expect(got, equals(entries));
  });

  test('getListing returns null for an unseen key', () {
    expect(
      cache.getListing(machineId: 'm1', cwd: '/proj', path: 'nope'),
      isNull,
    );
  });

  test('listings keyed by (machineId, cwd, path) — no cross-talk', () async {
    await cache.putListing(machineId: 'a', cwd: '/p', path: '', entries: [{'name': 'A'}]);
    await cache.putListing(machineId: 'b', cwd: '/p', path: '', entries: [{'name': 'B'}]);
    await cache.putListing(machineId: 'a', cwd: '/q', path: '', entries: [{'name': 'C'}]);
    expect(cache.getListing(machineId: 'a', cwd: '/p', path: '')![0]['name'], 'A');
    expect(cache.getListing(machineId: 'b', cwd: '/p', path: '')![0]['name'], 'B');
    expect(cache.getListing(machineId: 'a', cwd: '/q', path: '')![0]['name'], 'C');
  });

  test('content put then get round-trips', () async {
    await cache.putContent(
      machineId: 'm1',
      cwd: '/p',
      path: 'main.dart',
      content: 'void main() {}',
      encoding: 'utf-8',
      isBinary: false,
      size: 14,
      truncated: false,
    );
    final got = cache.getContent(
      machineId: 'm1',
      cwd: '/p',
      path: 'main.dart',
    );
    expect(got, isNotNull);
    expect(got!['content'], 'void main() {}');
    expect(got['encoding'], 'utf-8');
    expect(got['is_binary'], isFalse);
    expect(got['size'], 14);
    expect(got['truncated'], isFalse);
  });

  test('cache evicts oldest entries when over capacity', () async {
    final small = await FilesCache.open(maxEntries: 4);
    try {
      for (var i = 0; i < 10; i++) {
        await small.putListing(
          machineId: 'm',
          cwd: '/p',
          path: 'd$i',
          entries: [{'name': 'x$i'}],
        );
      }
      // Oldest 6 must have been evicted; the most recent 4 must survive.
      expect(small.getListing(machineId: 'm', cwd: '/p', path: 'd0'), isNull);
      expect(small.getListing(machineId: 'm', cwd: '/p', path: 'd5'), isNull);
      expect(small.getListing(machineId: 'm', cwd: '/p', path: 'd6'), isNotNull);
      expect(small.getListing(machineId: 'm', cwd: '/p', path: 'd9'), isNotNull);
    } finally {
      await small.close();
    }
  });

  test('wipeAll clears every cached entry', () async {
    await cache.putListing(machineId: 'm', cwd: '/p', path: '', entries: [{'name': 'x'}]);
    await cache.putContent(
      machineId: 'm',
      cwd: '/p',
      path: 'x',
      content: 'hi',
      encoding: 'utf-8',
      isBinary: false,
      size: 2,
      truncated: false,
    );
    await cache.wipeAll();
    expect(cache.getListing(machineId: 'm', cwd: '/p', path: ''), isNull);
    expect(cache.getContent(machineId: 'm', cwd: '/p', path: 'x'), isNull);
  });
}
