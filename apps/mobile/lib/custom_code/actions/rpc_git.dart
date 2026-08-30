// Typed wrappers around `ws_client.callRpc('git-status' | 'git-diff', ...)`.
// See `plans/todos/vicoa-app-git-tab.md` §RPC method surface + §Phase C.
//
// Either wrapper throws `GitOpsException` for daemon-reported error codes
// (not_a_repo, outside_project, path_not_found, ...); raw transport failures
// surface as `RpcException` from the underlying WS layer.

typedef RpcCaller = Future<Map<String, dynamic>> Function(
  String machineId,
  String method,
  Map<String, dynamic> params,
);

class GitOpsException implements Exception {
  GitOpsException(this.code);
  final String code;

  @override
  String toString() => 'GitOpsException($code)';
}

class GitFileEntry {
  GitFileEntry({
    required this.path,
    required this.status,
    required this.additions,
    required this.deletions,
    required this.contentHash,
    this.oldPath,
  });
  final String path;
  final String status; // 'M' | 'A' | 'D' | 'R' | 'U' | '??'
  final int additions;
  final int deletions;
  final String? contentHash;
  final String? oldPath;

  static GitFileEntry fromJson(Map<String, dynamic> json) => GitFileEntry(
        path: json['path'] as String,
        status: json['status'] as String,
        additions: json['additions'] as int? ?? 0,
        deletions: json['deletions'] as int? ?? 0,
        contentHash: json['content_hash'] as String?,
        oldPath: json['old_path'] as String?,
      );
}

class GitStatusResult {
  GitStatusResult({
    required this.branch,
    required this.ahead,
    required this.behind,
    required this.detachedHead,
    required this.staged,
    required this.unstaged,
    required this.untracked,
    this.upstream,
  });
  final String branch;
  final int ahead;
  final int behind;
  final String? upstream;
  final bool detachedHead;
  final List<GitFileEntry> staged;
  final List<GitFileEntry> unstaged;
  final List<GitFileEntry> untracked;

  bool get isClean => staged.isEmpty && unstaged.isEmpty && untracked.isEmpty;

  static GitStatusResult fromJson(Map<String, dynamic> json) {
    List<GitFileEntry> parseSection(String key) {
      final raw = json[key] as List<dynamic>? ?? const [];
      return raw
          .map((e) => GitFileEntry.fromJson(e as Map<String, dynamic>))
          .toList();
    }

    return GitStatusResult(
      branch: json['branch'] as String? ?? '',
      ahead: json['ahead'] as int? ?? 0,
      behind: json['behind'] as int? ?? 0,
      upstream: json['upstream'] as String?,
      detachedHead: json['detached_head'] as bool? ?? false,
      staged: parseSection('staged'),
      unstaged: parseSection('unstaged'),
      untracked: parseSection('untracked'),
    );
  }
}

class GitDiffLine {
  GitDiffLine({required this.type, required this.content});
  final String type; // 'context' | 'add' | 'remove'
  final String content;

  static GitDiffLine fromJson(Map<String, dynamic> json) => GitDiffLine(
        type: json['type'] as String,
        content: json['content'] as String,
      );
}

class GitDiffHunk {
  GitDiffHunk({
    required this.header,
    required this.oldStart,
    required this.oldCount,
    required this.newStart,
    required this.newCount,
    required this.lines,
  });
  final String header;
  final int oldStart;
  final int oldCount;
  final int newStart;
  final int newCount;
  final List<GitDiffLine> lines;

  static GitDiffHunk fromJson(Map<String, dynamic> json) {
    final lines = (json['lines'] as List<dynamic>? ?? const [])
        .map((e) => GitDiffLine.fromJson(e as Map<String, dynamic>))
        .toList();
    return GitDiffHunk(
      header: json['header'] as String? ?? '',
      oldStart: json['old_start'] as int? ?? 0,
      oldCount: json['old_count'] as int? ?? 0,
      newStart: json['new_start'] as int? ?? 0,
      newCount: json['new_count'] as int? ?? 0,
      lines: lines,
    );
  }
}

class GitDiffResult {
  GitDiffResult({
    required this.path,
    required this.hunks,
    required this.isBinary,
    required this.truncated,
    required this.size,
  });
  final String path;
  final List<GitDiffHunk> hunks;
  final bool isBinary;
  final bool truncated;
  final int size;

  static GitDiffResult fromJson(Map<String, dynamic> json) {
    final hunks = (json['hunks'] as List<dynamic>? ?? const [])
        .map((e) => GitDiffHunk.fromJson(e as Map<String, dynamic>))
        .toList();
    return GitDiffResult(
      path: json['path'] as String? ?? '',
      hunks: hunks,
      isBinary: json['is_binary'] as bool? ?? false,
      truncated: json['truncated'] as bool? ?? false,
      size: json['size'] as int? ?? 0,
    );
  }
}

Future<GitStatusResult> rpcGitStatus({
  required RpcCaller call,
  required String machineId,
  required String cwd,
}) async {
  final result = await call(machineId, 'git-status', {'cwd': cwd});
  final err = result['error'];
  if (err is String) throw GitOpsException(err);
  return GitStatusResult.fromJson(result);
}

Future<GitDiffResult> rpcGitDiff({
  required RpcCaller call,
  required String machineId,
  required String cwd,
  required String path,
  required bool staged,
  required bool ignoreWhitespace,
}) async {
  final result = await call(machineId, 'git-diff', {
    'cwd': cwd,
    'path': path,
    'staged': staged,
    'ignore_whitespace': ignoreWhitespace,
  });
  final err = result['error'];
  if (err is String) throw GitOpsException(err);
  return GitDiffResult.fromJson(result);
}

/// One git worktree of a repo. `managed` means the daemon created it under
/// `~/vicoa/workspaces/` — only managed worktrees are removable from the app;
/// the user's own hand-made worktrees are shown read-only.
class WorktreeInfo {
  WorktreeInfo({
    required this.path,
    required this.branch,
    required this.head,
    required this.managed,
  });
  final String path;
  final String branch;
  final String head;
  final bool managed;

  static WorktreeInfo fromJson(Map<String, dynamic> json) => WorktreeInfo(
        path: json['path'] as String,
        branch: json['branch'] as String? ?? '',
        head: json['head'] as String? ?? '',
        managed: json['managed'] as bool? ?? false,
      );
}

Future<List<WorktreeInfo>> rpcGitWorktreeList({
  required RpcCaller call,
  required String machineId,
  required String cwd,
}) async {
  final result = await call(machineId, 'git-worktree-list', {'cwd': cwd});
  final err = result['error'];
  if (err is String) throw GitOpsException(err);
  final raw = result['worktrees'] as List<dynamic>? ?? const [];
  return raw
      .map((e) => WorktreeInfo.fromJson(e as Map<String, dynamic>))
      .toList();
}

Future<void> rpcGitWorktreeRemove({
  required RpcCaller call,
  required String machineId,
  required String cwd,
  required String worktreePath,
  required bool force,
}) async {
  final result = await call(machineId, 'git-worktree-remove', {
    'cwd': cwd,
    'worktree_path': worktreePath,
    'force': force,
  });
  final err = result['error'];
  if (err is String) throw GitOpsException(err);
}
