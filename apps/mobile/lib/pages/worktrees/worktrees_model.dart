import 'package:flutter/foundation.dart' show mapEquals;
import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_git.dart';
import '/custom_code/actions/rpc_github.dart';
import '/custom_code/utils/pr_status.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'worktrees_widget.dart' show WorktreesWidget;

/// State for the worktrees screen: lists a repo's git worktrees over RPC and
/// supports optimistic removal of managed ones. Each worktree's pull request
/// comes from one `github-pr-list` for the repo, through the cache Home
/// shares, so the colors Home already knows paint at once.
class WorktreesModel extends FlutterFlowModel<WorktreesWidget> {
  bool isLoading = true;
  String? error; // 'not_a_repo' or a transport error string
  List<WorktreeInfo> worktrees = const [];
  Map<String, PrInfo> _prs = const {};
  DateTime? _prsRequestedAt;

  VoidCallback? _notify;
  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {}

  /// The pull request of [worktree]'s branch, or null.
  PrInfo? pullRequestFor(WorktreeInfo worktree) => prForCheckout(
        _prs,
        branch: worktree.branch,
        upstream: worktree.upstream,
        head: worktree.head,
      );

  /// [prMaxAge] is how old a reused PR answer may be: the default on open, a
  /// few seconds on a pull-to-refresh.
  Future<void> load(String machineId, String cwd, {Duration prMaxAge = kPrCacheTtl}) async {
    isLoading = worktrees.isEmpty;
    error = null;
    _bump();
    String? repoPath;
    try {
      final listing = await rpcGitWorktreeListing(
        call: actions.VicoaWsClient.instance.callRpc,
        machineId: machineId,
        cwd: cwd,
      );
      worktrees = listing.worktrees;
      // Keyed like Home's requests (the main checkout), so they share answers.
      repoPath = listing.mainDisplayPath ?? listing.mainPath ?? cwd;
      final known = peekGithubPrList(machineId, repoPath);
      if (known != null) _applyPrs(known);
    } on GitOpsException catch (e) {
      error = e.code;
    } catch (e) {
      error = e.toString();
    } finally {
      isLoading = false;
      _bump();
    }
    if (repoPath != null && worktrees.isNotEmpty) {
      await _loadPrs(machineId, repoPath, prMaxAge);
    }
  }

  Future<void> _loadPrs(String machineId, String repoPath, Duration maxAge) async {
    try {
      final snapshot = await rpcGithubPrListCached(
        call: actions.VicoaWsClient.instance.callRpc,
        machineId: machineId,
        repoPath: repoPath,
        maxAge: maxAge,
      );
      if (_applyPrs(snapshot)) _bump();
    } catch (_) {
      // No `gh`, a timeout, an unreachable machine: the rows keep the plain
      // branch icon (or the colors already shown). Never worth an error.
    }
  }

  /// Whether the shown PRs changed. An answer older than the one shown loses.
  bool _applyPrs(PrSnapshot snapshot) {
    final shown = _prsRequestedAt;
    if (shown != null && shown.isAfter(snapshot.requestedAt)) return false;
    _prsRequestedAt = snapshot.requestedAt;
    if (mapEquals(snapshot.prs, _prs)) return false;
    _prs = snapshot.prs;
    return true;
  }

  void removeFromList(String path) {
    worktrees = worktrees.where((w) => w.path != path).toList();
    _bump();
  }
}
