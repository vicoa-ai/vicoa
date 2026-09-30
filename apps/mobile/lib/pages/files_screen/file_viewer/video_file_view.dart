// FileVideoView — plays a video from the Files tab. The daemon can't send one
// in a single `read-file` frame, so it's copied down in `read-file-range`
// slices first.

import 'dart:async';
import 'dart:io';

import 'package:chewie/chewie.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:path_provider/path_provider.dart';
import 'package:video_player/video_player.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_files.dart';
import '/custom_code/actions/ws_client.dart' show RpcException;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import 'video_controls.dart';

/// A video, copied off the machine in `read-file-range` slices into a temp
/// file (it won't fit one `read-file` frame), then played from disk.
class FileVideoView extends StatefulWidget {
  const FileVideoView({super.key, required this.machineId, required this.cwd, required this.path, required this.name, required this.size, required this.theme, required this.formatBytes, required this.errorBuilder});
  final String machineId;
  final String cwd;
  final String path;
  final String name;
  final int size;
  final FlutterFlowTheme theme;
  final String Function(int bytes) formatBytes;
  // The viewer's error card for an RPC/daemon error code, with a retry.
  final Widget Function(String code, VoidCallback onRetry) errorBuilder;

  @override
  State<FileVideoView> createState() => _FileVideoViewState();
}

class _FileVideoViewState extends State<FileVideoView> {
  // Every byte crosses the shared relay as base64, so keep it to clips.
  static const int _maxBytes = 100 * 1024 * 1024;

  Directory? _tempDir;
  VideoPlayerController? _video;
  ChewieController? _chewie;
  int _received = 0;
  String? _errorCode;
  bool _unplayable = false;
  bool _disposed = false;

  @override
  void initState() {
    super.initState();
    if (widget.size <= _maxBytes) unawaited(_load());
  }

  @override
  void dispose() {
    _disposed = true;
    _chewie?.dispose();
    _video?.dispose();
    final dir = _tempDir;
    if (dir != null) unawaited(dir.delete(recursive: true).catchError((_) => dir));
    super.dispose();
  }

  Future<void> _load() async {
    _chewie?.dispose();
    _chewie = null;
    await _video?.dispose();
    _video = null;
    safeSetState(() {
      _received = 0;
      _errorCode = null;
      _unplayable = false;
    });
    final File file;
    try {
      final dir = _tempDir ??= await (await getTemporaryDirectory()).createTemp('file_viewer_video_');
      // Keep the real name: the platform player picks the container by extension.
      file = File('${dir.path}/${widget.name}');
      await rpcDownloadFile(
        call: actions.VicoaWsClient.instance.callRpc,
        machineId: widget.machineId,
        cwd: widget.cwd,
        path: widget.path,
        size: widget.size,
        dest: file,
        onProgress: (received) => safeSetState(() => _received = received),
        isCancelled: () => _disposed,
      );
    } on FileOpsException catch (e) {
      if (e.code != 'cancelled') safeSetState(() => _errorCode = e.code);
      return;
    } on RpcException catch (e) {
      safeSetState(() => _errorCode = e.code);
      return;
    } catch (_) {
      safeSetState(() => _errorCode = 'download_failed');
      return;
    }
    if (_disposed) return;

    final video = VideoPlayerController.file(file);
    _video = video;
    try {
      await video.initialize();
    } catch (_) {
      // The platform player rejected it: a codec or container this device
      // can't decode (e.g. WebM on iOS).
      safeSetState(() => _unplayable = true);
      return;
    }
    if (_disposed) return;
    safeSetState(() {
      _chewie = ChewieController(
        videoPlayerController: video,
        aspectRatio: video.value.aspectRatio,
        autoPlay: false,
        looping: false,
        customControls: const FileVideoControls(),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = widget.theme;
    final l10n = AppLocalizations.of(context);
    final messageStyle = theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), letterSpacing: 0.0);
    if (widget.size > _maxBytes) {
      return Center(child: Padding(padding: const EdgeInsets.all(32), child: Text(l10n.fileViewerXVideoTooLarge(widget.formatBytes(_maxBytes)), textAlign: TextAlign.center, style: messageStyle)));
    }
    if (_errorCode != null) return widget.errorBuilder(_errorCode!, _load);
    if (_unplayable) {
      return Center(child: Padding(padding: const EdgeInsets.all(32), child: Text(l10n.fileViewerXVideoUnsupported, textAlign: TextAlign.center, style: messageStyle)));
    }
    final chewie = _chewie;
    // Fills the body down to the screen edge (the viewer's SafeArea leaves the
    // bottom open); FileVideoControls keeps its bar clear of the home indicator.
    if (chewie != null) return Chewie(controller: chewie);
    final downloaded = _received >= widget.size;
    return Align(
      alignment: const Alignment(0.0, -0.3),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Indeterminate once the bytes are in and the player is opening.
          CircularProgressIndicator(value: downloaded || widget.size == 0 ? null : _received / widget.size),
          const SizedBox(height: 16),
          Text(l10n.fileViewerXVideoLoading, style: messageStyle),
          const SizedBox(height: 4),
          Text(
            l10n.fileViewerXVideoProgress(widget.formatBytes(_received), widget.formatBytes(widget.size)),
            style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0),
          ),
        ],
      ),
    );
  }
}
