// FileViewerWidget — pushed full-screen route for inspecting one file. An
// image can be swiped left and right through the other images in its folder.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C File viewer route.

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/atom-one-dark.dart';
import 'package:flutter_highlight/themes/atom-one-light.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/files_cache.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_files.dart';
import '/custom_code/widgets/file_dropdown_menu.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '../machine_offline_banner.dart';
import 'file_content_loader.dart';
import 'image_gallery.dart';
import 'video_file_view.dart';
import 'zoomable_image.dart';

class FileViewerWidget extends StatefulWidget {
  const FileViewerWidget({super.key, required this.machineId, required this.cwd, required this.path, required this.name, this.rpc});

  static String routeName = 'FileViewer';
  static String routePath = '/fileViewer';

  final String machineId;
  final String cwd;
  final String path;
  final String name;
  /// How files are fetched. Null uses the shared WS client; tests pass a fake.
  final FileViewerRpc? rpc;

  @override
  State<FileViewerWidget> createState() => _FileViewerWidgetState();
}

typedef FileViewerRpc = ({RpcCaller send, bool Function() connected});

// Route result key — agent_chat consumes this to drop `@<path>` into the
// chat input area when the user taps "Add to context".
const String kFileViewerAddToContextKey = 'addToContext';

class _FileViewerWidgetState extends State<FileViewerWidget> {
  late final Future<FilesCache> _cache = FilesCache.open();
  final GlobalKey _menuButtonKey = GlobalKey();

  // The file on screen. Starts as the one opened; the gallery moves it.
  late String _path = widget.path;
  late String _name = widget.name;
  final Map<String, FileContentLoader> _loaders = {};

  // Images in the opened image's folder, when there are others to swipe to.
  // Null shows just the one file, which is always the case for non-images.
  List<String>? _gallery;
  PageController? _pages;
  // Keys the PageView, so a re-read folder starts a fresh one on the right
  // page instead of jumping.
  int _galleryVersion = 0;
  bool _zoomed = false;
  // Fingers on the gallery right now. Two or more is a pinch, so paging
  // stops: otherwise a pinch with one finger held still reads as a swipe.
  final Set<int> _touches = {};
  // Which way the user last swiped: the neighbour that way gets preloaded.
  int _direction = 1;
  bool _edgeBuzzed = false;

  @override
  void initState() {
    super.initState();
    final first = _loaderFor(widget.path, viewed: true);
    // Read the folder only once the opened image is on screen, so the
    // gallery never slows down the first paint.
    if (isImageFileName(widget.path)) unawaited(first.settled.then((_) => _resolveGallery()));
  }

  @override
  void dispose() {
    for (final loader in _loaders.values) {
      loader.dispose();
    }
    _pages?.dispose();
    super.dispose();
  }

  RpcCaller get _send => widget.rpc?.send ?? actions.VicoaWsClient.instance.callRpc;
  bool _connected() => widget.rpc?.connected() ?? actions.VicoaWsClient.instance.isConnected;

  FileContentLoader _loaderFor(String path, {bool viewed = false}) {
    final existing = _loaders[path];
    if (existing != null) return existing;
    final loader = FileContentLoader(machineId: widget.machineId, cwd: widget.cwd, path: path, cache: _cache, call: _send, isConnected: _connected, viewed: viewed);
    _loaders[path] = loader;
    unawaited(loader.load());
    return loader;
  }

  Future<void> _resolveGallery({bool fresh = false}) async {
    final images = await loadImagesBeside(machineId: widget.machineId, cwd: widget.cwd, path: _path, cache: await _cache, call: _send, connected: _connected(), fresh: fresh);
    if (!mounted) return;
    _applyGallery(images);
  }

  void _applyGallery(List<String>? images) {
    final usable = images != null && images.contains(_path);
    if (!usable) {
      // Keep a gallery already on screen if a re-read can't place the
      // current image (offline, or it was just deleted).
      return;
    }
    final current = _gallery;
    if (current != null && listEquals(current, images)) return;
    final old = _pages;
    if (old != null) WidgetsBinding.instance.addPostFrameCallback((_) => old.dispose());
    final index = images.indexOf(_path);
    safeSetState(() {
      _gallery = images;
      _pages = PageController(initialPage: index);
      _galleryVersion++;
      _zoomed = false;
    });
    _dropFarLoaders(index);
    _preloadFrom(index);
  }

