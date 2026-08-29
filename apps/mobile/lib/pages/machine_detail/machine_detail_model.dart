import 'dart:async';

import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/machine_utils.dart' as mutils;
import '/flutter_flow/flutter_flow_util.dart';
import 'machine_detail_widget.dart' show MachineDetailWidget;

/// State for the machine detail page: seeds from the list's passed-in row,
/// re-fetches the canonical machine over REST, and merges live `machine-update`
/// WS events for the same id.
class MachineDetailModel extends FlutterFlowModel<MachineDetailWidget> {
  String machineId = '';
  dynamic machine; // normalized REST-shape map, or null until loaded
  bool isLoading = false;
  bool notFound = false;

  /// Set when a rename succeeds, so the list reloads on pop. (Removal pops with
  /// its own 'removed' result.)
  bool renamed = false;

  StreamSubscription<Map<String, dynamic>>? _wsSub;
  Timer? _ticker;
  VoidCallback? _notify;

  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    stopRealtime();
  }

  void seed(String id, dynamic data) {
    machineId = id;
    if (data is Map) machine = mutils.normalizeMachine(data);
  }

  Future<void> load() async {
    isLoading = machine == null;
    _bump();
    try {
      final result = await actions.apiGetMachineById(machineId);
      if (result == null) {
        // 404 — the machine was removed elsewhere. Only surface "not found"
        // when we had nothing to show; otherwise keep the seeded row.
        if (machine == null) notFound = true;
      } else {
        machine = mutils.normalizeMachine(result);
        notFound = false;
      }
    } catch (e) {
      debugPrint('Error loading machine $machineId: $e');
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
      if (e['event'] != 'machine_updated') return;
      if (mutils.machineId(e['data']) != machineId) return;
      final incoming = mutils.normalizeMachine(e['data']);
      final current = machine is Map
          ? Map<String, dynamic>.from(machine as Map)
          : <String, dynamic>{};
      machine = {...current, ...incoming};
      _bump();
    });
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

  /// Apply a rename result (the updated machine summary) locally.
  void applyRename(dynamic updated) {
    if (updated is Map) {
      final current = machine is Map
          ? Map<String, dynamic>.from(machine as Map)
          : <String, dynamic>{};
      machine = {...current, ...mutils.normalizeMachine(updated)};
    }
    renamed = true;
    _bump();
  }
}
