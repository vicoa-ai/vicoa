// Unit tests for the SessionConfig hydration helper used by the chat-
// header gear-icon pill.
//
// Plan: plans/session-config-storage.md §7.1 — mobile reads
// `instanceData['session_config']` as canonical, falls back to live
// pill state (already updated by the existing message-history scan in
// `_hydrateControlSettingsFromMessages`) when null. Does NOT reconcile
// against the catalog default — missing fields stay null so the pill
// renders nothing rather than synthesizing a default the session may
// not actually be running with.
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/backend/agent_catalog.dart';

void main() {
  final catalog = agentCatalogFallback();

  group('initialPillConfigFor', () {
    test('uses session_config from instanceData when present', () {
      final instanceData = <String, dynamic>{
        'session_config': <String, dynamic>{
          'agent': 'claude',
          'model': 'claude-sonnet-4-6',
          'thinking_effort': 'low',
          'permission_mode': 'acceptEdits',
        },
      };
      final config = initialPillConfigFor(
        instanceData: instanceData,
        catalog: catalog,
        fallbackAgentId: 'claude',
        livePermissionMode: 'plan',
        liveOpencodeMode: null,
      );
      expect(config.agent, 'claude');
      expect(config.model, 'claude-sonnet-4-6');
      expect(config.thinkingEffort, 'low');
      // Stored permission_mode wins over the live message-scan value
      // (the row is authoritative when populated).
      expect(config.permissionMode, 'acceptEdits');
    });

    test('falls back to live state when session_config is absent', () {
      final instanceData = <String, dynamic>{
        'name': 'legacy-session',
        // no session_config key — simulates a legacy row spawned before the
        // backend started persisting the column.
      };
      final config = initialPillConfigFor(
        instanceData: instanceData,
        catalog: catalog,
        fallbackAgentId: 'claude',
        livePermissionMode: 'plan',
        liveOpencodeMode: null,
      );
      expect(config.agent, 'claude');
      expect(config.permissionMode, 'plan');
      // Model + effort stay null. We don't synthesize a catalog default
      // here — the pill renders nothing for these rows rather than
      // claiming a value the session may not actually be running.
      expect(config.model, isNull);
      expect(config.thinkingEffort, isNull);
    });

    test('stored permission_mode null falls through to live state', () {
      // The wrapper PATCHed model + effort but the permission-mode jsonl
      // event hasn't landed yet. The pill must NOT lie via the catalog
      // default — show whatever the message-scan / TUI toggle state has.
      final instanceData = <String, dynamic>{
        'session_config': <String, dynamic>{
          'agent': 'claude',
          'model': 'claude-opus-4-7',
          'thinking_effort': 'xhigh',
        },
      };
      final config = initialPillConfigFor(
        instanceData: instanceData,
        catalog: catalog,
        fallbackAgentId: 'claude',
        livePermissionMode: 'plan',
        liveOpencodeMode: null,
      );
      expect(config.model, 'claude-opus-4-7');
      expect(config.thinkingEffort, 'xhigh');
      expect(config.permissionMode, 'plan'); // from live state, not catalog default
    });

    test('falls back when instanceData itself is null', () {
      final config = initialPillConfigFor(
        instanceData: null,
        catalog: catalog,
        fallbackAgentId: 'opencode',
        livePermissionMode: null,
        liveOpencodeMode: 'plan',
      );
      expect(config.agent, 'opencode');
      expect(config.opencodeMode, 'plan');
    });

    test('stale model id is preserved (not silently replaced)', () {
      // A model id no longer in the catalog (e.g., post-retirement) stays
      // as-is — the catalog's "never delete a model entry" rule means
      // labels still resolve, and silently swapping to a different model
      // would be misleading (the session is actually running on the
      // retired id, whatever it is).
      final instanceData = <String, dynamic>{
        'session_config': <String, dynamic>{
          'agent': 'claude',
          'model': 'definitely-not-a-real-model-id',
        },
      };
      final config = initialPillConfigFor(
        instanceData: instanceData,
        catalog: catalog,
        fallbackAgentId: 'claude',
        livePermissionMode: null,
        liveOpencodeMode: null,
      );
      expect(config.model, 'definitely-not-a-real-model-id');
    });
  });

  group('SessionConfig.defaultsFor', () {
    test('claude default permission_mode is "default" (not "acceptEdits")', () {
      // Catalog flipped is_default from acceptEdits → default so newly-
      // spawned sessions don't surprise users with auto-accept-edits.
      final config = SessionConfig.defaultsFor(catalog, 'claude');
      expect(config.permissionMode, 'default');
    });
  });
}
