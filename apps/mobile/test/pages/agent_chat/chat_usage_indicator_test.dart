import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/agent_chat/components/chat_usage_indicator.dart';

void main() {
  group('SessionUsage.fromInstanceData', () {
    test('returns null when there is no usage blob', () {
      expect(SessionUsage.fromInstanceData(null), isNull);
      expect(SessionUsage.fromInstanceData({}), isNull);
      expect(SessionUsage.fromInstanceData({'instance_metadata': {}}), isNull);
      expect(
          SessionUsage.fromInstanceData(
              {'instance_metadata': {'usage': {}}}),
          isNull);
    });

    test('parses context and computes clamped pct', () {
      final u = SessionUsage.fromInstanceData({
        'instance_metadata': {
          'usage': {
            'context': {'used_tokens': 50000, 'max_tokens': 200000, 'cost_usd': 0.42},
          },
        },
      })!;
      expect(u.usedTokens, 50000);
      expect(u.maxTokens, 200000);
      expect(u.costUsd, 0.42);
      expect(u.contextPct, closeTo(25, 0.001));
      expect(u.hasContext, isTrue);
    });

    test('contextPct is null when max is unknown', () {
      final u = SessionUsage.fromInstanceData({
        'instance_metadata': {
          'usage': {
            'context': {'used_tokens': 50000, 'max_tokens': null, 'cost_usd': null},
          },
        },
      })!;
      expect(u.contextPct, isNull);
      expect(u.hasAnything, isTrue);
    });

    test('parses windows, tightest, reset time and credits', () {
      final u = SessionUsage.fromInstanceData({
        'instance_metadata': {
          'usage': {
            'limits': {
              'windows': [
                {'id': 'session', 'label': 'Session', 'used_pct': 63.0, 'resets_at': '2026-07-16T21:00:00+00:00'},
                {'id': 'weekly', 'label': 'Weekly', 'used_pct': 82.0, 'resets_at': null},
              ],
              'credits': {'unit': 'usd', 'remaining': 4.10},
            },
          },
        },
      })!;
      expect(u.windows, hasLength(2));
      expect(u.windows.first.label, 'Session');
      expect(u.windows.first.resetsAt, DateTime.parse('2026-07-16T21:00:00+00:00'));
      expect(u.windows[1].resetsAt, isNull);
      expect(u.tightestWindowPct, 82.0);
      expect(u.creditsRemaining, 4.10);
      expect(u.hasContext, isFalse);
      expect(u.hasAnything, isTrue);
    });

    test('skips malformed windows without a percentage', () {
      final u = SessionUsage.fromInstanceData({
        'instance_metadata': {
          'usage': {
            'limits': {
              'windows': [
                {'id': 'session', 'label': 'Session'},
                {'id': 'weekly', 'label': 'Weekly', 'used_pct': 40},
              ],
            },
          },
        },
      })!;
      expect(u.windows, hasLength(1));
      expect(u.windows.single.id, 'weekly');
      expect(u.windows.single.usedPct, 40.0);
    });

    test('coerces a string credit balance defensively', () {
      final u = SessionUsage.fromInstanceData({
        'instance_metadata': {
          'usage': {
            'limits': {
              'windows': [
                {'id': 'session', 'label': 'Session', 'used_pct': 10},
              ],
              'credits': {'unit': 'usd', 'remaining': '4.10'},
            },
          },
        },
      })!;
      expect(u.creditsRemaining, 4.10);
    });
  });

  group('fetchProviderUsageWindows', () {
    final windows = <String, dynamic>{
      'limits': {
        'windows': [
          {'id': 'session', 'label': 'Session', 'used_pct': 12.5, 'resets_at': null},
        ],
      },
    };

    test('providerHasUsageFetcher matches the daemon registry exactly', () {
      expect(['claude', 'codex', 'copilot'].map(providerHasUsageFetcher), everyElement(isTrue));
      expect(['gemini', 'cursor', 'opencode', 'qwen', '', null].map(providerHasUsageFetcher), everyElement(isFalse));
    });

    test('calls fetch-provider-usage with the provider and returns the windows', () async {
      final calls = <List<dynamic>>[];
      Future<Map<String, dynamic>> call(String m, String method, Map<String, dynamic> params) async {
        calls.add([m, method, params]);
        return windows;
      }

      final result = await fetchProviderUsageWindows(call: call, machineId: 'm1', provider: 'codex');
      expect(result!.single.id, 'session');
      expect(calls, [
        ['m1', 'fetch-provider-usage', {'provider': 'codex'}],
      ]);
    });

    test('never calls the daemon for a provider without a fetcher', () async {
      var called = false;
      Future<Map<String, dynamic>> call(String m, String method, Map<String, dynamic> params) async {
        called = true;
        return windows;
      }

      expect(await fetchProviderUsageWindows(call: call, machineId: 'm1', provider: 'gemini'), isNull);
      expect(called, isFalse);
    });

    test('an error payload resolves to null', () async {
      Future<Map<String, dynamic>> call(String m, String method, Map<String, dynamic> params) async =>
          {'error': 'no_oauth_token'};
      expect(await fetchProviderUsageWindows(call: call, machineId: 'm1', provider: 'copilot'), isNull);
    });

    test('claude falls back to the legacy fetch-claude-usage on an old daemon', () async {
      final methods = <String>[];
      Future<Map<String, dynamic>> call(String m, String method, Map<String, dynamic> params) async {
        methods.add(method);
        if (method == 'fetch-provider-usage') throw Exception('rpc call failed: no_handler');
        return windows;
      }

      final result = await fetchProviderUsageWindows(call: call, machineId: 'm1', provider: 'claude');
      expect(result!.single.id, 'session');
      expect(methods, ['fetch-provider-usage', 'fetch-claude-usage']);
      // The pre-registry entry point rides the same path.
      expect((await fetchClaudeUsageWindows(call: call, machineId: 'm1'))!.single.id, 'session');
    });

    test('other providers on an old daemon hide silently; transport errors too', () async {
      var calls = 0;
      Future<Map<String, dynamic>> call(String m, String method, Map<String, dynamic> params) async {
        calls++;
        throw Exception('rpc call failed: no_handler');
      }

      expect(await fetchProviderUsageWindows(call: call, machineId: 'm1', provider: 'codex'), isNull);
      expect(calls, 1);
      Future<Map<String, dynamic>> offline(String m, String method, Map<String, dynamic> params) async =>
          throw Exception('rpc call failed: target_disconnected');
      expect(await fetchProviderUsageWindows(call: offline, machineId: 'm1', provider: 'claude'), isNull);
    });
  });

  group('formatUsageTokens', () {
    test('abbreviates thousands and millions', () {
      expect(formatUsageTokens(512), '512');
      expect(formatUsageTokens(48213), '48k');
      expect(formatUsageTokens(1000000), '1m');
      expect(formatUsageTokens(1500000), '1.5m');
    });
  });

  group('formatUsageCost', () {
    test('uses 4 decimals under a cent, else 2', () {
      expect(formatUsageCost(0.0004), '\$0.0004');
      expect(formatUsageCost(0.42), '\$0.42');
    });
  });
}
