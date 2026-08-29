// Spec for the slash-command / skill source selection: live daemon index
// (`scan-commands`) first, the CLI-synced DB copy as fallback.
//
// Tests use an injected `RpcCaller` fake — no live WebSocket needed. The REST
// fallback is the real `apiGetSlashCommands`, which swallows its own errors and
// returns an empty list without a signed-in session, so "fell back to REST"
// reads here as "returned empty via SlashCommandsSource.rest".

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/fetch_slash_commands.dart';
import 'package:vicoa/custom_code/actions/rpc_command_index.dart';
import 'package:vicoa/custom_code/actions/ws_client.dart';

const _index = {
  'commands': [
    {'name': 'review', 'description': 'Review', 'kind': 'skill', 'insert': r'$review'},
    {'name': 'gstack:ship', 'description': 'Ship', 'kind': 'command'},
  ],
  'command_count': 2,
  'hash': 'abc123',
  'scanned_at': 0,
};

void main() {
  setUp(resetCommandIndexSupport);

  group('rpcScanCommands', () {
    test('parses a full index, carrying kind and insert', () async {
      Future<Map<String, dynamic>> fakeCall(
        String machineId,
        String method,
        Map<String, dynamic> params,
      ) async {
        expect(machineId, 'm-1');
        expect(method, 'scan-commands');
        expect(params['agent_type'], 'claude');
        expect(params['cwd'], '/proj');
        return Map<String, dynamic>.from(_index);
      }

      final result = await rpcScanCommands(
        call: fakeCall,
        machineId: 'm-1',
        agentType: 'claude',
        cwd: '/proj',
      );

      expect(result.unchanged, isFalse);
      expect(result.commands!.map((c) => c.command), ['/review', '/gstack:ship']);
      expect(result.commands!.first.isSkill, isTrue);
      expect(result.commands!.first.insert, r'$review');
      expect(result.commands![1].kind, 'command');
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

      final result = await rpcScanCommands(
        call: fakeCall,
        machineId: 'm-1',
        agentType: 'claude',
        knownHash: 'abc123',
      );

      // Null commands means "keep what you have" — the caller must not wipe its
      // cache to an empty list.
      expect(result.unchanged, isTrue);
      expect(result.commands, isNull);
    });

    test('omits cwd when the caller has none', () async {
      Future<Map<String, dynamic>> fakeCall(
        String _,
        String __,
        Map<String, dynamic> params,
      ) async {
        expect(params.containsKey('cwd'), isFalse);
        return Map<String, dynamic>.from(_index);
      }

      await rpcScanCommands(call: fakeCall, machineId: 'm-1', agentType: 'codex');
    });
  });

  group('fetchSlashCommands', () {
    test('prefers the live daemon index when a machine is known', () async {
      Future<Map<String, dynamic>> fakeCall(
              String _, String __, Map<String, dynamic> ___) async =>
          Map<String, dynamic>.from(_index);

      final result = await fetchSlashCommands(
          agentType: 'claude', machineId: 'm-1', call: fakeCall);

      expect(result.source, SlashCommandsSource.rpc);
      expect(result.commands!.map((c) => c.command), ['/review', '/gstack:ship']);
    });

    test('skips the RPC entirely when the session has no machine', () async {
      var called = false;
      Future<Map<String, dynamic>> fakeCall(
          String _, String __, Map<String, dynamic> ___) async {
        called = true;
        return Map<String, dynamic>.from(_index);
      }

      final result =
          await fetchSlashCommands(agentType: 'claude', call: fakeCall);

      expect(called, isFalse);
      expect(result.source, SlashCommandsSource.rest);
    });

    test('falls back to the DB copy when the daemon is unreachable', () async {
      Future<Map<String, dynamic>> fakeCall(
              String _, String __, Map<String, dynamic> ___) async =>
          throw const RpcException('target_disconnected');

      final result = await fetchSlashCommands(
          agentType: 'claude', machineId: 'm-1', call: fakeCall);

      expect(result.source, SlashCommandsSource.rest);
    });

    test('falls back to the DB copy on any daemon error (empty is valid)',
        () async {
      // Unlike scan-files there are no authoritative disk codes — an empty or
      // errored reply just routes to the DB instead.
      Future<Map<String, dynamic>> fakeCall(
              String _, String __, Map<String, dynamic> ___) async =>
          {'error': 'invalid_agent_type'};

      final result = await fetchSlashCommands(
          agentType: '', machineId: 'm-1', call: fakeCall);

      expect(result.source, SlashCommandsSource.rest);
    });

    test('stops retrying a daemon that answered no_handler', () async {
      var attempts = 0;
      Future<Map<String, dynamic>> fakeCall(
          String _, String __, Map<String, dynamic> ___) async {
        attempts += 1;
        throw const RpcException('no_handler');
      }

      await fetchSlashCommands(
          agentType: 'claude', machineId: 'old', call: fakeCall);
      await fetchSlashCommands(
          agentType: 'codex', machineId: 'old', call: fakeCall);

      // One attempt total: later opens skip straight to the DB rather than
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

      await fetchSlashCommands(
          agentType: 'claude', machineId: 'm-1', call: fakeCall);
      await fetchSlashCommands(
          agentType: 'claude', machineId: 'm-1', call: fakeCall);

      expect(attempts, 2);
    });
  });
}
