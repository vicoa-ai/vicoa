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
      final metadata = SessionConfig(agent: 'cursor', model: 'composer-2.5', permissionMode: 'plan').toSpawnMetadata(prompt: 'fix it');
      expect(metadata, {'prompt': 'fix it', 'model': 'composer-2.5', 'permission_mode': 'plan'});
    });

    test('generic ACP agents keep the agent\'s own model for the auto/default sentinel', () {
      // Same rule as pi/opencode: the sentinel means "don't force a model", so
      // nothing is sent (the wrapper would skip it anyway).
      expect(SessionConfig(agent: 'cursor', model: 'auto', permissionMode: 'plan').toSpawnMetadata(), {'permission_mode': 'plan'});
      expect(SessionConfig(agent: 'hermes', model: 'default').toSpawnMetadata(), <String, dynamic>{});
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

    test('synthesizes an entry for a cached agent the static catalog cannot describe', () {
      // A catalog-added agent (Qwen Code) that was probed or ran once: the
      // cache has its models and modes, the daemon's agent_labels its name.
      // Before this the sheet had no model/mode picker at all for it.
      final base = agentCatalogFallback();
      final merged = catalogWithCachedModels(
        base,
        {
          'qwen': [
            {'id': 'qwen3-coder-plus', 'label': 'Qwen3 Coder Plus'},
            {'id': 'qwen3-max', 'label': 'Qwen3 Max'},
          ],
        },
        cachedModes: {
          'qwen': [
            {'id': 'default', 'label': 'Default'},
            {'id': 'plan', 'label': 'Plan'},
          ],
        },
        agentLabels: {'qwen': 'Qwen Code'},
      );
      expect(merged.agents.length, base.agents.length + 1);
      final qwen = merged.agents.last;
      expect(qwen.id, 'qwen');
      expect(qwen.label, 'Qwen Code');
      // `default` sentinel first (never sent as a model), then the real list.
      expect(qwen.models!.map((m) => m.id).toList(), ['default', 'qwen3-coder-plus', 'qwen3-max']);
      expect(qwen.models!.first.isDefault, isTrue);
      // Cached modes become permissionModes — the field the generic ACP spawn
      // path forwards — with the agent's first mode as its default.
      expect(qwen.permissionModes.map((e) => e.id).toList(), ['default', 'plan']);
      expect(qwen.permissionModes.first.isDefault, isTrue);
      expect(qwen.permissionModes.last.isDefault, isFalse);
      expect(qwen.thinkingEfforts, isEmpty);
      expect(qwen.reasoningEfforts, isEmpty);
      expect(qwen.modes, isEmpty);
      // Static agents keep their order and content.
      expect(merged.agents.sublist(0, base.agents.length).map((a) => a.id).toList(),
          base.agents.map((a) => a.id).toList());

      // Drives the config lifecycle end to end.
      final defaults = SessionConfig.defaultsFor(merged, 'qwen');
      expect(defaults.model, 'default');
      expect(defaults.permissionMode, 'default');
      // The sentinel is never sent as a model; a real pick + mode are.
      expect(defaults.toSpawnMetadata(), {'permission_mode': 'default'});
      expect(
        SessionConfig(agent: 'qwen', model: 'qwen3-max', permissionMode: 'plan').toSpawnMetadata(),
        {'model': 'qwen3-max', 'permission_mode': 'plan'},
      );
      // A config saved before the cache existed reconciles to the defaults.
      final reconciled = SessionConfig(agent: 'qwen', permissionMode: 'yolo').reconcileAgainst(merged);
      expect(reconciled.model, 'default');
      expect(reconciled.permissionMode, 'default');
    });

    test('synthesized entry falls back to a derived label and skips modes when none are cached', () {
      final merged = catalogWithCachedModels(agentCatalogFallback(), {
        'kimi-work': [
          {'id': 'default', 'label': 'Default'},
          {'id': 'moonshot-ai/kimi-k2.6', 'label': 'Kimi K2.6'},
        ],
      });
      final kimi = merged.agentById('kimi-work')!;
      expect(kimi.label, 'Kimi Work');
      // A cached `default` is not duplicated behind the sentinel.
      expect(kimi.models!.map((m) => m.id).toList(), ['default', 'moonshot-ai/kimi-k2.6']);
      expect(kimi.permissionModes, isEmpty);
    });

    test('cached modes fill in a static agent with no curated mode list, but not one that does', () {
      final base = agentCatalogFallback();
      final merged = catalogWithCachedModels(
        base,
        {
          'copilot': [
            {'id': 'gpt-5-mini', 'label': 'GPT-5 mini'},
          ],
        },
        cachedModes: {
          'copilot': [
            {'id': 'agent', 'label': 'Agent'},
            {'id': 'plan', 'label': 'Plan'},
          ],
          'cursor': [
            {'id': 'weird', 'label': 'Weird'},
          ],
          // Modes without models still land.
          'hermes': [
            {'id': 'default', 'label': 'Default'},
          ],
        },
      );
      expect(merged.agentById('copilot')!.permissionModes.map((e) => e.id).toList(), ['agent', 'plan']);
      expect(merged.agentById('copilot')!.models!.map((m) => m.id).toList(), ['default', 'gpt-5-mini']);
      expect(merged.agentById('cursor')!.permissionModes.map((e) => e.id).toList(),
          base.agentById('cursor')!.permissionModes.map((e) => e.id).toList());
      expect(merged.agentById('hermes')!.permissionModes.map((e) => e.id).toList(), ['default']);
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

  group('customAgentLabel', () {
    // Mirrors apps/web/lib/agent-catalog.test.ts so a user-defined provider
    // reads the same on both platforms.
    test('makes a readable name out of a provider id', () {
      expect(customAgentLabel('kimi-work'), 'Kimi Work');
      expect(customAgentLabel('goose'), 'Goose');
      expect(customAgentLabel('gemini-nightly-2'), 'Gemini Nightly 2');
    });

    test('survives ids with stray separators', () {
      expect(customAgentLabel('a--b'), 'A B');
      expect(customAgentLabel(''), '');
    });
  });

  group('supportsSteer', () {
    // Mirrors `supports_steer` in backend/src/protocol/agent_catalog.py: the
    // agents with a mid-turn primitive (Codex turn/steer, Claude Code streaming
    // stdin, pi/omp steer RPC). ACP agents and OpenCode only queue.
    test('fallback flags exactly the agents with a mid-turn primitive', () {
      final catalog = agentCatalogFallback();
      for (final id in ['claude', 'codex', 'omp', 'pi']) {
        expect(catalog.agentById(id)!.supportsSteer, isTrue, reason: id);
      }
      for (final id in ['opencode', 'antigravity', 'cursor', 'gemini', 'copilot', 'kimi', 'hermes']) {
        expect(catalog.agentById(id)!.supportsSteer, isFalse, reason: id);
      }
    });

    test('fromJson reads the flag and treats absent or non-bool as false', () {
      CatalogAgent parse(Map<String, dynamic> extra) =>
          CatalogAgent.fromJson({'id': 'x', 'label': 'X', 'models': null, ...extra});
      expect(parse({'supports_steer': true}).supportsSteer, isTrue);
      expect(parse({'supports_steer': false}).supportsSteer, isFalse);
      expect(parse({}).supportsSteer, isFalse);
      expect(parse({'supports_steer': 'yes'}).supportsSteer, isFalse);
    });

    test('survives the cached-models merge', () {
      final merged = catalogWithCachedModels(
        agentCatalogFallback(),
        {
          'claude': [
            {'id': 'claude-sonnet-5', 'label': 'Sonnet 5'},
          ],
          'qwen': [
            {'id': 'qwen3-coder', 'label': 'Qwen3 Coder'},
          ],
        },
        cachedModes: {
          'copilot': [
            {'id': 'agent', 'label': 'Agent'},
          ],
        },
      );
      // Cached models replaced the list — the capability rides along.
      expect(merged.agentById('claude')!.supportsSteer, isTrue);
      // Only cached modes were merged onto this static entry — still false.
      expect(merged.agentById('copilot')!.supportsSteer, isFalse);
      // A synthesized entry for an agent the catalog cannot describe never
      // claims a capability it can't verify.
      expect(merged.agentById('qwen')!.supportsSteer, isFalse);
    });
  });
}
