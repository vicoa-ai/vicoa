// FilesScreen — pushed full-screen route with Files | Git tabs.
// See `plans/todos/vicoa-app-files-tab.md` §Phase C.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import 'file_viewer/file_viewer_widget.dart' show FileViewerWidget, kFileViewerAddToContextKey;
import 'files_screen_model.dart';
import 'files_tree_view.dart';
import 'git_tab/git_tab_view.dart';
import 'machine_offline_banner.dart';

class FilesScreenWidget extends StatefulWidget {
  const FilesScreenWidget({super.key, required this.machineId, required this.cwd, this.projectName});

  static String routeName = 'FilesScreen';
  static String routePath = '/filesScreen';

  final String machineId;
  final String cwd;
  final String? projectName;

  @override
  State<FilesScreenWidget> createState() => _FilesScreenWidgetState();
}

class _FilesScreenWidgetState extends State<FilesScreenWidget> with SingleTickerProviderStateMixin {
  late final FilesScreenModel _model;
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => FilesScreenModel());
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    _tabs = TabController(length: 2, vsync: this);
    _tabs.addListener(() {
      if (mounted) safeSetState(() {});
      if (_tabs.index == 1) {
        // Lazy-init the Git tab on first activation; subsequent visits are no-ops.
        unawaited(_model.activateGitTab());
      }
      if (!_tabs.indexIsChanging) {
        // Persist the user's tab choice so the next FilesScreen entry
        // opens on the same tab.
        unawaited(_model.persistLastFilesTabIndex(_tabs.index));
      }
    });
    unawaited(_model.initialize(machineId: widget.machineId, cwd: widget.cwd).then((_) {
      if (!mounted) return;
      final saved = _model.lastFilesTabIndex;
      if (saved == null || saved == _tabs.index || saved < 0 || saved >= _tabs.length) {
        return;
      }
      // Animation feels nicer than a hard jump when restoring.
      _tabs.animateTo(saved);
      if (saved == 1) {
        unawaited(_model.activateGitTab());
      }
    }));
  }

  @override
  void dispose() {
    _tabs.dispose();
    _model.dispose();
    super.dispose();
  }

  Future<void> _openFile(String path, String name) async {
    // Awaiting the push lets the viewer return a result map ("Add to context",
    // etc.). Forward it up by popping this screen with the same map so
    // agent_chat — which awaits the original push — gets it.
    final result = await context.pushNamed(
      FileViewerWidget.routeName,
      extra: <String, dynamic>{
        'machineId': widget.machineId,
        'cwd': widget.cwd,
        'path': path,
        'name': name,
      },
    );
    if (!mounted) return;
    if (result is Map && result[kFileViewerAddToContextKey] is String) {
      context.pop(result);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final tab = _model.tab;
    return Scaffold(
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
        elevation: 0,
        titleSpacing: 16.0,
        centerTitle: false,
        title: _SegmentedTabs(
          theme: theme,
          selectedIndex: _tabs.index,
          onSelect: (i) {
            if (i == _tabs.index) return;
            HapticFeedback.lightImpact();
            _tabs.animateTo(i);
          },
        ),
        actions: [
          Align(
            alignment: const AlignmentDirectional(-1.0, 0.0),
            child: Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0, 0, 12, 0),
              child: FlutterFlowIconButton(
                borderColor: theme.alternate,
                borderRadius: 10,
                borderWidth: 1,
                buttonSize: 40,
                icon: Icon(Icons.close_rounded, color: theme.secondaryText, size: 20),
                onPressed: () {
                  HapticFeedback.lightImpact();
                  context.safePop();
                },
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            if (tab != null && tab.isMachineOffline)
              MachineOfflineBanner(machineId: widget.machineId),
            Expanded(
              child: TabBarView(
                controller: _tabs,
                children: [
                  tab == null ? const Center(child: CircularProgressIndicator()) : FilesTreeView(model: tab, onOpenFile: _openFile),
                  _model.gitTab == null
                      ? const Center(child: CircularProgressIndicator())
                      : GitTabView(model: _model.gitTab!),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SegmentedTabs extends StatelessWidget {
  const _SegmentedTabs({required this.theme, required this.selectedIndex, required this.onSelect});
  final FlutterFlowTheme theme;
  final int selectedIndex;
  final ValueChanged<int> onSelect;

  static const _gap = 12.0;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final labels = [l10n.filesScreenTabFiles, l10n.filesScreenTabChanges];
    final children = <Widget>[];
    for (var i = 0; i < labels.length; i++) {
      if (i > 0) children.add(const SizedBox(width: _gap));
      final selected = selectedIndex == i;
      children.add(
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onSelect(i),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
            decoration: BoxDecoration(
              color: selected ? theme.primaryBackground : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              labels[i],
              style: theme.titleMedium.override(
                font: GoogleFonts.sourceSans3(),
                color: selected ? theme.primaryText : theme.secondaryText,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                letterSpacing: 0.0,
              ),
            ),
          ),
        ),
      );
    }
    return Row(mainAxisSize: MainAxisSize.min, children: children);
  }
}