  void _onPageChanged(int index) {
    final images = _gallery!;
    final path = images[index];
    final from = images.indexOf(_path);
    if (from >= 0 && index != from) _direction = index > from ? 1 : -1;
    safeSetState(() {
      _path = path;
      _name = baseNameOf(path);
      _zoomed = false;
    });
    _loaderFor(path).markViewed();
    _dropFarLoaders(index);
    _preloadFrom(index);
  }

  // Once the current image has loaded, fetch the next one in the swipe
  // direction so it's ready by the time it's swiped in.
  void _preloadFrom(int index) {
    final images = _gallery;
    if (images == null) return;
    final next = index + _direction;
    if (next < 0 || next >= images.length) return;
    final path = images[index];
    unawaited(_loaderFor(path).settled.then((_) {
      if (!mounted || _path != path || _gallery != images) return;
      _loaderFor(images[next]);
    }));
  }

  // Only the current page and its two neighbours can be on screen (PageView
  // builds nothing off-screen), so loaders further away are let go.
  void _dropFarLoaders(int index) {
    final images = _gallery!;
    final keep = {for (var i = index - 1; i <= index + 1; i++) if (i >= 0 && i < images.length) images[i]};
    final far = _loaders.keys.where((p) => !keep.contains(p)).toList();
    for (final path in far) {
      _loaders.remove(path)!.dispose();
    }
  }

  void _onTouch(PointerEvent e, {required bool down}) {
    final wasPinch = _touches.length > 1;
    down ? _touches.add(e.pointer) : _touches.remove(e.pointer);
    if (wasPinch != _touches.length > 1) safeSetState(() {});
  }

  void _onZoomChanged(bool zoomed) {
    if (zoomed != _zoomed) safeSetState(() => _zoomed = zoomed);
  }

  // A light tap when a swipe runs past the first or last image.
  bool _onGalleryScroll(ScrollNotification n) {
    if (n.depth != 0) return false;
    if (n is ScrollStartNotification) _edgeBuzzed = false;
    final m = n.metrics;
    final dragging = (n is ScrollUpdateNotification && n.dragDetails != null) || (n is OverscrollNotification && n.dragDetails != null);
    final pastEdge = n is OverscrollNotification || m.pixels < m.minScrollExtent || m.pixels > m.maxScrollExtent;
    if (dragging && pastEdge && !_edgeBuzzed) {
      _edgeBuzzed = true;
      HapticFeedback.lightImpact();
    }
    return false;
  }

  void _refresh() {
    unawaited(_loaderFor(_path).load());
    if (isImageFileName(_path)) unawaited(_resolveGallery(fresh: true));
  }

