import '/flutter_flow/flutter_flow_util.dart';
import 'session_info_sheet_widget.dart' show SessionInfoSheetWidget;
import 'package:flutter/material.dart';

class SessionInfoSheetModel extends FlutterFlowModel<SessionInfoSheetWidget> {
  TextEditingController? titleController;
  FocusNode? titleFocusNode;

  String? originalTitle;
  bool isSaving = false;

  dynamic resolvedMachine;
  bool isMachineLoading = false;

  // The worktree's checked-out branch (fetched over RPC). Null until resolved
  // or when it can't be read (offline / not a repo / detached) — the row then
  // falls back to the directory name.
  String? worktreeBranch;
  bool worktreeResolved = false;

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    titleFocusNode?.dispose();
    titleController?.dispose();
  }
}
