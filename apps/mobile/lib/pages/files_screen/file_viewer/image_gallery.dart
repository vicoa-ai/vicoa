// Which images the viewer can swipe between: the images in the opened image's
// folder, in the Files tree's order. Other files, and subfolders, are left out.

import '/custom_code/actions/files_cache.dart';
import '/custom_code/actions/rpc_files.dart';

/// The folder part of [path] (`''` for a file at the project root).
String parentDirOf(String path) {
  final i = path.lastIndexOf('/');
  return i < 0 ? '' : path.substring(0, i);
}

String baseNameOf(String path) => path.substring(path.lastIndexOf('/') + 1);

/// The image paths in [path]'s folder, given that folder's [entries]. Null
/// when [path] isn't among them, so the caller knows the listing is stale.
List<String>? imagesBeside(String path, List<FilesEntry> entries) {
  final dir = parentDirOf(path);
  final images = [
    for (final e in entries)
      if (!e.isDir && isImageFileName(e.name)) dir.isEmpty ? e.name : '$dir/${e.name}',
  ];
  return images.contains(path) ? images : null;
}

/// The images to swipe between when [path] is opened: from the cached folder
/// listing if it knows [path], otherwise (or with [fresh]) from one
/// `list-files` call, whose result is cached the way the Files tree caches
/// it. Null when there is nothing to swipe to (fewer than two images) or the
/// folder can't be read.
Future<List<String>?> loadImagesBeside({
  required String machineId,
  required String cwd,
  required String path,
  required FilesCache cache,
  required RpcCaller call,
  required bool connected,
  bool fresh = false,
}) async {
  final dir = parentDirOf(path);
  List<String>? images;
  final cached = cache.getListing(machineId: machineId, cwd: cwd, path: dir);
  if (cached != null) images = imagesBeside(path, cached.map(_entryFromCache).toList());
  if ((images == null || fresh) && connected) {
    try {
      final entries = await rpcListFiles(call: call, machineId: machineId, cwd: cwd, path: dir);
      await cache.putListing(
        machineId: machineId,
        cwd: cwd,
        path: dir,
        entries: [
          for (final e in entries) {'name': e.name, 'type': e.isDir ? 'dir' : 'file', if (e.size != null) 'size': e.size},
        ],
      );
      images = imagesBeside(path, entries);
    } catch (_) {
      // Keep whatever the cache said; no gallery is a fine fallback.
    }
  }
  return images != null && images.length > 1 ? images : null;
}

FilesEntry _entryFromCache(dynamic e) => FilesEntry(name: e['name'] as String, isDir: e['type'] == 'dir', size: e['size'] as int?);
