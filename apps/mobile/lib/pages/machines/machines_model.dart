import 'dart:async';

import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/machine_utils.dart' as mutils;
import '/flutter_flow/flutter_flow_util.dart';
import 'machines_widget.dart' show MachinesWidget;

/// State for the machines list: seeds from the FFAppState cache, fetches over
/// REST, merges live `machine-update` WS events, and runs a local ticker so
/// online/offline flips as heartbeats age (machine-management D13).
class MachinesModel extends FlutterFlowModel<MachinesWidget> {
  List<dynamic> machines = [];
  bool isLoading = false;
  bool hasError = false;

  StreamSubscription<Map<String, dynamic>>? _wsSub;
  Timer? _ticker;
  VoidCallback? _notify;

  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  @override
  void initState(BuildContext context) {
    machines = _sorted(FFAppState().cachedMachines);
  }

  @override
  void dispose() {
    stopRealtime();
  }

  Future<void> load() async {
    isLoading = machines.isEmpty; // spinner only when nothing cached
    hasError = false;
    _bump();
    try {
      final result = await actions.apiGetMachines();
      machines = _sorted(result);
      FFAppState().cachedMachines = machines;
      FFAppState().cachedMachinesTimestamp = getCurrentTimestamp;
    } catch (e) {
      debugPrint('Error loading machines: $e');
      if (machines.isEmpty) hasError = true;
    } finally {
      isLoading = false;
      _bump();
    }
  }

  void startRealtime() {
    if (_wsSub != null) return;
    final client = actions.VicoaWsClient.instance;
    client.retain();
    _wsSub = client.machineEvents.listen((e) {
      if (e['event'] == 'machine_updated') _mergeUpdate(e['data']);
    });
    // Re-evaluate liveness from last_heartbeat_at as time passes; the data
    // doesn't change, only its age relative to the 90s cutoff.
    _ticker = Timer.periodic(const Duration(seconds: 30), (_) => _bump());
  }

  void stopRealtime() {
    if (_wsSub != null) {
      _wsSub?.cancel();
      _wsSub = null;
      actions.VicoaWsClient.instance.release();
    }
    _ticker?.cancel();
    _ticker = null;
  }

  void _mergeUpdate(dynamic data) {
    final incoming = mutils.normalizeMachine(data);
    final id = incoming['machine_id']?.toString();
    if (id == null) return;
    final idx = machines.indexWhere((m) => mutils.machineId(m) == id);
    if (idx == -1) {
      machines = _sorted([...machines, incoming]);
    } else {
      final merged = {
        ...Map<String, dynamic>.from(machines[idx] as Map),
        ...incoming,
      };
      machines = _sorted(List<dynamic>.from(machines)..[idx] = merged);
    }
    FFAppState().cachedMachines = machines;
    _bump();
  }

  /// Online first, then most-recently-seen first (machine-management D16).
  List<dynamic> _sorted(dynamic raw) => mutils.sortMachinesByStatus(raw);
}
