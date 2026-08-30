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
