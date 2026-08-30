import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/backend/agent_catalog.dart';

void main() {
  group('agent catalog fallback', () {
    test('includes the generic ACP agents', () {
      final catalog = agentCatalogFallback();
      final ids = catalog.agents.map((a) => a.id).toList();
      expect(
        ids,
        containsAll(<String>['claude', 'codex', 'opencode', 'cursor', 'gemini', 'copilot', 'kimi', 'hermes']),
      );
    });

    test('ACP agents offer a static model picker with a default', () {
      final catalog = agentCatalogFallback();
      // A default model list is shown at new-session (the live full list is
      // sourced in the gear). Every ACP agent has at least a default.
      for (final id in ['cursor', 'gemini', 'copilot', 'kimi', 'hermes']) {
        final models = catalog.agentById(id)!.models;
        expect(models, isNotNull, reason: id);
        expect(models!, isNotEmpty, reason: id);
        expect(SessionConfig.defaultsFor(catalog, id).model, isNotNull, reason: id);
      }
      // Gemini defaults to 'auto' (defer to the agent) and keeps its mode default.
      final gemini = SessionConfig.defaultsFor(catalog, 'gemini');
      expect(gemini.model, 'auto');
      expect(gemini.permissionMode, 'default');
    });
  });

  group('SessionConfig.toSpawnMetadata', () {
    test('generic ACP agents pass model and permission_mode through', () {
      final metadata = SessionConfig(agent: 'cursor', model: 'auto', permissionMode: 'plan').toSpawnMetadata(prompt: 'fix it');
      expect(metadata, {'prompt': 'fix it', 'model': 'auto', 'permission_mode': 'plan'});
    });

    test('hermes without mode sends only the model', () {
      final metadata = SessionConfig(agent: 'hermes', model: 'default').toSpawnMetadata();
      expect(metadata, {'model': 'default'});
    });

    test('claude shape is unchanged', () {
      final metadata = SessionConfig(agent: 'claude', model: 'claude-sonnet-4-6', thinkingEffort: 'high', permissionMode: 'default').toSpawnMetadata();
      expect(metadata, {
        'model': 'claude-sonnet-4-6',
        'thinking_effort': 'high',
        'enable_thinking': true,
        'permission_mode': 'default',
      });
    });

    test('opencode "default" keeps the agent\'s own model (no model sent)', () {
      final metadata = SessionConfig(agent: 'opencode', model: 'default', opencodeMode: 'build').toSpawnMetadata();
      expect(metadata, {'agent_mode': 'build'});
    });

    test('opencode explicit model is sent at spawn', () {
      final metadata = SessionConfig(agent: 'opencode', model: 'opencode/big-pickle', opencodeMode: 'plan').toSpawnMetadata();
      expect(metadata, {'agent_mode': 'plan', 'model': 'opencode/big-pickle'});
    });
  });

  group('catalogWithCachedModels', () {
    test("replaces an agent's models with the cached list (keeping the defer sentinel), others untouched", () {
      final base = agentCatalogFallback();
      final merged = catalogWithCachedModels(base, {
        'cursor': [
          {'id': 'composer-2.5[fast=true]', 'label': 'composer-2.5'},
          {'id': 'gpt-5.4[context=272k]', 'label': 'gpt-5.4'},
        ],
      });
      final cursor = merged.agentById('cursor')!;
      // The is_default catalog sentinel (`auto`) stays at the top so a stored
      // default remains selectable once the real models load.
      expect(cursor.models!.map((m) => m.id).toList(),
          ['auto', 'composer-2.5[fast=true]', 'gpt-5.4[context=272k]']);
      expect(cursor.models!.firstWhere((m) => m.id == 'auto').isDefault, isTrue);
      // Modes/permission_modes survive the merge.
      expect(cursor.permissionModes.map((e) => e.id).toList(),
          base.agentById('cursor')!.permissionModes.map((e) => e.id).toList());
      // An agent without a cached entry keeps its catalog models.
      expect(merged.agentById('claude')!.models!.map((m) => m.id).toList(),
          base.agentById('claude')!.models!.map((m) => m.id).toList());
    });

    test('does not duplicate the sentinel when the cached list already includes it', () {
      final merged = catalogWithCachedModels(agentCatalogFallback(), {
        'cursor': [
          {'id': 'auto', 'label': 'Default'},
          {'id': 'composer-2.5', 'label': 'composer-2.5'},
        ],
      });
      expect(merged.agentById('cursor')!.models!.map((m) => m.id).toList(), ['auto', 'composer-2.5']);
    });

    test('keeps per-model capability metadata for ids the catalog knows', () {
      // Headless Claude reports its real model list (catalog + the machine's
      // custom slugs). The cached entries carry only {id, label}; dropping the
      // catalog's per-model arrays would hide the `auto` permission mode and
      // the Opus xhigh thinking default from the new-session sheet.
      final merged = catalogWithCachedModels(agentCatalogFallback(), {
        'claude': [
          {'id': 'claude-sonnet-5', 'label': 'Sonnet 5'},
          {'id': 'claude-opus-4-8', 'label': 'Opus 4.8'},
          {'id': 'my-org/custom-sonnet', 'label': 'my-org/custom-sonnet'},
        ],
      });
      final models = merged.agentById('claude')!.models!;
      expect(models.map((m) => m.id).toList(), ['claude-sonnet-5', 'claude-opus-4-8', 'my-org/custom-sonnet']);
      final sonnet = models.firstWhere((m) => m.id == 'claude-sonnet-5');
      expect(sonnet.permissionModes, ['auto']);
      expect(sonnet.isDefault, isTrue);
      expect(models.firstWhere((m) => m.id == 'claude-opus-4-8').defaultThinkingEffort, 'xhigh');
      // A slug the catalog has never heard of gets the common set only.
      expect(models.firstWhere((m) => m.id == 'my-org/custom-sonnet').permissionModes, isNull);
    });

    test('empty cache returns the base catalog unchanged', () {
      final base = agentCatalogFallback();
      expect(identical(catalogWithCachedModels(base, const {}), base), isTrue);
    });

    test('an empty cached list for an agent keeps its catalog defaults', () {
      final base = agentCatalogFallback();
      final merged = catalogWithCachedModels(base, {'cursor': const []});
      expect(merged.agentById('cursor')!.models!.map((m) => m.id).toList(),
          base.agentById('cursor')!.models!.map((m) => m.id).toList());
    });
  });

  group('opencode model picker', () {
    test('defaults to the "default" sentinel (keep own model)', () {
      final catalog = agentCatalogFallback();
      final oc = catalog.agentById('opencode')!;
      expect(oc.models, isNotNull);
      expect(oc.models!.map((m) => m.id), contains('default'));
      expect(SessionConfig.defaultsFor(catalog, 'opencode').model, 'default');
    });
  });
}
