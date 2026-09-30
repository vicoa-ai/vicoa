// Spec for the typed `rpc_list_files` + `rpc_read_file` + `rpc_download_file`
// wrappers.
// Covers `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers.
//
// Tests use an injected `RpcCaller` fake — no live WebSocket needed.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/rpc_files.dart';

void main() {
  group('rpcListFiles', () {
    test('daemon error code surfaces as FileOpsException', () async {
      Future<Map<String, dynamic>> fakeCall(String _, String __, Map<String, dynamic> ___) async {
        return {'error': 'outside_project'};
      }
      expect(
        () => rpcListFiles(
          call: fakeCall,
          machineId: 'm',
          cwd: '/p',
          path: '../escape',
        ),
        throwsA(isA<FileOpsException>().having(
          (e) => e.code,
          'code',
          'outside_project',
        )),
      );
    });

    test('parses a successful daemon response into typed FilesEntry rows', () async {
      Future<Map<String, dynamic>> fakeCall(
        String machineId,
        String method,
        Map<String, dynamic> params,
      ) async {
        expect(machineId, 'm-1');
        expect(method, 'list-files');
        expect(params, {'cwd': '/proj', 'path': 'src'});
        return {
          'entries': [
            {'name': 'lib', 'type': 'dir'},
            {'name': 'main.dart', 'type': 'file', 'size': 42},
          ],
        };
      }

      final entries = await rpcListFiles(
        call: fakeCall,
        machineId: 'm-1',
        cwd: '/proj',
        path: 'src',
      );
      expect(entries, hasLength(2));
      expect(entries[0].name, 'lib');
      expect(entries[0].isDir, isTrue);
      expect(entries[0].size, isNull);
      expect(entries[1].name, 'main.dart');
      expect(entries[1].isDir, isFalse);
      expect(entries[1].size, 42);
    });
  });

  group('rpcReadFile', () {
    test('parses a text response into a typed FileContent', () async {
      Future<Map<String, dynamic>> fakeCall(
        String machineId,
        String method,
        Map<String, dynamic> params,
      ) async {
        expect(method, 'read-file');
        return {
          'content': 'hello\n',
          'encoding': 'utf-8',
          'is_binary': false,
          'size': 6,
          'truncated': false,
        };
      }

      final content = await rpcReadFile(
        call: fakeCall,
        machineId: 'm',
        cwd: '/p',
        path: 'hi.txt',
      );
      expect(content.content, 'hello\n');
      expect(content.encoding, 'utf-8');
      expect(content.isBinary, isFalse);
      expect(content.size, 6);
      expect(content.truncated, isFalse);
    });

    test('error code surfaces as FileOpsException', () async {
      Future<Map<String, dynamic>> fakeCall(String _, String __, Map<String, dynamic> ___) async {
        return {'error': 'path_not_found'};
      }
      expect(
        () => rpcReadFile(call: fakeCall, machineId: 'm', cwd: '/p', path: 'gone'),
        throwsA(isA<FileOpsException>().having((e) => e.code, 'code', 'path_not_found')),
      );
    });

    test('a video carries its mime type', () async {
      Future<Map<String, dynamic>> fakeCall(String _, String __, Map<String, dynamic> ___) async {
        return {
          'content': '',
          'encoding': 'utf-8',
          'is_binary': true,
          'size': 1024,
          'truncated': false,
          'mime_type': 'video/mp4',
        };
      }
      final content = await rpcReadFile(call: fakeCall, machineId: 'm', cwd: '/p', path: 'a.mp4');
      expect(content.mimeType, 'video/mp4');
      expect(content.isVideo, isTrue);
    });

    test('an older daemon sends no mime type, so nothing is a video', () async {
      Future<Map<String, dynamic>> fakeCall(String _, String __, Map<String, dynamic> ___) async {
        return {'content': '', 'encoding': 'utf-8', 'is_binary': true, 'size': 1024, 'truncated': false};
      }
      final content = await rpcReadFile(call: fakeCall, machineId: 'm', cwd: '/p', path: 'a.mp4');
      expect(content.mimeType, isNull);
      expect(content.isVideo, isFalse);
    });
  });

  group('rpcDownloadFile', () {
    late Directory tmp;
    setUp(() => tmp = Directory.systemTemp.createTempSync('rpc_download_test_'));
    tearDown(() => tmp.deleteSync(recursive: true));

    final source = Uint8List.fromList(List.generate(2500, (i) => i % 251));

    // Serves `read-file-range` slices of [data] like the daemon does, with
    // an optional per-call override to simulate a file changing underneath.
    RpcCaller rangeServer(
      Uint8List data, {
      List<Map<String, dynamic>>? calls,
      Map<String, dynamic>? Function(int offset)? override,
    }) {
      return (String machineId, String method, Map<String, dynamic> params) async {
        expect(method, 'read-file-range');
        calls?.add(params);
        final offset = params['offset'] as int;
        final forced = override?.call(offset);
        if (forced != null) return forced;
        final end = (offset + (params['length'] as int)).clamp(0, data.length);
        final slice = offset >= data.length ? Uint8List(0) : data.sublist(offset, end);
        // Out-of-order completion, like parallel relay round trips.
        await Future<void>.delayed(Duration(milliseconds: (offset ~/ 1000).isEven ? 5 : 0));
        return {
          'content': base64Encode(slice),
          'encoding': 'base64',
          'offset': offset,
          'size': data.length,
          'mtime': 1700000000.5,
        };
      };
    }

    test('reassembles out-of-order slices into the exact bytes', () async {
      final calls = <Map<String, dynamic>>[];
      final dest = File('${tmp.path}/clip.mp4');
      final progress = <int>[];
      await rpcDownloadFile(
        call: rangeServer(source, calls: calls),
        machineId: 'm',
        cwd: '/p',
        path: 'clip.mp4',
        size: source.length,
        dest: dest,
        chunkBytes: 1000,
        onProgress: progress.add,
      );
      expect(dest.readAsBytesSync(), source);
      expect(calls.map((c) => c['offset']).toSet(), {0, 1000, 2000});
      expect(calls.first, containsPair('path', 'clip.mp4'));
      expect(progress.last, source.length);
    });

    test('a file that changes mid-download fails with file_changed', () async {
      final dest = File('${tmp.path}/clip.mp4');
      expect(
        () => rpcDownloadFile(
          call: rangeServer(source, override: (int offset) {
            if (offset != 2000) return null;
            return {'content': '', 'encoding': 'base64', 'offset': offset, 'size': source.length, 'mtime': 1700000099.0};
          }),
          machineId: 'm',
          cwd: '/p',
          path: 'clip.mp4',
          size: source.length,
          dest: dest,
          chunkBytes: 1000,
        ),
        throwsA(isA<FileOpsException>().having((e) => e.code, 'code', 'file_changed')),
      );
    });

    test('a daemon error stops the download', () async {
      final calls = <Map<String, dynamic>>[];
      final dest = File('${tmp.path}/clip.mp4');
      await expectLater(
        rpcDownloadFile(
          call: rangeServer(source, calls: calls, override: (_) => <String, dynamic>{'error': 'permission_denied'}),
          machineId: 'm',
          cwd: '/p',
          path: 'clip.mp4',
          size: source.length,
          dest: dest,
          chunkBytes: 100,
          parallelism: 2,
        ),
        throwsA(isA<FileOpsException>().having((e) => e.code, 'code', 'permission_denied')),
      );
      // Only the slices already in flight were asked for, not all 25.
      expect(calls.length, lessThanOrEqualTo(2));
    });

    test('cancelling stops before the next slice', () async {
      final calls = <Map<String, dynamic>>[];
      final dest = File('${tmp.path}/clip.mp4');
      await expectLater(
        rpcDownloadFile(
          call: rangeServer(source, calls: calls),
          machineId: 'm',
          cwd: '/p',
          path: 'clip.mp4',
          size: source.length,
          dest: dest,
          chunkBytes: 100,
          parallelism: 1,
          isCancelled: () => calls.length >= 3,
        ),
        throwsA(isA<FileOpsException>().having((e) => e.code, 'code', 'cancelled')),
      );
      expect(calls, hasLength(3));
    });
  });
}
