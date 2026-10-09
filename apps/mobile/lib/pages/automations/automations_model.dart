import 'dart:async';

import 'package:flutter/material.dart';

import '/backend/agent_catalog.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/automation_utils.dart' as autils;
import '/custom_code/utils/machine_utils.dart';
import '/custom_code/utils/worktree_selection.dart';
import '/custom_code/utils/task_utils.dart' as tutils show kNoProjectFilter;
import '/flutter_flow/flutter_flow_util.dart';
import '/pages/common/filter_panel.dart' show filterByProject;
import 'automations_widget.dart' show AutomationsWidget;

class AutomationsModel extends FlutterFlowModel<AutomationsWidget> {
  List<dynamic> automations = [];
  List<dynamic> machines = [];
  List<dynamic> projects = [];
  AgentCatalog? agentCatalog;
  bool isLoading = true;
  bool hasError = false;

  /// 'all' | 'active' | 'paused'
  String filter = 'all';

  /// null → all projects; [tutils.kNoProjectFilter] → filed nowhere; otherwise
  /// a project id, matched against the automation's derived `project_id`.
  String? projectFilter;

  /// Automation id with an in-flight run-now/toggle/delete, for row spinners.
  String? busyId;

  VoidCallback? _notify;
  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  @override
  void initState(BuildContext context) {
    agentCatalog = agentCatalogFallback();
  }

  @override
  void dispose() {}

  List<dynamic> get filteredAutomations {
    final inProject =
        filterByProject(automations, projectFilter, autils.automationProjectId);
    if (filter == 'active') {
      return inProject.where(autils.automationEnabled).toList();
    }
    if (filter == 'paused') {
      return inProject.where((a) => !autils.automationEnabled(a)).toList();
    }
    return inProject;
  }

  bool get isFiltered => filter != 'all' || projectFilter != null;

  void setFilter(String value) {
    filter = value;
    _bump();
  }

  void setProjectFilter(String? projectId) {
    projectFilter = projectId;
    _bump();
  }

  dynamic machineById(String id) => machines.firstWhere(
        (m) => machineId(m) == id,
        orElse: () => null,
      );

  Future<void> load() async {
    isLoading = automations.isEmpty;
    _bump();
    final results = await Future.wait<dynamic>([
      actions.apiGetAutomations(),
      actions.apiGetMachines(),
      actions.apiGetProjects(),
    ]);
    final fetched = results[0] as List<dynamic>?;
    machines = sortMachinesByStatus(results[1]);
    projects = results[2] as List<dynamic>;
    if (fetched == null) {
      hasError = automations.isEmpty;
    } else {
      automations = fetched;
      hasError = false;
    }
    isLoading = false;
    _bump();
    // SWR catalog refresh — the baked-in fallback keeps the editor renderable.
    unawaited(actions
        .apiGetAgentCatalog()
        .then((fresh) {
          agentCatalog = fresh;
          _bump();
        })
        .catchError((_) {}));
  }

  /// Optimistic pause/resume. Toggling `enabled` alone deliberately does not
  /// recompute the schedule server-side, so a paused one-time automation keeps
  /// its fire time.
  Future<bool> toggleEnabled(dynamic automation) async {
    final id = autils.automationId(automation);
    final next = !autils.automationEnabled(automation);
    automations = [
      for (final a in automations)
        if (autils.automationId(a) == id)
          {...(a as Map), 'enabled': next}
        else
          a,
    ];
    _bump();
    final updated = await actions.apiUpdateAutomation(id, {'enabled': next});
    if (updated == null) {
      await load();
      return false;
    }
    _replace(updated);
    return true;
  }

  Future<bool> deleteAutomation(String id) async {
    busyId = id;
    _bump();
    final ok = await actions.apiDeleteAutomation(id);
    busyId = null;
    if (ok) {
      automations =
          automations.where((a) => autils.automationId(a) != id).toList();
    }
    _bump();
    return ok;
  }

  Future<Map<String, dynamic>?> createAutomation(
      Map<String, dynamic> body) async {
    final created = await actions.apiCreateAutomation(body);
    if (created != null) {
      automations = [created, ...automations];
      _bump();
    }
    return created;
  }

  Future<Map<String, dynamic>?> updateAutomation(
      String id, Map<String, dynamic> body) async {
    final updated = await actions.apiUpdateAutomation(id, body);
    if (updated != null) _replace(updated);
    return updated;
  }