  void _showMenu() {
    showFileDropdownMenu(
      context: context,
      anchorKey: _menuButtonKey,
      items: [
        FileDropdownMenuItem(
          icon: Icons.alternate_email_rounded,
          label: AppLocalizations.of(context).fileViewerXAddToContext,
          onTap: () {
            // Pop the viewer with a result. FilesScreen mirrors the pop so
            // agent_chat (which awaited the original push) receives it.
            context.pop({kFileViewerAddToContextKey: _path});
          },
        ),
        FileDropdownMenuItem(
          icon: Icons.refresh_rounded,
          label: AppLocalizations.of(context).fileViewerXRefresh,
          onTap: _refresh,
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final parent = parentDirOf(_path);
    final gallery = _gallery;
    final position = gallery == null ? null : '${gallery.indexOf(_path) + 1} / ${gallery.length}';
    final subtitle = [if (parent.isNotEmpty) parent, if (position != null) position].join(' · ');
    final current = _loaderFor(_path);
    return Scaffold(
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
        elevation: 0,
        toolbarHeight: subtitle.isNotEmpty ? 72 : 56,
        leading: Align(
          alignment: const AlignmentDirectional(1.0, 0.0),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(10.0),
              onTap: () => context.safePop(),
              child: Container(
                width: 40.0,
                height: 40.0,
                alignment: Alignment.center,
                child: Icon(Icons.chevron_left_rounded, color: theme.secondaryText, size: 24),
              ),
            ),
          ),
        ),
        title: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.titleMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 15, letterSpacing: 0.0)),
            if (subtitle.isNotEmpty) Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0)),
          ],
        ),
        centerTitle: true,
        actions: [
          Align(
            alignment: const AlignmentDirectional(-1.0, 0.0),
            child: Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0, 0, 16, 0),
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  borderRadius: BorderRadius.circular(10.0),
                  onTap: () {
                    HapticFeedback.lightImpact();
                    _showMenu();
                  },
                  child: Container(
                    key: _menuButtonKey,
                    width: 40.0,
                    height: 40.0,
                    alignment: Alignment.center,
                    child: Icon(Icons.more_horiz_rounded, color: theme.secondaryText, size: 24),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            ListenableBuilder(
              listenable: current,
              builder: (context, _) => current.offline
                  ? MachineOfflineBanner(
                      machineId: widget.machineId,
                      detail: current.content != null
                          ? AppLocalizations.of(context).fileViewerXDetailOutdated
                          : AppLocalizations.of(context).fileViewerXDetailNotDownloaded,
                    )
                  : const SizedBox.shrink(),
            ),
            Expanded(
              child: gallery == null
                  ? _page(_path, _name, theme)
                  : Listener(
                      onPointerDown: (e) => _onTouch(e, down: true),
                      onPointerUp: (e) => _onTouch(e, down: false),
                      onPointerCancel: (e) => _onTouch(e, down: false),
                      child: NotificationListener<ScrollNotification>(
                        onNotification: _onGalleryScroll,
                        child: PageView.builder(
                          key: ValueKey(_galleryVersion),
                          controller: _pages,
                          // Zoomed in, a drag pans the image rather than paging.
                          physics: _zoomed || _touches.length > 1 ? const NeverScrollableScrollPhysics() : null,
                          itemCount: gallery.length,
                          onPageChanged: _onPageChanged,
                          itemBuilder: (context, i) => _page(gallery[i], baseNameOf(gallery[i]), theme),
                        ),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _page(String path, String name, FlutterFlowTheme theme) {
    final loader = _loaderFor(path);
    return ListenableBuilder(listenable: loader, builder: (context, _) => _body(loader, path, name, theme));
  }

  Widget _body(FileContentLoader loader, String path, String name, FlutterFlowTheme theme) {
    // Match `_NoCachePlaceholder` alignment so the spinner doesn't visually
    // jump down when the load resolves into the no-cache state.
    if (loader.loading) return const Align(alignment: Alignment(0.0, -0.3), child: CircularProgressIndicator());
    final errorCode = loader.errorCode;
    if (errorCode != null) return _ErrorCard(code: errorCode, theme: theme, onRetry: loader.load);
    final content = loader.content;
    if (content == null) return _NoCachePlaceholder(theme: theme);
    if (content.encoding == 'base64' && content.isBinary) return _ImageView(bytes: loader.imageBytes, truncated: content.truncated, size: content.size, onZoomChanged: _onZoomChanged);
    // Offline the bytes can't be fetched, so a video falls through to the
    // plain placeholder under the offline banner.
    if (content.isVideo && !loader.offline) {
      return FileVideoView(machineId: widget.machineId, cwd: widget.cwd, path: path, name: name, size: content.size, theme: theme, formatBytes: _formatBytes, errorBuilder: (code, onRetry) => _ErrorCard(code: code, theme: theme, onRetry: onRetry));
    }
    if (content.isBinary) {
      // A video the daemon didn't tag with a mime type: it predates video
      // playback, so say how to get it rather than just "no preview".
      final needsUpdate = !loader.offline && _isVideoName(name);
      return _BinaryPlaceholder(
        size: content.size,
        theme: theme,
        detail: needsUpdate ? AppLocalizations.of(context).fileViewerXVideoNeedsUpdate : null,
      );
    }
    return _TextView(content: content, fileName: name, theme: theme);
  }
}

class _NoCachePlaceholder extends StatelessWidget {
  const _NoCachePlaceholder({required this.theme});
  final FlutterFlowTheme theme;

  @override
  Widget build(BuildContext context) {
    // Slight upward bias instead of dead-center so the icon doesn't float in
    // the gap below the offline banner, but still keeps comfortable air above.
    return Align(
      alignment: const Alignment(0.0, -0.3),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(FontAwesomeIcons.fileCircleXmark, size: 42, color: theme.secondaryText),
            const SizedBox(height: 24),
            Text(
              AppLocalizations.of(context).fileViewerXFileNotDownloaded,
              textAlign: TextAlign.center,
              style: theme.titleMedium.override(font: GoogleFonts.sourceSans3(), letterSpacing: 0.0),
            ),
            const SizedBox(height: 4),
            Text(
              AppLocalizations.of(context).fileViewerXReconnectToView,
              textAlign: TextAlign.center,
              style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0),
            ),
          ],
        ),
      ),
    );
  }
}

