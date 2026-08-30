// FileViewerWidget — pushed full-screen route for inspecting one file.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C File viewer route.

import 'dart:async';
import 'dart:convert';

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

class FileViewerWidget extends StatefulWidget {
  const FileViewerWidget({super.key, required this.machineId, required this.cwd, required this.path, required this.name});

  static String routeName = 'FileViewer';
  static String routePath = '/fileViewer';

  final String machineId;
  final String cwd;
  final String path;
  final String name;

  @override
  State<FileViewerWidget> createState() => _FileViewerWidgetState();
}

// Route result key — agent_chat consumes this to drop `@<path>` into the
// chat input area when the user taps "Add to context".
const String kFileViewerAddToContextKey = 'addToContext';

class _FileViewerWidgetState extends State<FileViewerWidget> {
  FileContent? _content;
  String? _errorCode;
  bool _loading = true;
  // True when the live fetch failed for a connectivity reason; drives the
  // offline banner above the body. Independent of whether we have a cache to
  // fall back on — that's `_content != null`.
  bool _offline = false;
  final GlobalKey _menuButtonKey = GlobalKey();
  FilesCache? _cache;

  // Mirrors FilesTabModel's set — RPC failures matching these get treated as
  // "machine unreachable" rather than a per-file error.
  static const Set<String> _connectivityCodes = {
    'not_connected',
    'target_disconnected',
    'timeout',
    'no_handler',
  };

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    safeSetState(() {
      _loading = true;
      _errorCode = null;
    });
    _cache ??= await FilesCache.open();

    // Fast path: WS already down — surface offline immediately, don't sit on
    // callRpc's wait-then-timeout cycle (~30s).
    if (!actions.VicoaWsClient.instance.isConnected) {
      _renderOfflineFromCache();
      return;
    }

    try {
      final content = await rpcReadFile(
        call: actions.VicoaWsClient.instance.callRpc,
        machineId: widget.machineId,
        cwd: widget.cwd,
        path: widget.path,
      );
      if (!mounted) return;
      // Populate the cache on success so a later offline visit has something
      // to show. Fire-and-forget — UI is already painting.
      unawaited(_cache!.putContent(
        machineId: widget.machineId,
        cwd: widget.cwd,
        path: widget.path,
        content: content.content,
        encoding: content.encoding,
        isBinary: content.isBinary,
        size: content.size,
        truncated: content.truncated,
      ));
      safeSetState(() {
        _content = content;
        _loading = false;
        _offline = false;
      });
    } on FileOpsException catch (e) {
      if (!mounted) return;
      if (_connectivityCodes.contains(e.code)) {
        _renderOfflineFromCache();
      } else {
        safeSetState(() {
          _errorCode = e.code;
          _loading = false;
          _offline = false;
        });
      }
    } catch (_) {
      if (!mounted) return;
      _renderOfflineFromCache();
    }
  }

  void _renderOfflineFromCache() {
    final cached = _cache?.getContent(
      machineId: widget.machineId,
      cwd: widget.cwd,
      path: widget.path,
    );
    if (!mounted) return;
    safeSetState(() {
      _loading = false;
      _offline = true;
      _errorCode = null;
      if (cached != null) {
        _content = FileContent(
          content: cached['content'] as String,
          encoding: cached['encoding'] as String,
          isBinary: cached['is_binary'] as bool,
          size: cached['size'] as int,
          truncated: cached['truncated'] as bool,
        );
      } else {
        _content = null;
      }
    });
  }

  String? _parentDir() {
    final i = widget.path.lastIndexOf('/');
    return i <= 0 ? null : widget.path.substring(0, i);
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
            context.pop({kFileViewerAddToContextKey: widget.path});
          },
        ),
        FileDropdownMenuItem(
          icon: Icons.refresh_rounded,
          label: AppLocalizations.of(context).fileViewerXRefresh,
          onTap: _load,
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final parent = _parentDir();
    return Scaffold(
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
        elevation: 0,
        toolbarHeight: parent != null ? 72 : 56,
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
            Text(widget.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.titleMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 15, letterSpacing: 0.0)),
            if (parent != null) Text(parent, maxLines: 1, overflow: TextOverflow.ellipsis, style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0)),
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
            if (_offline)
              MachineOfflineBanner(
                machineId: widget.machineId,
                detail: _content != null
                    ? AppLocalizations.of(context).fileViewerXDetailOutdated
                    : AppLocalizations.of(context).fileViewerXDetailNotDownloaded,
              ),
            Expanded(child: _body(theme)),
          ],
        ),
      ),
    );
  }

  Widget _body(FlutterFlowTheme theme) {
    // Match `_NoCachePlaceholder` alignment so the spinner doesn't visually
    // jump down when the load resolves into the no-cache state.
    if (_loading) return const Align(alignment: Alignment(0.0, -0.3), child: CircularProgressIndicator());
    if (_errorCode != null) return _ErrorCard(code: _errorCode!, theme: theme, onRetry: _load);
    final content = _content;
    if (content == null) return _NoCachePlaceholder(theme: theme);
    if (content.encoding == 'base64' && content.isBinary) return _ImageView(base64Content: content.content, truncated: content.truncated, size: content.size);
    if (content.isBinary) return _BinaryPlaceholder(size: content.size, theme: theme);
    return _TextView(content: content, fileName: widget.name, theme: theme);
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
  const _ImageView({required this.base64Content, required this.truncated, required this.size});
  final String base64Content;
  final bool truncated;
  final int size;

  @override
  Widget build(BuildContext context) {
    if (base64Content.isEmpty) {
      return Center(child: Padding(padding: const EdgeInsets.all(32), child: Text(AppLocalizations.of(context).fileViewerXImageTooLarge)));
    }
    final bytes = base64Decode(base64Content);
    final theme = FlutterFlowTheme.of(context);
    return Column(
      children: [
        Expanded(
          child: InteractiveViewer(child: Center(child: Image.memory(bytes, fit: BoxFit.contain))),
        ),
        if (truncated) _TruncatedBanner(size: size, theme: theme),
      ],
    );
  }
}

class _BinaryPlaceholder extends StatelessWidget {
  const _BinaryPlaceholder({required this.size, required this.theme});
  final int size;
  final FlutterFlowTheme theme;

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
            Text(AppLocalizations.of(context).fileViewerXPreviewNotAvailable, style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0)),
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
    default:
      return l10n.fileViewerXErrDefault(code);
  }
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
