import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/backend/agent_catalog.dart';
import 'package:vicoa/components/agent_type_icon/agent_type_icon_widget.dart';

void main() {
  group('pi / omp catalog entries', () {
    test('both agents are in the fallback catalog', () {
      final catalog = agentCatalogFallback();
      expect(catalog.agentById('omp')?.label, 'Oh My Pi');
      expect(catalog.agentById('pi')?.label, 'Pi');
    });

    test('omp offers the three approval modes; pi offers none', () {
      // omp maps these onto `--approval-mode always-ask|write|yolo`. Pi has no
      // approval flag at all, so showing it a mode picker would be a lie.
      final catalog = agentCatalogFallback();
      expect(
        catalog.agentById('omp')!.permissionModes.map((m) => m.id).toList(),
        <String>['default', 'acceptEdits', 'bypassPermissions'],
      );
      // `permissionModes` is non-nullable here (an absent block parses to an
      // empty list), so "no modes" means empty, not null.
      expect(catalog.agentById('pi')!.permissionModes, isEmpty);
    });

    test('both default to the "let the agent choose" model sentinel', () {
      // The real per-machine list arrives live from get_available_models.
      final catalog = agentCatalogFallback();
      expect(SessionConfig.defaultsFor(catalog, 'omp').model, 'default');
      expect(SessionConfig.defaultsFor(catalog, 'pi').model, 'default');
    });

    test('both expose a thinking-effort picker defaulting to medium', () {
      final catalog = agentCatalogFallback();
      for (final id in <String>['omp', 'pi']) {
        expect(SessionConfig.defaultsFor(catalog, id).thinkingEffort, 'medium',
            reason: id);
      }
    });
  });

  group('SessionConfig.toSpawnMetadata for the pi family', () {
    test('sends model, thinking effort and permission mode', () {
      final metadata = SessionConfig(
        agent: 'omp',
        model: 'anthropic/claude-haiku-4-5',
        thinkingEffort: 'high',
        permissionMode: 'acceptEdits',
      ).toSpawnMetadata();
      expect(metadata, {
        'model': 'anthropic/claude-haiku-4-5',
        'thinking_effort': 'high',
        'permission_mode': 'acceptEdits',
      });
    });

    test("does not dual-write claude's legacy enable_thinking flag", () {
      final metadata =
          SessionConfig(agent: 'pi', thinkingEffort: 'off').toSpawnMetadata();
      expect(metadata.containsKey('enable_thinking'), isFalse);
    });

    test('the defer sentinel sends no model so the agent keeps its own', () {
      expect(SessionConfig(agent: 'omp', model: 'default').toSpawnMetadata(), {});
      expect(SessionConfig(agent: 'pi', model: 'auto').toSpawnMetadata(), {});
    });
  });

  group('the "pi" substring hazard', () {
    // Icons resolve with `name.contains(match)` over an ordered list, and
    // 'copilot' contains 'pi'. A bare 'pi' entry placed before Copilot would
    // silently swallow it.
    test('Copilot and the Pi family each keep their own mark', () {
      expect(agentTypeHasLogo('Copilot'), isTrue);
      expect(agentTypeHasLogo('Oh My Pi'), isTrue);
      expect(agentTypeHasLogo('Pi'), isTrue);
    });
  });
}
