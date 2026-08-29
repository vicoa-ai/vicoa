import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/machine_utils.dart';
import 'start_session_widget.dart' show StartSessionWidget;
import 'package:flutter/material.dart';

class StartSessionModel extends FlutterFlowModel<StartSessionWidget> {
  // State
  List<dynamic> machines = [];
  bool isLoadingMachines = true;
  String? selectedMachineId;
  String? selectedAgentType;
  TextEditingController directoryController = TextEditingController();
  FocusNode directoryFocusNode = FocusNode();
  bool isSubmitting = false;

  // Callback to trigger widget rebuild
  VoidCallback? onStateChanged;

  // Available agent types
  final List<Map<String, dynamic>> agentTypes = [
    {
      'id': 'claude code',
      'name': 'Claude Code',
      'isComingSoon': false,
    },
    {
      'id': 'codex',
      'name': 'Codex',
      'isComingSoon': false,
    },
    {
      'id': 'opencode',
      'name': 'OpenCode',
      'isComingSoon': false,
    },
    {
      'id': 'gemini',
      'name': 'Gemini',
      'isComingSoon': true,
    },
  ];

  @override
  void initState(BuildContext context) {
    debugLogWidgetClass(this);
    // Set default agent type
    final defaultAgent = agentTypes.firstWhere(
      (agent) => !(agent['isComingSoon'] as bool? ?? false),
      orElse: () => agentTypes.first,
    );
    selectedAgentType = defaultAgent['id'] as String?;
    // Load machines asynchronously
    _loadMachines();
  }

  Future<void> _loadMachines() async {
    // Fetch data from API
    debugPrint('Fetching machines from API...');
    try {
      final freshMachines = await actions.apiGetMachines();
      debugPrint('Received ${freshMachines.length} machines from API');
      machines = freshMachines;

      // Select first available machine if none selected
      if (selectedMachineId == null && machines.isNotEmpty) {
        _selectDefaultMachine();
      }

      isLoadingMachines = false;
      onStateChanged?.call(); // Trigger widget rebuild
      debugPrint('Machine loading complete, UI updated');
    } catch (e) {
      debugPrint('Error loading machines from API: $e');
      machines = [];
      isLoadingMachines = false;
      onStateChanged?.call(); // Trigger widget rebuild
    }
  }

  void _selectDefaultMachine() {
    if (machines.isNotEmpty) {
      final firstMachine = machines.first;
      selectedMachineId = firstMachine['machine_id'] ?? firstMachine['id'];
      _updateDirectoryForMachine(firstMachine);
    }
  }

  void selectMachine(String machineId) {
    selectedMachineId = machineId;
    final machine = machines.firstWhere(
      (m) => (m['machine_id'] ?? m['id']) == machineId,
      orElse: () => null,
    );
    if (machine != null) {
      _updateDirectoryForMachine(machine);
    }
  }

  void _updateDirectoryForMachine(dynamic machine) {
    final recentDirs = _getRecentDirectoriesForMachine(machine);
    if (recentDirs.isNotEmpty) {
      directoryController.text = recentDirs.first;
    } else {
      final homeDir = getMachineHomeDir(machine);
      directoryController.text = homeDir ?? '~/';
    }
  }

  List<String> _getRecentDirectoriesForMachine(dynamic machine) {
    if (machine is Map) {
      final dirs = machine['recent_directories'];
      if (dirs is List) {
        return dirs.map((item) => item.toString()).toList();
      }
      final metadata = machine['metadata'];
      if (metadata is Map && metadata['recent_directories'] is List) {
        return (metadata['recent_directories'] as List)
            .map((item) => item.toString())
            .toList();
      }
    }
    return [];
  }

  List<String> getRecentDirectories() {
    final appState = FFAppState();

    if (selectedMachineId == null) return appState.cachedDirectories;

    final machine = machines.firstWhere(
      (m) => (m['machine_id'] ?? m['id']) == selectedMachineId,
      orElse: () => null,
    );

    if (machine != null) {
      final machineRecent = _getRecentDirectoriesForMachine(machine);
      // Combine machine-specific directories with app-level cached directories
      final combined = <String>{...machineRecent, ...appState.cachedDirectories}.toList();
      return combined.take(20).toList();
    }

    return appState.cachedDirectories;
  }

  bool isMachineOnline(dynamic machine) {
    try {
      final lastHeartbeatStr = machine['last_heartbeat_at'];
      if (lastHeartbeatStr == null) return false;

      final lastHeartbeat = DateTime.parse(lastHeartbeatStr);
      final now = DateTime.now();
      final difference = now.difference(lastHeartbeat);

      // Consider online if heartbeat is within last 60 seconds (2x the 30s interval)
      return difference.inSeconds <= 60;
    } catch (e) {
      debugPrint('Error checking machine online status: $e');
      return false;
    }
  }

  String getMachineDisplayName(dynamic machine) {
    final displayName = machine['display_name'];
    if (displayName is String && displayName.isNotEmpty) {
      return displayName;
    }
    final hostname = machine['hostname'];
    if (hostname is String && hostname.isNotEmpty) {
      return hostname;
    }
    return 'Unnamed machine';
  }

  dynamic getSelectedMachine() {
    if (selectedMachineId == null) return null;
    return machines.firstWhere(
      (m) => (m['machine_id'] ?? m['id']) == selectedMachineId,
      orElse: () => null,
    );
  }

  Future<Map<String, dynamic>> startSession() async {
    if (selectedMachineId == null ||
        directoryController.text.trim().isEmpty ||
        selectedAgentType == null) {
      return {
        'success': false,
        'error': 'Please fill in all fields',
      };
    }

    if (!isAgentTypeSelectable(selectedAgentType)) {
      return {
        'success': false,
        'error': 'Selected agent is coming soon',
      };
    }

    isSubmitting = true;
    onStateChanged?.call(); // Trigger widget rebuild for loading state

    try {
      final directory = directoryController.text.trim();

      // Add to cache before spawning
      FFAppState().addToCachedDirectories(directory);

      final result = await actions.apiSpawnSession(
        selectedMachineId!,
        directory,
        agent: _getApiAgentType(selectedAgentType!),
      );

      return result;
    } finally {
      isSubmitting = false;
      onStateChanged?.call(); // Trigger widget rebuild
    }
  }

  @override
  void dispose() {
    directoryController.dispose();
    directoryFocusNode.dispose();
  }

  bool isAgentTypeSelectable(String? agentId) {
    if (agentId == null) {
      return false;
    }
    final agent = agentTypes.firstWhere(
      (item) => item['id'] == agentId,
      orElse: () => <String, dynamic>{},
    );
    if (agent.isEmpty) {
      return false;
    }
    return !(agent['isComingSoon'] as bool? ?? false);
  }

  String _getApiAgentType(String agentId) {
    if (agentId == 'claude code') {
      return 'claude';
    }
    return agentId;
  }
}