class _TextView extends StatelessWidget {
  const _TextView({required this.content, required this.fileName, required this.theme});
  final FileContent content;
  final String fileName;
  final FlutterFlowTheme theme;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final lang = _detectLang(fileName);
    final lines = content.content.split('\n');
    final maxLine = lines.length.toString().length;
    // Match the in-chat code block font (markdown_text_builder.dart) so a code
    // snippet rendered in chat reads identically when opened in the viewer.
    final monospace = GoogleFonts.jetBrainsMono(fontSize: 12, color: theme.primaryText, height: 1.4);
    // flutter_highlight bakes a 'root' background into each theme. Strip it so
    // the code surface matches the Scaffold's `secondaryBackground` and tracks
    // light/dark mode without showing a misfit slab.
    final baseTheme = isDark ? atomOneDarkTheme : atomOneLightTheme;
    final tunedTheme = Map<String, TextStyle>.from(baseTheme);
    tunedTheme['root'] = (baseTheme['root'] ?? const TextStyle()).copyWith(
      backgroundColor: theme.secondaryBackground,
      color: theme.primaryText,
    );
    // Line numbers are rendered per-line in a Row so they stay aligned with
    // the visual top of each wrapped line. A single tall Column of numbers
    // would drift the moment any code line wraps. The cost is per-line
    // highlighting (multi-line tokens like raw strings won't span lines).
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: List.generate(lines.length, (i) {
        final line = lines[i];
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Text(
                (i + 1).toString().padLeft(maxLine, ' '),
                style: monospace.copyWith(color: theme.secondaryText),
              ),
            ),
            Expanded(
              child: line.isEmpty
                  ? Text(' ', style: monospace)
                  : HighlightView(
                      line,
                      language: lang,
                      theme: tunedTheme,
                      padding: EdgeInsets.zero,
                      textStyle: monospace,
                    ),
            ),
          ],
        );
      }),
    );
    return Column(
      children: [
        Expanded(
          child: Container(
            color: theme.secondaryBackground,
            // Generous bottom inset so the last line clears the home
            // indicator and gives the eye somewhere to land — Scaffold's
            // SafeArea(bottom: false) hands that responsibility to the body.
            child: SingleChildScrollView(
              padding: const EdgeInsetsDirectional.fromSTEB(8, 8, 8, 64),
              child: body,
            ),
          ),
        ),
        if (content.truncated) _TruncatedBanner(size: content.size, theme: theme),
      ],
    );
  }
}

class _ImageView extends StatelessWidget {
  const _ImageView({required this.bytes, required this.truncated, required this.size, required this.onZoomChanged});
  final Uint8List? bytes;
  final bool truncated;
  final int size;
  final ValueChanged<bool> onZoomChanged;

  @override
  Widget build(BuildContext context) {
    final bytes = this.bytes;
    if (bytes == null) {
      return Center(child: Padding(padding: const EdgeInsets.all(32), child: Text(AppLocalizations.of(context).fileViewerXImageTooLarge)));
    }
    final theme = FlutterFlowTheme.of(context);
    return Column(
      children: [
        Expanded(child: ZoomableImage(bytes: bytes, onZoomChanged: onZoomChanged)),
        if (truncated) _TruncatedBanner(size: size, theme: theme),
      ],
    );
  }
}

