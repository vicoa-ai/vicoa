import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_git.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'worktrees_widget.dart' show WorktreesWidget;

/// State for the worktrees screen: lists a repo's git worktrees over RPC and
/// supports optimistic removal of managed ones.
class WorktreesModel extends FlutterFlowModel<WorktreesWidget> {
  bool isLoading = true;
  String? error; // 'not_a_repo' or a transport error string
  List<WorktreeInfo> worktrees = const [];

  VoidCallback? _notify;
  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {}

  Future<void> load(String machineId, String cwd) async {
    isLoading = worktrees.isEmpty;
    error = null;
    _bump();
    try {
      worktrees = await rpcGitWorktreeList(
        call: actions.VicoaWsClient.instance.callRpc,
        machineId: machineId,
        cwd: cwd,
      );
    } on GitOpsException catch (e) {
      error = e.code;
    } catch (e) {
      error = e.toString();
    } finally {
      isLoading = false;
      _bump();
    }
  }

  void removeFromList(String path) {
    worktrees = worktrees.where((w) => w.path != path).toList();
    _bump();
  }
}
