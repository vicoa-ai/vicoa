// Typed wrappers around `ws_client.callRpc('list-files' | 'read-file', ...)`.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers + §RPC method surface.
//
// Either wrapper throws `FileOpsException` for daemon-reported error codes
// (path_not_found, outside_project, too_large, ...); raw transport failures
// surface as `RpcException` from the underlying WS layer.

typedef RpcCaller = Future<Map<String, dynamic>> Function(
  String machineId,
  String method,
  Map<String, dynamic> params,
);

class FileOpsException implements Exception {
  FileOpsException(this.code);
  final String code;

  @override
  String toString() => 'FileOpsException($code)';
}

class FilesEntry {
  FilesEntry({required this.name, required this.isDir, this.size});
  final String name;
  final bool isDir;
  final int? size;
}

class FileContent {
  FileContent({
    required this.content,
    required this.encoding,
    required this.isBinary,
    required this.size,
    required this.truncated,
  });
  final String content;
  final String encoding; // 'utf-8' | 'base64'
  final bool isBinary;
  final int size;
  final bool truncated;
}

Future<List<FilesEntry>> rpcListFiles({
  required RpcCaller call,
  required String machineId,
  required String cwd,
  required String path,
}) async {
  final result = await call(machineId, 'list-files', {
    'cwd': cwd,
    'path': path,
  });
  final err = result['error'];
  if (err is String) throw FileOpsException(err);
  final entries = result['entries'] as List<dynamic>;
  return entries
      .map(
        (e) => FilesEntry(
          name: e['name'] as String,
          isDir: e['type'] == 'dir',
          size: e['size'] as int?,
        ),
      )
      .toList();
}

Future<FileContent> rpcReadFile({
  required RpcCaller call,
  required String machineId,
  required String cwd,
  required String path,
}) async {
  final result = await call(machineId, 'read-file', {
    'cwd': cwd,
    'path': path,
  });
  final err = result['error'];
  if (err is String) throw FileOpsException(err);
  return FileContent(
    content: result['content'] as String,
    encoding: result['encoding'] as String,
    isBinary: result['is_binary'] as bool,
    size: result['size'] as int,
    truncated: result['truncated'] as bool,
  );
}
