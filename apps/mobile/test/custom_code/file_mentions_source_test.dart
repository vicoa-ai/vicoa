// Spec for the `@`-mention source selection: live daemon index first, the
// CLI-synced DB copy as fallback.
// Covers `plans/todos/file-mentions-live-rpc.md` §Phase 3.
//
// Tests use an injected `RpcCaller` fake — no live WebSocket needed. The REST
// fallback is the real `apiGetFileMentions`, which swallows its own errors and
// returns an empty list without a signed-in session, so "fell back to REST"
// reads here as "returned empty via FileMentionsSource.rest".

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/fetch_file_mentions.dart';
import 'package:vicoa/custom_code/actions/rpc_file_index.dart';
import 'package:vicoa/custom_code/actions/ws_client.dart';

const _index = {
  'files': ['src/', 'src/main.dart'],
  'file_count': 2,
  'hash': 'abc123',
  'truncated': false,
  'scanned_at': 0,
};

void main() {
  setUp(resetFileIndexSupport);

  group('rpcScanFiles', () {
    test('parses a full index', () async {
      Future<Map<String, dynamic>> fakeCall(
        String machineId,
        String method,
        Map<String, dynamic> params,
      ) async {
        expect(machineId, 'm-1');
        expect(method, 'scan-files');
        expect(params, {'cwd': '/proj'});
        return Map<String, dynamic>.from(_index);
      }

      final result = await rpcScanFiles(
          call: fakeCall, machineId: 'm-1', cwd: '/proj');

      expect(result.unchanged, isFalse);
      expect(result.files, ['src/', 'src/main.dart']);
      expect(result.hash, 'abc123');
    });

    test('sends known_hash and understands the unchanged reply', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> params,
      ) async {
        expect(params['known_hash'], 'abc123');
        return {'unchanged': true, 'hash': 'abc123'};
      }

      final result = await rpcScanFiles(
        call: fakeCall,
        machineId: 'm-1',
        cwd: '/proj',
        knownHash: 'abc123',
      );

      // Null files means "keep what you have" — the caller must not treat it
      // as an empty project and wipe its cache.
      expect(result.unchanged, isTrue);
      expect(result.files, isNull);
    });

    test('omits known_hash when the caller has none', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> params,
      ) async {
        expect(params.containsKey('known_hash'), isFalse);
        return Map<String, dynamic>.from(_index);
      }

      await rpcScanFiles(call: fakeCall, machineId: 'm-1', cwd: '/proj');
    });

    test('daemon error code surfaces as FileIndexException', () async {
      Future<Map<String, dynamic>> fakeCall(
              String _, String __, Map<String, dynamic> ___) async =>
          {'error': 'path_not_found'};

      expect(
        () => rpcScanFiles(call: fakeCall, machineId: 'm', cwd: '/gone'),
        throwsA(isA<FileIndexException>()
            .having((e) => e.code, 'code', 'path_not_found')),
      );
    });
  });

  group('fetchFileMentions source selection', () {
    test('prefers the live daemon index', () async {
      Future<Map<String, dynamic>> fakeCall(
              String _, String __, Map<String, dynamic> ___) async =>
          Map<String, dynamic>.from(_index);

      final result = await fetchFileMentions(
          projectPath: '/proj', machineId: 'm-1', call: fakeCall);

      expect(result.source, FileMentionsSource.rpc);
      expect(result.files, ['src/', 'src/main.dart']);
    });

    test('skips the RPC entirely when the session has no machine', () async {
      var called = false;
      Future<Map<String, dynamic>> fakeCall(
          String _, String __, Map<String, dynamic> ___) async {
        called = true;
        return Map<String, dynamic>.from(_index);
      }

      final result =
          await fetchFileMentions(projectPath: '/proj', call: fakeCall);

      expect(called, isFalse);
      expect(result.source, FileMentionsSource.rest);
    });

    test('falls back to the DB copy when the daemon is unreachable', () async {
      Future<Map<String, dynamic>> fakeCall(
              String _, String __, Map<String, dynamic> ___) async =>
          throw const RpcException('target_disconnected');

      final result = await fetchFileMentions(
          projectPath: '/proj', machineId: 'm-1', call: fakeCall);

      expect(result.source, FileMentionsSource.rest);
    });

    test('trusts the daemon on path_not_found instead of falling back',
        () async {
      // The daemon is authoritative about its own disk. Serving the DB copy
      // here would resurrect paths that no longer exist on that machine.
      Future<Map<String, dynamic>> fakeCall(
              String _, String __, Map<String, dynamic> ___) async =>
          {'error': 'path_not_found'};

      final result = await fetchFileMentions(
          projectPath: '/gone', machineId: 'm-1', call: fakeCall);

      expect(result.source, FileMentionsSource.rpc);
      expect(result.files, isEmpty);
    });

    test('stops retrying a daemon that answered no_handler', () async {
      var attempts = 0;
      Future<Map<String, dynamic>> fakeCall(
          String _, String __, Map<String, dynamic> ___) async {
        attempts += 1;
        throw const RpcException('no_handler');
      }

      await fetchFileMentions(
          projectPath: '/proj', machineId: 'old', call: fakeCall);
      await fetchFileMentions(
          projectPath: '/proj', machineId: 'old', call: fakeCall);
      await fetchFileMentions(
          projectPath: '/other', machineId: 'old', call: fakeCall);

      // One attempt total: later mentions skip straight to the DB rather than
      // burning the server's 3s no-handler grace window again.
      expect(attempts, 1);
    });

    test('keeps retrying after a transient timeout', () async {
      var attempts = 0;
      Future<Map<String, dynamic>> fakeCall(
          String _, String __, Map<String, dynamic> ___) async {
        attempts += 1;
        throw const RpcException('timeout');
      }

      await fetchFileMentions(
          projectPath: '/proj', machineId: 'm-1', call: fakeCall);
      await fetchFileMentions(
          projectPath: '/proj', machineId: 'm-1', call: fakeCall);

      expect(attempts, 2);
    });
  });
}