class _BinaryPlaceholder extends StatelessWidget {
  const _BinaryPlaceholder({required this.size, required this.theme, this.detail});
  final int size;
  final FlutterFlowTheme theme;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.insert_drive_file_outlined, size: 48, color: theme.secondaryText),
            const SizedBox(height: 12),
            Text(AppLocalizations.of(context).fileViewerXBinaryFile(_formatBytes(size)), style: theme.titleMedium.override(font: GoogleFonts.sourceSans3(), letterSpacing: 0.0)),
            const SizedBox(height: 4),
            Text(detail ?? AppLocalizations.of(context).fileViewerXPreviewNotAvailable, textAlign: TextAlign.center, style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0)),
          ],
        ),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.code, required this.theme, required this.onRetry});
  final String code;
  final FlutterFlowTheme theme;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final msg = _errorMessage(context, code);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline_rounded, size: 48, color: theme.error),
            const SizedBox(height: 12),
            Text(msg, textAlign: TextAlign.center, style: theme.titleMedium.override(font: GoogleFonts.sourceSans3(), letterSpacing: 0.0)),
            const SizedBox(height: 16),
            TextButton(onPressed: onRetry, child: Text(AppLocalizations.of(context).commonRetry)),
          ],
        ),
      ),
    );
  }
}

class _TruncatedBanner extends StatelessWidget {
  const _TruncatedBanner({required this.size, required this.theme});
  final int size;
  final FlutterFlowTheme theme;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: theme.warning.withValues(alpha: 0.15),
        border: Border(top: BorderSide(color: theme.alternate)),
      ),
      child: Text(
        AppLocalizations.of(context).fileViewerXShowingFirstPortion(_formatBytes(size)),
        textAlign: TextAlign.center,
        style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), letterSpacing: 0.0),
      ),
    );
  }
}

String _errorMessage(BuildContext context, String code) {
  final l10n = AppLocalizations.of(context);
  switch (code) {
    case 'path_not_found':
      return l10n.fileViewerXErrPathNotFound;
    case 'permission_denied':
      return l10n.fileViewerXErrPermissionDenied;
    case 'not_a_file':
      return l10n.fileViewerXErrNotAFile;
    case 'outside_project':
      return l10n.fileViewerXErrOutsideProject;
    case 'no_handler':
      return l10n.fileViewerXErrNoHandler;
    case 'not_connected':
    case 'target_disconnected':
      return l10n.fileViewerXErrMachineOffline;
    case 'timeout':
      return l10n.fileViewerXErrTimeout;
    case 'file_changed':
      return l10n.fileViewerXErrFileChanged;
    default:
      return l10n.fileViewerXErrDefault(code);
  }
}

// Mirrors the daemon's `_VIDEO_MIME_TYPES` (vicoa/rpc/file_ops.py).
const Set<String> _videoExtensions = {'mp4', 'm4v', 'mov', 'webm', 'mkv'};

bool _isVideoName(String name) {
  final dot = name.lastIndexOf('.');
  return dot >= 0 && _videoExtensions.contains(name.substring(dot + 1).toLowerCase());
}

String _formatBytes(int bytes) {
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  return '${(bytes / 1024 / 1024).toStringAsFixed(1)} MB';
}

String _detectLang(String name) {
  final lower = name.toLowerCase();
  if (lower.endsWith('.dart')) return 'dart';
  if (lower.endsWith('.py')) return 'python';
  if (lower.endsWith('.js') || lower.endsWith('.jsx')) return 'javascript';
  if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return 'typescript';
  if (lower.endsWith('.go')) return 'go';
  if (lower.endsWith('.rs')) return 'rust';
  if (lower.endsWith('.rb')) return 'ruby';
  if (lower.endsWith('.java')) return 'java';
  if (lower.endsWith('.kt')) return 'kotlin';
  if (lower.endsWith('.swift')) return 'swift';
  if (lower.endsWith('.c') || lower.endsWith('.h')) return 'c';
  if (lower.endsWith('.cc') || lower.endsWith('.cpp') || lower.endsWith('.hpp')) return 'cpp';
  if (lower.endsWith('.cs')) return 'csharp';
  if (lower.endsWith('.sh') || lower.endsWith('.zsh') || lower.endsWith('.bash')) return 'bash';
  if (lower.endsWith('.json')) return 'json';
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'yaml';
  if (lower.endsWith('.toml')) return 'ini';
  if (lower.endsWith('.html')) return 'xml';
  if (lower.endsWith('.svg') || lower.endsWith('.xml')) return 'xml';
  if (lower.endsWith('.md') || lower.endsWith('.markdown') || lower.endsWith('.mdx')) return 'markdown';
  if (lower.endsWith('.css')) return 'css';
  if (lower.endsWith('.scss') || lower.endsWith('.sass')) return 'scss';
  if (lower.endsWith('.sql')) return 'sql';
  return 'plaintext';
}
