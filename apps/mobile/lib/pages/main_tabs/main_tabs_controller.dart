import 'package:flutter/foundation.dart';

/// App-scoped bridge that lets a route pushed above the signed-in shell (the
/// full-screen [SearchWidget]) drive that shell: switch the active tab and,
/// for tasks/automations, deep-open an item once its tab's data has loaded.
///
/// It's a tiny singleton rather than callbacks threaded down the tree because
/// the search page is pushed on the root navigator, above [MainTabsWidget], and
/// otherwise has no handle back to the live tab that owns the fully-loaded
/// model needed to open an item's detail sheet. Sessions don't go through here
/// — they're a normal pushed route ([AgentChatWidget]).
///
/// Contract:
///  * [MainTabsWidget] listens to [requestedTab] and switches when it's a valid
///    index (>= 0).
///  * The Tasks / Automations tabs listen to [openTaskId] / [openAutomationId],
///    open the matching item after ensuring their list is loaded, then reset
///    the notifier to null so the same item can be re-opened later.
class MainTabsController {
  MainTabsController._();
  static final MainTabsController instance = MainTabsController._();

  static const int agentsTab = 0;
  static const int tasksTab = 1;
  static const int automationsTab = 2;

  /// Last requested tab index; -1 means "no request yet".
  final ValueNotifier<int> requestedTab = ValueNotifier<int>(-1);

  /// Item to open once its tab is ready; null when nothing is pending. The
  /// consuming tab resets this to null after handling it.
  final ValueNotifier<String?> openTaskId = ValueNotifier<String?>(null);
  final ValueNotifier<String?> openAutomationId = ValueNotifier<String?>(null);

  /// Switch to the Tasks tab and open [taskId]'s detail sheet.
  void showTask(String taskId) {
    openTaskId.value = taskId;
    requestedTab.value = tasksTab;
  }

  /// Switch to the Automations tab and open [automationId]'s editor.
  void showAutomation(String automationId) {
    openAutomationId.value = automationId;
    requestedTab.value = automationsTab;
  }
}
