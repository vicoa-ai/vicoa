import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vicoa/backend/agent_catalog.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/new_session/components/agent_config_sheet.dart';

/// Two-agent catalog: one installed, one not — enough to exercise the
/// "show all, disable uninstalled" picker behavior.
AgentCatalog _catalog() => AgentCatalog.fromJson({
      'version': 'test',
      'agents': [
        {
          'id': 'claude',
          'label': 'Claude Code',
          'models': [
            {'id': 'm1', 'label': 'Model One', 'is_default': true},
          ],
        },
        {
          'id': 'cursor',
          'label': 'Cursor',
          'models': [
            {'id': 'auto', 'label': 'Auto', 'is_default': true},
          ],
        },
      ],
    });

Future<void> _openSheet(
  WidgetTester tester, {
  required Map<String, bool>? availableAgents,
  required SessionConfig initial,
}) async {
  final catalog = _catalog();
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => showAgentConfigSheet(
              context: context,
              catalog: catalog,
              initial: initial,
              availableAgents: availableAgents,
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  group('agent picker availability', () {
    testWidgets('shows every agent, even ones the machine lacks', (tester) async {
      await _openSheet(
        tester,
        availableAgents: const {'claude': true, 'cursor': false},
        initial: SessionConfig(agent: 'claude'),
      );

      // Open the Agent dropdown (the trigger shows the current agent label).
      await tester.tap(find.text('Claude Code').last);
      await tester.pumpAndSettle();

      // Both agents render in the menu — the uninstalled one is NOT hidden.
      // Non-GA agents carry a "(Beta)" suffix in the picker.
      expect(find.text('Cursor (Beta)'), findsWidgets);
      expect(find.text('Claude Code'), findsWidgets);
    });

    testWidgets('tapping an uninstalled agent shows a notice and does not switch',
        (tester) async {
      await _openSheet(
        tester,
        availableAgents: const {'claude': true, 'cursor': false},
        initial: SessionConfig(agent: 'claude'),
      );

      await tester.tap(find.text('Claude Code').last);
      await tester.pumpAndSettle();

      // Tap the uninstalled agent in the menu.
      await tester.tap(find.text('Cursor (Beta)'));
      await tester.pumpAndSettle();

      // The menu closed, an explanation appears, and the daemon hint is shown.
      expect(find.widgetWithText(PopupMenuItem<String>, 'Cursor (Beta)'), findsNothing);
      expect(find.textContaining('is not installed'), findsOneWidget);
      expect(find.textContaining('vicoa daemon'), findsOneWidget);
      // Selection didn't change — the trigger still shows Claude Code.
      expect(find.text('Claude Code'), findsWidgets);
    });

    testWidgets('orders installed agents first, then not installed, each in catalog order',
        (tester) async {
      // Catalog order: claude, cursor, codex. claude uninstalled.
      final catalog = AgentCatalog.fromJson({
        'version': 'test',
        'agents': [
          {'id': 'claude', 'label': 'Claude Code'},
          {'id': 'cursor', 'label': 'Cursor'},
          {'id': 'codex', 'label': 'Codex'},
        ],
      });
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () => showAgentConfigSheet(
                  context: context,
                  catalog: catalog,
                  initial: SessionConfig(agent: 'cursor'),
                  availableAgents: const {'claude': false, 'cursor': true, 'codex': true},
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cursor (Beta)').last);
      await tester.pumpAndSettle();

      final values = tester
          .widgetList<PopupMenuItem<String>>(find.byType(PopupMenuItem<String>))
          .map((i) => i.value)
          .toList();
      // Installed (cursor, codex) in catalog order, then uninstalled (claude).
      expect(values, ['cursor', 'codex', 'claude']);
    });

    testWidgets('opens on a supported agent when the initial one is missing',
        (tester) async {
      await _openSheet(
        tester,
        availableAgents: const {'claude': false, 'cursor': true},
        initial: SessionConfig(agent: 'claude'),
      );

      // The trigger should reflect cursor (the supported agent), not claude.
      expect(find.text('Cursor (Beta)'), findsWidgets);
    });
  });

  group('opencode model', () {
    testWidgets('model dropdown is editable (not frozen)', (tester) async {
      final catalog = AgentCatalog.fromJson({
        'version': 'test',
        'agents': [
          {
            'id': 'opencode',
            'label': 'OpenCode',
            'models': [
              {'id': 'default', 'label': 'Default', 'is_default': true},
              {'id': 'opencode/big-pickle', 'label': 'Big Pickle'},
            ],
            'modes': [
              {'id': 'build', 'label': 'Build', 'is_default': true},
            ],
          },
        ],
      });
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () => showAgentConfigSheet(
                  context: context,
                  catalog: catalog,
                  initial: SessionConfig(agent: 'opencode', model: 'default', opencodeMode: 'build'),
                  hideAgentSelector: true,
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      // Open the Model dropdown — if it were frozen (IgnorePointer) this tap
      // would be a no-op and the other option wouldn't appear.
      await tester.tap(find.text('Default').last);
      await tester.pumpAndSettle();
      expect(find.text('Big Pickle'), findsWidgets);
    });
  });

  group('beta labelling', () {
    testWidgets('non-GA agents get a "(Beta)" suffix; claude/codex do not',
        (tester) async {
      final catalog = AgentCatalog.fromJson({
        'version': 'test',
        'agents': [
          {'id': 'claude', 'label': 'Claude Code'},
          {'id': 'codex', 'label': 'Codex'},
          {'id': 'gemini', 'label': 'Gemini'},
        ],
      });
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () => showAgentConfigSheet(
                  context: context,
                  catalog: catalog,
                  initial: SessionConfig(agent: 'claude'),
                  availableAgents: const {'claude': true, 'codex': true, 'gemini': true},
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Claude Code').last);
      await tester.pumpAndSettle();

      // Beta agent carries the suffix; GA agents render plain (and the bare
      // "Gemini" without the suffix must NOT appear).
      expect(find.text('Gemini (Beta)'), findsWidgets);
      expect(find.text('Gemini'), findsNothing);
      expect(find.text('Claude Code'), findsWidgets);
      expect(find.text('Codex'), findsWidgets);
      expect(find.text('Claude Code (Beta)'), findsNothing);
      expect(find.text('Codex (Beta)'), findsNothing);
    });
  });

  group('automation agent sheet', _automationSheetTests);
}

/// The automation editor's mode: the caller's saved agents at the top of the
/// Agent dropdown, and an [AgentPick] back instead of a bare config.
const _reviewer = {
  'id': 'p-reviewer',
  'name': 'Reviewer',
  'agent': 'claude',
  'config': {'agent': 'claude', 'model': 'm2'},
  'system_prompt': 'Review carefully.',
  'team_id': null,
};

AgentCatalog _twoModelCatalog() => AgentCatalog.fromJson({
      'version': 'test',
      'agents': [
        {
          'id': 'claude',
          'label': 'Claude Code',
          'models': [
            {'id': 'm1', 'label': 'Model One', 'is_default': true},
            {'id': 'm2', 'label': 'Model Two'},
          ],
        },
        {
          'id': 'codex',
          'label': 'Codex',
          'models': [
            {'id': 'c1', 'label': 'Codex One', 'is_default': true},
          ],
        },
      ],
    });

/// Opens the automation sheet and returns a getter for what it popped.
Future<AgentPick? Function()> _openAutomationSheet(
  WidgetTester tester, {
  required SessionConfig initial,
  String? initialAgentProfileId,
  List<dynamic> savedAgents = const [_reviewer],
  bool machineSupportsInstructions = true,
}) async {
  AgentPick? picked;
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              picked = await showAutomationAgentSheet(
                context: context,
                catalog: _twoModelCatalog(),
                initial: initial,
                savedAgents: savedAgents,
                initialAgentProfileId: initialAgentProfileId,
                machineSupportsInstructions: machineSupportsInstructions,
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return () => picked;
}

Future<void> _confirm(WidgetTester tester) async {
  await tester.tap(find.byIcon(Icons.check_rounded));
  await tester.pumpAndSettle();
}

void _automationSheetTests() {
  testWidgets('lists saved agents under "My agents", above the plain agents',
      (tester) async {
    await _openAutomationSheet(tester, initial: SessionConfig(agent: 'claude'));
    await tester.tap(find.text('Claude Code').last);
    await tester.pumpAndSettle();

    final values = tester
        .widgetList<PopupMenuItem<String>>(find.byType(PopupMenuItem<String>))
        .map((i) => i.value)
        .toList();
    expect(
        values, ['header:personal', 'profile:p-reviewer', 'claude', 'codex']);
    expect(find.text('My agents'), findsOneWidget);
  });

  testWidgets('picking a saved agent hides the model and returns its id',
      (tester) async {
    final result = await _openAutomationSheet(tester,
        initial: SessionConfig(agent: 'claude'));
    expect(find.text('Model'), findsOneWidget);

    await tester.tap(find.text('Claude Code').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Reviewer').last);
    await tester.pumpAndSettle();

    expect(find.text('Model'), findsNothing);
    await _confirm(tester);
    expect(result()!.agentProfileId, 'p-reviewer');
    expect(result()!.config.model, 'm2');
  });

  testWidgets('switching back to the same provider keeps the agent\'s settings',
      (tester) async {
    final result = await _openAutomationSheet(
      tester,
      initial: SessionConfig(agent: 'claude', model: 'm1'),
      initialAgentProfileId: 'p-reviewer',
    );
    expect(find.text('Model'), findsNothing);

    await tester.tap(find.text('Reviewer').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Claude Code').last);
    await tester.pumpAndSettle();

    expect(find.text('Model'), findsOneWidget);
    await _confirm(tester);
    expect(result()!.agentProfileId, isNull);
    expect(result()!.config.model, 'm2');
  });

  testWidgets('another provider starts from its defaults', (tester) async {
    final result = await _openAutomationSheet(
      tester,
      initial: SessionConfig(agent: 'claude'),
      initialAgentProfileId: 'p-reviewer',
    );
    await tester.tap(find.text('Reviewer').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Codex').last);
    await tester.pumpAndSettle();

    await _confirm(tester);
    expect(result()!.agentProfileId, isNull);
    expect(result()!.config.agent, 'codex');
    expect(result()!.config.model, 'c1');
  });

  testWidgets('a link to an agent not in the list survives a plain confirm',
      (tester) async {
    // Archived, or the list failed to load: the picker can't show it, but
    // confirming without touching the picker must not unlink it.
    final result = await _openAutomationSheet(
      tester,
      initial: SessionConfig(agent: 'claude', model: 'm1'),
      initialAgentProfileId: 'p-gone',
    );
    expect(find.text('Model'), findsOneWidget);
    await _confirm(tester);
    expect(result()!.agentProfileId, 'p-gone');
  });

  testWidgets('an agent with instructions is unavailable on an old daemon',
      (tester) async {
    final result = await _openAutomationSheet(
      tester,
      initial: SessionConfig(agent: 'claude'),
      machineSupportsInstructions: false,
    );
    await tester.tap(find.text('Claude Code').last);
    await tester.pumpAndSettle();
    expect(find.text('Update required'), findsOneWidget);
    await tester.tap(find.text('Reviewer').last);
    await tester.pumpAndSettle();

    expect(find.text('Model'), findsOneWidget);
    await _confirm(tester);
    expect(result()!.agentProfileId, isNull);
  });
}
