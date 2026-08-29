// Typed wrapper around `ws_client.callRpc('scan-files', ...)` — the live
// `@`-mention project index.
// See `plans/todos/file-mentions-live-rpc.md` §Phase 3.
//
// Distinct from `rpc_files.dart`'s `list-files`, which lists ONE directory
// level for the Files tab and filters through `git check-ignore`; this walks
// the whole project through `pathspec`, so it also works outside a git repo.
//
// Daemon-reported errors (path_not_found, not_a_directory, permission_denied)
// throw `FileIndexException`; transport failures surface as `RpcException`
// from the underlying WS layer — the two get handled differently, because the
// daemon is authoritative about its own disk but a dead socket says nothing
// about it.

typedef RpcCaller = Future<Map<String, dynamic>> Function(
  String machineId,
  String method,
  Map<String, dynamic> params,
);

class FileIndexException implements Exception {
  FileIndexException(this.code);
  final String code;

  @override
  String toString() => 'FileIndexException($code)';
}

/// One `scan-files` reply. [files] is null when the daemon answered
/// `unchanged` — the caller's `knownHash` still matches, so it should keep
/// what it already has rather than re-parsing an identical list.
class FileIndexResult {
  FileIndexResult({required this.hash, this.files, this.truncated = false});

  final String hash;
  final List<String>? files;
  final bool truncated;

  bool get unchanged => files == null;
}

Future<FileIndexResult> rpcScanFiles({
  required RpcCaller call,
  required String machineId,
  required String cwd,
  String? knownHash,
}) async {
  final result = await call(machineId, 'scan-files', {
    'cwd': cwd,
    if (knownHash != null && knownHash.isNotEmpty) 'known_hash': knownHash,
  });
  final err = result['error'];
  if (err is String) throw FileIndexException(err);
  if (result['unchanged'] == true) {
    return FileIndexResult(hash: result['hash'] as String? ?? '');
  }
  final raw = result['files'];
  return FileIndexResult(
    hash: result['hash'] as String? ?? '',
    files: raw is List
        ? raw.map((e) => e.toString()).toList(growable: false)
        : const <String>[],
    truncated: result['truncated'] == true,
  );
}
