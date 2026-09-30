// Typed wrappers around `ws_client.callRpc('list-files' | 'read-file' |
// 'read-file-range', ...)`.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers + §RPC method surface.
//
// Each wrapper throws `FileOpsException` for daemon-reported error codes
// (path_not_found, outside_project, too_large, ...); raw transport failures
// surface as `RpcException` from the underlying WS layer.

import 'dart:convert';
import 'dart:io';
import 'dart:math';

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
    this.mimeType,
  });
  final String content;
  final String encoding; // 'utf-8' | 'base64'
  final bool isBinary;
  final int size;
  final bool truncated;
  // Set for videos (`video/mp4`, ...): their bytes come through
  // `rpcDownloadFile`, not `content`. An older daemon never sets it.
  final String? mimeType;

  bool get isVideo => mimeType?.startsWith('video/') ?? false;
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
    mimeType: result['mime_type'] as String?,
  );
}

/// Bytes requested per `read-file-range` call. Half the daemon's cap so the
/// slices in flight together still clear the 30s RPC timeout on a slow uplink.
const int kFileRangeChunkBytes = 512 * 1024;

/// Copy a whole file off the machine into [dest] through `read-file-range`
/// slices, [parallelism] of them in flight at a time.
///
/// [size] is the file's size from `read-file`. Throws [FileOpsException] with
/// a daemon error code, `file_changed` when the file's size or mtime moves
/// mid-copy (stitching two versions together would corrupt it), or
/// `cancelled` once [isCancelled] returns true.
Future<void> rpcDownloadFile({
  required RpcCaller call,
  required String machineId,
  required String cwd,
  required String path,
  required int size,
  required File dest,
  void Function(int received)? onProgress,
  bool Function()? isCancelled,
  int chunkBytes = kFileRangeChunkBytes,
  int parallelism = 3,
}) async {
  final raf = await dest.open(mode: FileMode.write);
  var nextOffset = 0;
  var received = 0;
  var failed = false;
  num? mtime;
  // RandomAccessFile allows one pending operation at a time; slices land out
  // of order, so their writes queue here.
  var writes = Future<void>.value();

  Future<void> worker() async {
    try {
      while (!failed && nextOffset < size) {
        if (isCancelled?.call() ?? false) throw FileOpsException('cancelled');
        final offset = nextOffset;
        nextOffset += chunkBytes;
        final result = await call(machineId, 'read-file-range', {
          'cwd': cwd,
          'path': path,
          'offset': offset,
          'length': chunkBytes,
        });
        if (failed) return;
        final err = result['error'];
        if (err is String) throw FileOpsException(err);
        final bytes = base64Decode(result['content'] as String);
        final sliceMtime = result['mtime'] as num;
        mtime ??= sliceMtime;
        if (result['size'] != size ||
            sliceMtime != mtime ||
            bytes.length != min(chunkBytes, size - offset)) {
          throw FileOpsException('file_changed');
        }
        writes = writes.then((_) async {
          await raf.setPosition(offset);
          await raf.writeFrom(bytes);
        });
        await writes;
        received += bytes.length;
        onProgress?.call(received);
      }
    } catch (_) {
      failed = true;
      rethrow;
    }
  }

  try {
    await Future.wait([for (var i = 0; i < parallelism; i++) worker()]);
  } finally {
    await raf.close();
  }
}
