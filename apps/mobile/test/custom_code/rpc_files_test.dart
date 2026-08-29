// Spec for the typed `rpc_list_files` + `rpc_read_file` wrappers.
// Covers `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers.
//
// Tests use an injected `RpcCaller` fake — no live WebSocket needed.

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
  });
}
