import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/pages/snack_bar/snack_bar_widget.dart';
import '/pages/machine_detail/machine_detail_widget.dart';
import '/pages/worktrees/worktrees_widget.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/rpc_git.dart';
import '/custom_code/utils/machine_utils.dart' as mutils;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
import 'session_info_sheet_model.dart';
export 'session_info_sheet_model.dart';

class SessionInfoSheetWidget extends StatefulWidget {
  const SessionInfoSheetWidget({
    super.key,
    required this.instanceId,
    required this.instanceData,
    this.onTitleChanged,
  });

  final String instanceId;
  final dynamic instanceData;
  final ValueChanged<String>? onTitleChanged;

  @override
  State<SessionInfoSheetWidget> createState() => _SessionInfoSheetWidgetState();
}

class _SessionInfoSheetWidgetState extends State<SessionInfoSheetWidget>
    with RouteAware {
  late SessionInfoSheetModel _model;
  bool _isTitleFocused = false;
  bool _isDisposed = false;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => SessionInfoSheetModel());

    final initialTitle = _readField('name')?.toString() ?? '';
    _model.originalTitle = initialTitle;
    _model.titleController = TextEditingController(text: initialTitle);
    _model.titleFocusNode = FocusNode();
    _model.titleFocusNode!.addListener(_onTitleFocusChange);

    _loadMachineIfNeeded();
    _loadWorktreeBranchIfNeeded();
  }

  void _onTitleFocusChange() {
    // FocusNode.dispose() fires a focus-loss event synchronously. Skip it so
    // we don't call safeSetState / start an async save after the widget is
    // already being torn down.
    if (_isDisposed || !mounted) return;
    final focused = _model.titleFocusNode?.hasFocus ?? false;
    if (focused != _isTitleFocused) {
      safeSetState(() => _isTitleFocused = focused);
    }
    if (!focused) {
      _saveTitleIfChanged();
    }
  }

  @override
  void dispose() {
    _isDisposed = true;
    _model.titleFocusNode?.removeListener(_onTitleFocusChange);
    routeObserver.unsubscribe(this);
    _model.maybeDispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final route = DebugModalRoute.of(context);
    if (route != null) {
      routeObserver.subscribe(this, route);
    }
    debugLogGlobalProperty(context);
  }

  dynamic _readField(String key) {
    final data = widget.instanceData;
    if (data is Map) {
      return data[key];
    }
    return null;
  }

  String? _projectDisplay() {
    final project = _readField('project')?.toString().trim();
    if (project == null || project.isEmpty) return null;
    return project.endsWith('/')
        ? project.substring(0, project.length - 1)
        : project;
  }

  String _agentTypeDisplay() {
    final raw = _readField('agent_type_name')?.toString().trim() ?? '';
    if (raw.isEmpty) return AppLocalizations.of(context).sessionInfoAgent;
    if (raw.toLowerCase() == 'claude') return 'Claude Code';
    return raw;
  }

  String? _formatDate(dynamic raw) {
    if (raw == null) return null;
    final str = raw.toString();
    if (str.isEmpty) return null;
    final dt = DateTime.tryParse(str);
    if (dt == null) return null;
    final local = dt.toLocal();
    return AppLocalizations.of(context).sessionInfoDateAtTime(
      dateTimeFormat('MMMMEEEEd', local),
      dateTimeFormat('jm', local),
    );
  }

  String? _machineId() {
    final s = _readField('machine_id')?.toString();
    return (s != null && s.isNotEmpty) ? s : null;
  }

  /// Normalized source token (`'app'` / `'terminal'`) used for both the
  /// displayed label and the icon choice; `null` when unknown.
  String? _startedFrom() {
    // source is a top-level field in newer API responses; older responses
    // store it inside instance_metadata as a fallback.
    final topLevel = _readField('source')?.toString();
    final meta = _readField('instance_metadata');
    final metaSource = (meta is Map) ? meta['source']?.toString() : null;
    final s = topLevel ?? metaSource;
    if (s == 'app') return 'app';
    if (s == 'terminal') return 'terminal';
    return null;
  }

  Future<void> _loadMachineIfNeeded() async {
    final mid = _machineId();
    if (mid == null) return;
    final cached = FFAppState().cachedMachines.firstWhere(
      (m) => mutils.machineId(m) == mid,
      orElse: () => null,
    );
    if (cached != null) {
      if (mounted && !_isDisposed) safeSetState(() => _model.resolvedMachine = cached);
      return;
    }
    if (mounted && !_isDisposed) safeSetState(() => _model.isMachineLoading = true);
    final fetched = await actions.apiGetMachineById(mid);
    if (!mounted || _isDisposed) return;
    safeSetState(() {
      _model.resolvedMachine = fetched;
      _model.isMachineLoading = false;
    });
  }

  /// Resolve the worktree's branch over RPC so the worktree row shows the
  /// actual branch (the worktree's identity) rather than just the directory
  /// name. Best-effort: any failure (offline / not a repo / detached) leaves
  /// the row on its directory-name fallback.
  Future<void> _loadWorktreeBranchIfNeeded() async {
    final mid = _machineId();
    final project = _projectDisplay();
    if (mid == null || project == null || project.isEmpty) return;
    try {
      final status = await rpcGitStatus(
        call: actions.VicoaWsClient.instance.callRpc,
        machineId: mid,
        cwd: project,
      );
      if (!mounted || _isDisposed) return;
      safeSetState(() {
        if (!status.detachedHead && status.branch.isNotEmpty) {
          _model.worktreeBranch = status.branch;
        }
        _model.worktreeResolved = true;
      });
    } catch (_) {
      if (!mounted || _isDisposed) return;
      safeSetState(() => _model.worktreeResolved = true);
    }
  }

  Future<void> _saveTitleIfChanged() async {
    // Re-entry guard — focus loss can fire multiple times (e.g. blur from
    // the check button, then another blur from the sheet dismissal). Without
    // this, two API calls and two snackbars fire for the same edit.
    if (_model.isSaving) return;

    final newName = _model.titleController!.text.trim();
    final previousOriginal = _model.originalTitle ?? '';
    if (newName == previousOriginal) return;

    // Optimistically commit so any re-entrant focus event sees the new value
    // and short-circuits at the equality check above.
    _model.originalTitle = newName;

    if (!mounted || _isDisposed) {
      // Widget already gone (e.g. user dismissed sheet immediately after
      // editing). Fire-and-forget the save, no UI updates.
      try {
        await actions.apiUpdateInstanceName(widget.instanceId, newName);
        widget.onTitleChanged?.call(newName);
        if (widget.instanceData is Map) {
          (widget.instanceData as Map)['name'] = newName;
        }
      } catch (e) {
        debugPrint('Background rename failed: $e');
      }
      return;
    }

    safeSetState(() => _model.isSaving = true);

    try {
      final success =
          await actions.apiUpdateInstanceName(widget.instanceId, newName);
      if (success) {
        if (widget.instanceData is Map) {
          (widget.instanceData as Map)['name'] = newName;
        }
        widget.onTitleChanged?.call(newName);
        if (!mounted || _isDisposed) return;
        safeSetState(() => _model.isSaving = false);
        await _showSnack(AppLocalizations.of(context).sessionInfoRenamed);
      } else {
        // Revert on failure
        _model.originalTitle = previousOriginal;
        if (!mounted || _isDisposed) return;
        _model.titleController!.text = previousOriginal;
        safeSetState(() => _model.isSaving = false);
        await _showSnack(AppLocalizations.of(context).sessionInfoRenameFailed);
      }
    } catch (e) {
      debugPrint('Error renaming session: $e');
      _model.originalTitle = previousOriginal;
      if (!mounted || _isDisposed) return;
      _model.titleController!.text = previousOriginal;
      safeSetState(() => _model.isSaving = false);
      await _showSnack(AppLocalizations.of(context).sessionInfoRenameFailed);
    }
  }

  Future<void> _showSnack(String message) async {
    if (!mounted || _isDisposed) return;
    await showModalBottomSheet(
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.transparent,
      context: context,
      builder: (context) {
        return Padding(
          padding: MediaQuery.viewInsetsOf(context),
          child: SnackBarWidget(content: message),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    DebugFlutterFlowModelContext.maybeOf(context)
        ?.parentModelCallback
        ?.call(_model);

    final theme = FlutterFlowTheme.of(context);
    final agentTypeName = _readField('agent_type_name')?.toString();
    final project = _projectDisplay();
    final id = widget.instanceId;
    final createdDisplay = _formatDate(_readField('started_at'));
    final updatedDisplay = _formatDate(
        _readField('latest_message_at') ?? _readField('last_heartbeat_at'));
    final startedFrom = _startedFrom();

    final sheetHeight = MediaQuery.of(context).size.height * 0.8;

    return GestureDetector(
      onTap: () {
        FocusScope.of(context).unfocus();
        FocusManager.instance.primaryFocus?.unfocus();
      },
      child: Padding(
        padding: MediaQuery.viewInsetsOf(context),
        child: Container(
          width: double.infinity,
          height: sheetHeight,
          decoration: BoxDecoration(
            color: theme.secondaryBackground,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(24.0),
              topRight: Radius.circular(24.0),
            ),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.max,
            children: [
              // Drag handle
              Padding(
                padding:
                    const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
                child: Container(
                  width: 50.0,
                  height: 4.0,
                  decoration: BoxDecoration(
                    color: theme.alternate,
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
              ),
              // Header row
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(
                    18.0, 8.0, 16.0, 0.0),
                child: Row(
                  mainAxisSize: MainAxisSize.max,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      AppLocalizations.of(context).sessionInfoSessionInfo,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(
                          fontWeight: theme.bodyMedium.fontWeight,
                          fontStyle: theme.bodyMedium.fontStyle,
                        ),
                        fontSize: 20.0,
                        letterSpacing: 0.0,
                        fontWeight: theme.bodyMedium.fontWeight,
                        fontStyle: theme.bodyMedium.fontStyle,
                      ),
                    ),
                    FlutterFlowIconButton(
                      borderColor: theme.alternate,
                      borderRadius: 10.0,
                      borderWidth: 1.0,
                      buttonSize: 40.0,
                      icon: Icon(
                        Icons.close_rounded,
                        color: theme.secondaryText,
                        size: 20.0,
                      ),
                      onPressed: () async {
                        HapticFeedback.lightImpact();
                        Navigator.pop(context);
                      },
                    ),
                  ],
                ),
              ),
              // Scrollable body
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsetsDirectional.fromSTEB(
                      16.0, 24.0, 16.0, 48.0),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildGroup(theme, [
                        _buildTitleRow(theme),
                        _buildIdRow(theme, id),
                      ]),
                      const SizedBox(height: 16.0),
                      _buildGroup(theme, [
                        if (_machineId() != null) _buildMachineRow(theme),
                        if (project != null)
                          _buildInfoRow(
                            theme,
                            label: AppLocalizations.of(context).sessionInfoProject,
                            value: project,
                            icon: Icons.folder_outlined,
                          ),
                        if (_machineId() != null &&
                            project != null &&
                            project.isNotEmpty)
                          _buildWorktreesRow(theme, _machineId()!, project),
                        _buildAgentRow(theme, agentTypeName),
                        if (startedFrom != null)
                          _buildInfoRow(
                            theme,
                            label: AppLocalizations.of(context).sessionInfoStartedFrom,
                            value: startedFrom == 'terminal'
                                ? AppLocalizations.of(context).sessionInfoSourceTerminal
                                : AppLocalizations.of(context).sessionInfoSourceApp,
                            icon: startedFrom == 'terminal'
                                ? Icons.terminal
                                : Icons.phone_iphone_outlined,
                          ),
                      ]),
                      if (createdDisplay != null || updatedDisplay != null) ...[
                        const SizedBox(height: 16.0),
                        _buildGroup(theme, [
                          if (createdDisplay != null)
                            _buildInfoRow(
                              theme,
                              label: AppLocalizations.of(context).sessionInfoCreated,
                              value: createdDisplay,
                              icon: Icons.access_time_rounded,
                            ),
                          if (updatedDisplay != null)
                            _buildInfoRow(
                              theme,
                              label: AppLocalizations.of(context).sessionInfoLastUpdated,
                              value: updatedDisplay,
                              icon: Icons.update_rounded,
                            ),
                        ]),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTitleRow(FlutterFlowTheme theme) {
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 8.0, 12.0),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(
            Icons.title_rounded,
            color: theme.secondaryText,
            size: 20.0,
          ),
          const SizedBox(width: 14.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  AppLocalizations.of(context).sessionInfoSessionName,
                  style: theme.labelSmall.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.secondaryText,
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                  ),
                ),
                const SizedBox(height: 2.0),
                TextField(
                  controller: _model.titleController,
                  focusNode: _model.titleFocusNode,
                  enabled: !_model.isSaving,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _model.titleFocusNode?.unfocus(),
                  maxLength: 100,
                  maxLengthEnforcement: MaxLengthEnforcement.enforced,
                  buildCounter: (context,
                          {required currentLength,
                          required isFocused,
                          maxLength}) =>
                      null,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.primaryText,
                    fontSize: 16.0,
                    letterSpacing: 0.0,
                  ),
                  decoration: InputDecoration(
                    isDense: true,
                    hintText: AppLocalizations.of(context).sessionInfoNameThisSession,
                    hintStyle: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      color: theme.secondaryText.withValues(alpha: 0.5),
                      fontSize: 16.0,
                      letterSpacing: 0.0,
                    ),
                    contentPadding: EdgeInsets.zero,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    disabledBorder: InputBorder.none,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8.0),
          SizedBox(
            width: 36.0,
            height: 36.0,
            child: Center(
              child: _model.isSaving
                  ? SizedBox(
                      width: 18.0,
                      height: 18.0,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.0,
                        valueColor:
                            AlwaysStoppedAnimation<Color>(theme.primary),
                      ),
                    )
                  : IconButton(
                      padding: EdgeInsets.zero,
                      iconSize: 18.0,
                      icon: Icon(
                        _isTitleFocused
                            ? Icons.check_rounded
                            : Icons.edit_outlined,
                        color: theme.secondaryText.withValues(
                            alpha: _isTitleFocused ? 1.0 : 0.7),
                      ),
                      tooltip: _isTitleFocused
                          ? AppLocalizations.of(context).commonSave
                          : AppLocalizations.of(context).sessionInfoEditTitle,
                      onPressed: () {
                        HapticFeedback.lightImpact();
                        if (_isTitleFocused) {
                          _model.titleFocusNode?.unfocus();
                        } else {
                          _model.titleFocusNode?.requestFocus();
                        }
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGroup(FlutterFlowTheme theme, List<Widget> rows) {
    if (rows.isEmpty) return const SizedBox.shrink();
    final children = <Widget>[];
    for (var i = 0; i < rows.length; i++) {
      if (i > 0) children.add(_buildDivider(theme));
      children.add(rows[i]);
    }
    return Container(
      width: double.infinity,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(14.0),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: children,
      ),
    );
  }

  Widget _buildDivider(FlutterFlowTheme theme) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
      child: Container(
        height: 0.5,
        color: theme.secondaryText.withValues(alpha: 0.12),
      ),
    );
  }

  Widget _buildAgentRow(FlutterFlowTheme theme, String? agentTypeName) {
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 12.0),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        children: [
          SizedBox(
            width: 22.0,
            height: 22.0,
            child: Center(
              child: AgentTypeIconWidget(
                agentTypeName: agentTypeName,
                size: 18.0,
              ),
            ),
          ),
          const SizedBox(width: 12.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  AppLocalizations.of(context).sessionInfoAiAgent,
                  style: theme.labelSmall.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.secondaryText,
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                  ),
                ),
                const SizedBox(height: 2.0),
                Text(
                  _agentTypeDisplay(),
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.primaryText,
                    fontSize: 16.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoRow(
    FlutterFlowTheme theme, {
    required String label,
    required String value,
    required IconData icon,
  }) {
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 12.0),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        children: [
          Icon(
            icon,
            color: theme.secondaryText,
            size: 20.0,
          ),
          const SizedBox(width: 14.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  style: theme.labelSmall.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.secondaryText,
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                  ),
                ),
                const SizedBox(height: 2.0),
                Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.primaryText,
                    fontSize: 16.0,
                    letterSpacing: 0.0,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMachineRow(FlutterFlowTheme theme) {
    final id = _machineId();
    final machine = _model.resolvedMachine;
    final String label;
    if (_model.isMachineLoading) {
      label = AppLocalizations.of(context).commonLoading;
    } else if (machine != null) {
      label = mutils.machineDisplayName(machine);
    } else {
      label = AppLocalizations.of(context).sessionInfoViewMachine;
    }
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          if (id == null) return;
          HapticFeedback.lightImpact();
          final router = GoRouter.of(context);
          Navigator.of(context).pop();
          router.pushNamed(
            MachineDetailWidget.routeName,
            pathParameters: {'machineId': id},
            extra: machine != null
                ? <String, dynamic>{'machineData': machine}
                : null,
          );
        },
        child: Container(
          width: double.infinity,
          padding:
              const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 12.0),
          child: Row(
            mainAxisSize: MainAxisSize.max,
            children: [
              Icon(Icons.dns_rounded, color: theme.secondaryText, size: 20.0),
              const SizedBox(width: 14.0),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      AppLocalizations.of(context).sessionInfoMachine,
                      style: theme.labelSmall.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.secondaryText,
                        fontSize: 13.0,
                        letterSpacing: 0.0,
                      ),
                    ),
                    const SizedBox(height: 2.0),
                    _model.isMachineLoading
                        ? SizedBox(
                            width: 100.0,
                            height: 16.0,
                            child: LinearProgressIndicator(
                              backgroundColor:
                                  theme.secondaryText.withValues(alpha: 0.12),
                              valueColor: AlwaysStoppedAnimation<Color>(
                                  theme.primary.withValues(alpha: 0.5)),
                            ),
                          )
                        : Text(
                            label,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.bodyMedium.override(
                              font: GoogleFonts.sourceSans3(),
                              color: theme.primaryText,
                              fontSize: 16.0,
                              letterSpacing: 0.0,
                            ),
                          ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded,
                  color: theme.secondaryText, size: 22.0),
            ],
          ),
        ),
      ),
    );
  }

  /// Tappable row → the worktrees screen for this session's repo. Shows the
  /// current worktree's directory name; the screen lists the repo's worktrees
  /// and removes managed ones.
  Widget _buildWorktreesRow(
      FlutterFlowTheme theme, String machineId, String project) {
    final name = project.split('/').where((p) => p.isNotEmpty).toList();
    final directoryName = name.isNotEmpty ? name.last : project;
    // Prefer the actual branch (the worktree's identity); fall back to the
    // directory name until it resolves or if it can't be read.
    final branch = _model.worktreeBranch;
    final worktreeName =
        (branch != null && branch.isNotEmpty) ? branch : directoryName;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          final router = GoRouter.of(context);
          Navigator.of(context).pop();
          router.pushNamed(
            WorktreesWidget.routeName,
            extra: <String, dynamic>{
              'machineId': machineId,
              'cwd': project,
              if (name.isNotEmpty) 'projectName': name.last,
            },
          );
        },
        child: Container(
          width: double.infinity,
          padding:
              const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 12.0),
          child: Row(
            mainAxisSize: MainAxisSize.max,
            children: [
              SizedBox(
                width: 20.0,
                height: 20.0,
                child: Center(
                  child: FaIcon(FontAwesomeIcons.codeBranch,
                      color: theme.secondaryText, size: 16.0),
                ),
              ),
              const SizedBox(width: 14.0),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      AppLocalizations.of(context).sessionInfoWorktree,
                      style: theme.labelSmall.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.secondaryText,
                        fontSize: 13.0,
                        letterSpacing: 0.0,
                      ),
                    ),
                    const SizedBox(height: 2.0),
                    Text(
                      worktreeName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        fontSize: 16.0,
                        letterSpacing: 0.0,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded,
                  color: theme.secondaryText, size: 22.0),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildIdRow(FlutterFlowTheme theme, String id) {
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 8.0, 12.0),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        children: [
          Icon(
            Icons.tag_rounded,
            color: theme.secondaryText,
            size: 20.0,
          ),
          const SizedBox(width: 14.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  AppLocalizations.of(context).sessionInfoId,
                  style: theme.labelSmall.override(
                    font: GoogleFonts.sourceSans3(),
                    color: theme.secondaryText,
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                  ),
                ),
                const SizedBox(height: 2.0),
                Text(
                  id,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.robotoMono(),
                    color: theme.primaryText,
                    fontSize: 14.0,
                    letterSpacing: 0.0,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            icon: Icon(
              Icons.content_copy_rounded,
              color: theme.secondaryText,
              size: 20.0,
            ),
            tooltip: AppLocalizations.of(context).sessionInfoCopyId,
            onPressed: () async {
              HapticFeedback.lightImpact();
              final copiedMessage =
                  AppLocalizations.of(context).sessionInfoIdCopied;
              await Clipboard.setData(ClipboardData(text: id));
              await _showSnack(copiedMessage);
            },
          ),
        ],
      ),
    );
  }
}