  /// Client-side "Run now": spawn the session over the daemon WS RPC (the
  /// same path the web uses), then record the outcome on the automation.
  /// Returns `{'status': 'fired'|'missed_offline'|'failed', 'instanceId'?}`.
  Future<Map<String, dynamic>> runNow(dynamic automation) async {
    final id = autils.automationId(automation);
    busyId = id;
    _bump();
    try {
      final sessionId = autils.automationTargetSessionId(automation);
      if (sessionId != null) {
        return await _runInSession(id, sessionId, autils.automationPrompt(automation));
      }
      final cfg =
          SessionConfig.fromJson(autils.automationSessionConfig(automation));
      final wt = autils.automationWorktree(automation);
      final mode = switch (wt?['mode']) {
        'new' => WorktreeMode.newWorktree,
        'existing' => WorktreeMode.existing,
        _ => WorktreeMode.none,
      };
      final spawn = resolveWorktreeSpawn(
        mode: mode,
        baseDirectory: autils.automationDirectory(automation),
        selectedWorktreePath: wt?['path'] as String?,
      );
      final result = await actions.apiSpawnSession(
        autils.automationMachineId(automation),
        spawn.directory,
        agent: cfg.agent,
        prompt: autils.automationPrompt(automation),
        extraMetadata: cfg.toSpawnMetadata(),
        worktree: spawn.worktree,
        // A linked automation runs its saved agent, the same as a scheduled
        // fire: the server adds the agent's instructions and stamps the session.
        agentProfileId: autils.automationAgentProfileId(automation),
      );
      String status;
      String? detail;
      String? instanceId;
      if (result['success'] == true) {
        status = 'fired';
        instanceId = result['agentInstanceId']?.toString();
      } else {
        final error = (result['error'] ?? '').toString();
        final offline =
            error.contains('no_handler') || error.contains('not_connected');
        status = offline ? 'missed_offline' : 'failed';
        detail = error;
      }
      await actions.apiRecordAutomationRun(
        id,
        status: status,
        agentInstanceId: instanceId,
        detail: detail,
      );
      return {
        'status': status,
        if (instanceId != null) 'instanceId': instanceId,
      };
    } finally {
      busyId = null;
      _bump();
      unawaited(_refreshOne(id));
    }
  }

  /// "Run now" on an automation that runs in a session continues it the way
  /// the scheduler does: the prompt as a message while its agent is live, else
  /// a resume carrying the prompt (and a message after all if the daemon finds
  /// the agent still running).
  Future<Map<String, dynamic>> _runInSession(
      String id, String sessionId, String prompt) async {
    String status = 'fired';
    String? detail;
    final instance = await actions.apiGetInstanceById(sessionId);
    if (instance is! Map) {
      status = 'failed';
      detail = 'session not found';
    } else {
      var send = instance['live_state'] == actions.kLiveStateLive;
      if (!send) {
        final config = instance['session_config'] is Map
            ? Map<String, dynamic>.from(instance['session_config'] as Map)
            : null;
        final metadata = instance['instance_metadata'] is Map
            ? Map<String, dynamic>.from(instance['instance_metadata'] as Map)
            : null;
        final resumed = await actions.apiResumeSession(
          instance['machine_id']?.toString() ?? '',
          sessionId,
          actions.resumeExpandProjectPath(
            instance['project']?.toString() ?? '',
            instance['home_dir']?.toString(),
          ),
          agent: actions.resumeAgentSlug(
            instance['agent_type_name']?.toString(),
            sessionConfig: config,
          ),
          agentSessionId: actions.resumeAgentSessionHandle(metadata),
          sessionConfig: config,
          prompt: prompt,
        );
        if (resumed['success'] != true) {
          final error = (resumed['error'] ?? '').toString();
          final code = (resumed['errorCode'] ?? '').toString();
          final offline = code == 'no_handler' ||
              error.contains('no_handler') ||
              error.contains('not_connected');
          status = offline ? 'missed_offline' : 'failed';
          detail = error;
        } else {
          actions.markResumed(sessionId);
          send = resumed['alreadyRunning'] == true;
        }
      }
      if (send && await actions.apiChatWithAgent(sessionId, prompt) == null) {
        status = 'failed';
        detail = 'could not send the prompt';
      }
    }
    await actions.apiRecordAutomationRun(
      id,
      status: status,
      agentInstanceId: instance is Map ? sessionId : null,
      detail: detail,
    );
    return {'status': status, 'instanceId': sessionId};
  }

  void _replace(Map<String, dynamic> updated) {
    final id = autils.automationId(updated);
    automations = [
      for (final a in automations)
        if (autils.automationId(a) == id) updated else a,
    ];
    _bump();
  }

  /// Refresh a single row's server-derived fields (last_run_*, next_run_at)
  /// after a run-now without reloading the whole list.
  Future<void> _refreshOne(String id) async {
    final fresh = await actions.apiGetAutomations();
    if (fresh == null) return;
    automations = fresh;
    _bump();
  }
}
