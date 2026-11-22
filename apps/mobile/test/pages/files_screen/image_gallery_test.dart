// Which images the file viewer swipes between (`image_gallery.dart`): the
// images in the opened image's folder, from the cached listing when it knows
// the file, otherwise from one `list-files` call.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:vicoa/custom_code/actions/files_cache.dart';
import 'package:vicoa/custom_code/actions/rpc_files.dart';
import 'package:vicoa/pages/files_screen/file_viewer/image_gallery.dart';

List<FilesEntry> _entries(List<String> files, {List<String> dirs = const []}) => [
      for (final d in dirs) FilesEntry(name: d, isDir: true),
      for (final f in files) FilesEntry(name: f, isDir: false),
    ];

void main() {
  group('imagesBeside', () {
    test('keeps only the images, in listing order, skipping folders and other files', () {
      final entries = _entries(['a.png', 'b.ts', 'c.JPG', 'notes.md', 'd.webp'], dirs: ['nested.png']);
      expect(imagesBeside('shots/c.JPG', entries), ['shots/a.png', 'shots/c.JPG', 'shots/d.webp']);
    });

    test('a file at the project root has no folder prefix', () {
      expect(imagesBeside('a.png', _entries(['a.png', 'b.gif'])), ['a.png', 'b.gif']);
    });

    test('null when the listing does not have the file', () {
      expect(imagesBeside('shots/new.png', _entries(['a.png', 'b.png'])), isNull);
    });
  });

  group('loadImagesBeside', () {
    late Directory dir;
    late FilesCache cache;
    late List<String> listed;
    late List<FilesEntry> onMachine;

    Future<Map<String, dynamic>> call(String machineId, String method, Map<String, dynamic> params) async {
      expect(method, 'list-files');
      listed.add(params['path'] as String);
      return {
        'entries': [for (final e in onMachine) {'name': e.name, 'type': e.isDir ? 'dir' : 'file'}],
      };
    }

    Future<List<String>?> load(String path, {bool connected = true, bool fresh = false}) =>
        loadImagesBeside(machineId: 'm', cwd: '/p', path: path, cache: cache, call: call, connected: connected, fresh: fresh);

    Future<void> cacheListing(String path, List<String> files) => cache.putListing(
          machineId: 'm',
          cwd: '/p',
          path: path,
          entries: [for (final f in files) {'name': f, 'type': 'file'}],
        );

    setUp(() async {
      dir = await Directory.systemTemp.createTemp('image_gallery_test_');
      Hive.init(dir.path);
      cache = await FilesCache.open();
      listed = [];
      onMachine = _entries(['a.png', 'b.png', 'c.png']);
    });

    tearDown(() async {
      await cache.close();
      await dir.delete(recursive: true);
    });

    test('a cached listing that has the file is used as is', () async {
      await cacheListing('shots', ['a.png', 'b.png']);
      expect(await load('shots/b.png'), ['shots/a.png', 'shots/b.png']);
      expect(listed, isEmpty);
    });

    test('lists the folder when the cache does not know the file, and caches it', () async {
      await cacheListing('shots', ['a.png', 'b.png']);
      expect(await load('shots/c.png'), ['shots/a.png', 'shots/b.png', 'shots/c.png']);
      expect(listed, ['shots']);
      final cached = cache.getListing(machineId: 'm', cwd: '/p', path: 'shots')!;
      expect(cached.map((e) => e['name']), ['a.png', 'b.png', 'c.png']);
    });

    test('fresh lists the folder even when the cache knows the file', () async {
      await cacheListing('', ['a.png', 'b.png']);
      expect(await load('a.png', fresh: true), ['a.png', 'b.png', 'c.png']);
      expect(listed, ['']);
    });

    test('offline it only has the cache', () async {
      expect(await load('shots/a.png', connected: false), isNull);
      await cacheListing('shots', ['a.png', 'b.png']);
      expect(await load('shots/a.png', connected: false, fresh: true), ['shots/a.png', 'shots/b.png']);
      expect(listed, isEmpty);
    });

    test('null when the image is alone in its folder', () async {
      onMachine = _entries(['a.png', 'readme.md']);
      expect(await load('a.png'), isNull);
    });

    test('a failed listing falls back to no gallery', () async {
      Future<Map<String, dynamic>> failing(String _, String __, Map<String, dynamic> ___) async => {'error': 'permission_denied'};
      expect(await loadImagesBeside(machineId: 'm', cwd: '/p', path: 'a.png', cache: cache, call: failing, connected: true), isNull);
    });
  });
}
