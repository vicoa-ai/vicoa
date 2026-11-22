// One file's load for the viewer (`file_content_loader.dart`): live first,
// the cached copy when the machine is unreachable, and only files the user
// actually viewed get written to the cache.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:vicoa/custom_code/actions/files_cache.dart';
import 'package:vicoa/custom_code/actions/rpc_files.dart';
import 'package:vicoa/pages/files_screen/file_viewer/file_content_loader.dart';

void main() {
  late Directory dir;
  late FilesCache cache;
  late bool connected;
  late Map<String, dynamic> Function(String path) respond;

  Future<Map<String, dynamic>> call(String machineId, String method, Map<String, dynamic> params) async {
    expect(method, 'read-file');
    return respond(params['path'] as String);
  }

  Map<String, dynamic> image(List<int> bytes) => {'content': base64Encode(bytes), 'encoding': 'base64', 'is_binary': true, 'size': bytes.length, 'truncated': false};

  FileContentLoader loader(String path, {bool viewed = true}) =>
      FileContentLoader(machineId: 'm', cwd: '/p', path: path, cache: Future.value(cache), call: call, isConnected: () => connected, viewed: viewed);

  bool cached(String path) => cache.getContent(machineId: 'm', cwd: '/p', path: path) != null;

  // `_save` is fire-and-forget; let its Hive write land.
  Future<void> settleWrites() => Future<void>.delayed(const Duration(milliseconds: 50));

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('file_content_loader_test_');
    Hive.init(dir.path);
    cache = await FilesCache.open();
    connected = true;
    respond = (_) => image([1, 2, 3]);
  });

  tearDown(() async {
    await settleWrites();
    await cache.close();
    await dir.delete(recursive: true);
  });

  test('a viewed file is cached as soon as it loads', () async {
    final l = loader('a.png');
    await l.load();
    await settleWrites();
    expect(l.loading, isFalse);
    expect(l.imageBytes, [1, 2, 3]);
    expect(cached('a.png'), isTrue);
  });

  test('a preloaded file is cached only once it is viewed', () async {
    final l = loader('b.png', viewed: false);
    await l.load();
    await settleWrites();
    expect(l.content, isNotNull);
    expect(cached('b.png'), isFalse);
    l.markViewed();
    await settleWrites();
    expect(cached('b.png'), isTrue);
  });

  test('a preload viewed before it finishes is cached when it lands', () async {
    final l = loader('b.png', viewed: false);
    final pending = l.load();
    l.markViewed();
    await pending;
    await settleWrites();
    expect(cached('b.png'), isTrue);
  });

  test('offline shows the cached copy', () async {
    await cache.putContent(machineId: 'm', cwd: '/p', path: 'a.png', content: base64Encode([9]), encoding: 'base64', isBinary: true, size: 1, truncated: false);
    connected = false;
    final l = loader('a.png');
    await l.load();
    expect(l.offline, isTrue);
    expect(l.imageBytes, [9]);
  });

  test('a daemon error is shown, not treated as offline', () async {
    respond = (_) => {'error': 'path_not_found'};
    final l = loader('gone.png');
    await l.load();
    expect(l.errorCode, 'path_not_found');
    expect(l.offline, isFalse);
  });

  test('imageBytes is decoded once and is null for text', () async {
    final l = loader('a.png');
    await l.load();
    expect(identical(l.imageBytes, l.imageBytes), isTrue);
    respond = (_) => {'content': 'hi', 'encoding': 'utf-8', 'is_binary': false, 'size': 2, 'truncated': false};
    final t = loader('a.txt');
    await t.load();
    expect(t.content, isA<FileContent>());
    expect(t.imageBytes, isNull);
  });
}
