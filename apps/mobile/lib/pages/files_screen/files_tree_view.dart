// VS Code-style expandable tree for the Files tab.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C Files tab body.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/file_icon.dart';
import '/custom_code/actions/files_tab_model.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

class FilesTreeView extends StatelessWidget {
  const FilesTreeView({super.key, required this.model, required this.onOpenFile});

  final FilesTabModel model;
  final void Function(String path, String name) onOpenFile;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final rootState = model.listingFor('');
    final rows = _flatten(model);
    return RefreshIndicator(
      onRefresh: model.refresh,
      child: rootState is ListingLoading
          ? ListView(physics: const AlwaysScrollableScrollPhysics(), children: const [Padding(padding: EdgeInsets.only(top: 96), child: Center(child: CircularProgressIndicator()))])
          : rootState is ListingError
              ? _RootErrorList(code: rootState.code, theme: theme, machineId: model.machineId, cwd: model.cwd, onRetry: model.refresh)
              : rows.isEmpty
                  ? ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(top: 64),
                          child: Center(
                            child: Text(
                              AppLocalizations.of(context).filesXNoFiles,
                              style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0),
                            ),
                          ),
                        ),
                      ],
                    )
                  : ListView.builder(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.only(bottom: 32),
                      itemCount: rows.length,
                      itemBuilder: (context, i) => _TreeRow(row: rows[i], theme: theme, onTap: () => _onTap(rows[i]), onOpenFile: onOpenFile),
                    ),
    );
  }

  void _onTap(_Row row) {
    HapticFeedback.lightImpact();
    if (row.isDir) {
      model.toggleExpanded(row.path);
    } else {
      onOpenFile(row.path, row.name);
    }
  }

  static List<_Row> _flatten(FilesTabModel m) {
    final rows = <_Row>[];
    _walk(m, '', 0, rows);
    return rows;
  }

  static void _walk(FilesTabModel m, String path, int depth, List<_Row> out) {
    final state = m.listingFor(path);
    if (state is! ListingLoaded) return;
    for (final entry in state.entries) {
      final childPath = path.isEmpty ? entry.name : '$path/${entry.name}';
      final expanded = m.expanded.contains(childPath);
      out.add(_Row(
        name: entry.name,
        path: childPath,
        isDir: entry.isDir,
        isExpanded: expanded,
        depth: depth,
      ));
      if (entry.isDir && expanded) {
        _walk(m, childPath, depth + 1, out);
      }
    }
  }
}

class _Row {
  _Row({required this.name, required this.path, required this.isDir, required this.isExpanded, required this.depth});
  final String name;
  final String path;
  final bool isDir;
  final bool isExpanded;
  final int depth;
}

class _RootErrorList extends StatelessWidget {
  const _RootErrorList({required this.code, required this.theme, required this.machineId, required this.cwd, required this.onRetry});
  final String code;
  final FlutterFlowTheme theme;
  final String machineId;
  final String cwd;
  final Future<void> Function() onRetry;

  String _message(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    switch (code) {
      case 'path_not_found':
        return l10n.filesXErrPathNotFound;
      case 'permission_denied':
        return l10n.filesXErrPermissionDenied;
      case 'outside_project':
        return l10n.filesXErrOutsideProject;
      case 'not_a_directory':
        return l10n.filesXErrNotADirectory;
      case 'no_handler':
        return l10n.filesXErrNoHandler;
      case 'timeout':
        return l10n.filesXErrTimeout;
      default:
        return l10n.filesXErrDefault(code);
    }
  }

  bool get _isConnectivityError =>
      code == 'not_connected' || code == 'target_disconnected';

  @override
  Widget build(BuildContext context) {
    // Pure connectivity error (= no cache, machine unreachable) gets the
    // file_viewer-style "not loaded on this device" surface — cleaner read
    // than the cwd / machine / Retry list which mostly nags the user.
    // ListView wrapper preserves pull-to-refresh.
    if (_isConnectivityError) {
      return LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: constraints.maxHeight),
              child: Align(
                alignment: const Alignment(0.0, -0.3),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.cloud_off_outlined, color: theme.secondaryText, size: 42),
                      const SizedBox(height: 24),
                      Text(
                        AppLocalizations.of(context).filesXNotLoaded,
                        textAlign: TextAlign.center,
                        style: theme.titleMedium.override(font: GoogleFonts.sourceSans3(), letterSpacing: 0.0),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        AppLocalizations.of(context).filesXReconnectToBrowse,
                        textAlign: TextAlign.center,
                        style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      );
    }
    // Vertically centred like the connectivity-error state above; the
    // ListView wrapper (SingleChildScrollView + min-height) keeps pull-to-refresh.
    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Align(
              alignment: const Alignment(0.0, -0.3),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.folder_off_outlined, color: theme.secondaryText, size: 40),
                    const SizedBox(height: 12),
                    Text(_message(context), textAlign: TextAlign.center, style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 16.0, letterSpacing: 0.0)),
                    const SizedBox(height: 8),
                    Text(AppLocalizations.of(context).filesXProjectLabel(cwd), textAlign: TextAlign.center, style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0)),
                    // Text('machine: $machineId', textAlign: TextAlign.center, style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0)),
                    // const SizedBox(height: 16),
                    // Center(child: TextButton(onPressed: onRetry, child: const Text('Retry'))),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _TreeRow extends StatelessWidget {
  const _TreeRow({required this.row, required this.theme, required this.onTap, required this.onOpenFile});
  final _Row row;
  final FlutterFlowTheme theme;
  final VoidCallback onTap;
  final void Function(String path, String name) onOpenFile;

  @override
  Widget build(BuildContext context) {
    final iconInfo = fileIconFor(row.name, isDir: row.isDir, isExpanded: row.isExpanded);
    // Row starts at 16px so the chevron/icon column lines up with the left
    // edge of the "Files" segmented tab in the AppBar (titleSpacing: 16).
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: EdgeInsetsDirectional.fromSTEB(16.0 + row.depth * 16.0, 8.0, 12.0, 8.0),
        child: Row(
          children: [
            if (row.isDir)
              Icon(
                row.isExpanded ? Icons.keyboard_arrow_down_rounded : Icons.keyboard_arrow_right_rounded,
                size: 18,
                color: theme.secondaryText,
              )
            else
              const SizedBox(width: 18),
            const SizedBox(width: 4),
            // FontAwesome glyphs render visually heavier than Material at the
            // same point size; trim ~3pt so they sit even in the row.
            Icon(
              iconInfo.icon,
              size: iconInfo.icon.fontPackage == 'font_awesome_flutter' ? 15 : 18,
              color: iconInfo.color ?? theme.secondaryText,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                row.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), letterSpacing: 0.0),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
