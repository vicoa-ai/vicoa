import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '/components/floating_tab_bar.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/automations/automations_widget.dart';
import '/pages/home/home_widget.dart';
import '/pages/tasks/tasks_widget.dart';
import 'main_tabs_controller.dart';

/// The signed-in shell: Agents / Tasks / Automations as tabs behind a floating
/// Apple-style bottom tab bar. Tabs build lazily on first visit and then stay
/// alive in an IndexedStack so each keeps its scroll position, filters, and
/// streams when switching. Profile now lives in the Home header (top-left), not
/// as a tab.
class MainTabsWidget extends StatefulWidget {
  const MainTabsWidget({super.key, this.initialTab = 0});

  final int initialTab;

  static String routeName = 'MainTabs';
  static String routePath = '/tabs';

  @override
  State<MainTabsWidget> createState() => _MainTabsWidgetState();
}

class _MainTabsWidgetState extends State<MainTabsWidget> {
  late int _index = widget.initialTab.clamp(0, 2);
  final Set<int> _built = {};

  @override
  void initState() {
    super.initState();
    MainTabsController.instance.requestedTab.addListener(_onTabRequested);
  }

  @override
  void dispose() {
    MainTabsController.instance.requestedTab.removeListener(_onTabRequested);
    super.dispose();
  }

  /// Honors a tab switch requested from a pushed route (e.g. search opening a
  /// task result). Building the target lazily first keeps the IndexedStack's
  /// build-on-first-visit behavior intact.
  void _onTabRequested() {
    final requested = MainTabsController.instance.requestedTab.value;
    if (!mounted || requested < 0 || requested > 2 || requested == _index) {
      return;
    }
    setState(() {
      _built.add(requested);
      _index = requested;
    });
  }

  Widget _tab(int index) {
    if (!_built.contains(index)) return const SizedBox.shrink();
    switch (index) {
      case 0:
        return const HomeWidget();
      case 1:
        return const TasksWidget();
      default:
        return const AutomationsWidget();
    }
  }

  @override
  Widget build(BuildContext context) {
    _built.add(_index);
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: theme.secondaryBackground,
      body: Stack(
        children: [
          IndexedStack(
            index: _index,
            children: [for (var i = 0; i < 3; i++) _tab(i)],
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: FloatingTabBar(
              currentIndex: _index,
              onTap: (i) => setState(() => _index = i),
              items: [
                FloatingTabItem(
                  icon: FontAwesomeIcons.comment,
                  selectedIcon: FontAwesomeIcons.comment,
                  label: l10n.tabAgents,
                  // FontAwesome glyph reads heavier than the Material icons —
                  // shrink it so all four tabs feel optically the same size.
                  iconSize: 21.0,
                ),
                FloatingTabItem(
                  icon: Icons.checklist_rounded,
                  selectedIcon: Icons.checklist_rounded,
                  label: l10n.tabTasks,
                ),
                FloatingTabItem(
                  icon: Icons.schedule_outlined,
                  selectedIcon: Icons.schedule_rounded,
                  label: l10n.tabAutomations,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
