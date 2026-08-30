import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/custom_code/utils/machine_utils.dart' as mutils;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/l10n/app_localizations.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/pages/common/machine_actions.dart';
import 'machine_detail_model.dart';
export 'machine_detail_model.dart';

const List<List<String>> _kAgents = [
  ['claude', 'Claude Code'],
  ['codex', 'Codex'],
  ['opencode', 'OpenCode'],
  ['cursor', 'Cursor'],
  ['gemini', 'Gemini'],
  ['copilot', 'Copilot'],
  ['kimi', 'Kimi'],
  ['hermes', 'Hermes'],
];

/// Detail view for one machine: status, agent availability, and system info
/// (incl. Vicoa CLI version + last heartbeat), plus rename and remove. Opened
/// from the machines list or deep-linked from a session's info sheet.
class MachineDetailWidget extends StatefulWidget {
  const MachineDetailWidget({
    super.key,
    required this.machineId,
    this.machineData,
  });

  final String machineId;
  final dynamic machineData;

  static String routeName = 'MachineDetail';
  static String routePath = '/machineDetail/:machineId';

  @override
  State<MachineDetailWidget> createState() => _MachineDetailWidgetState();
}

class _MachineDetailWidgetState extends State<MachineDetailWidget> {
  late MachineDetailModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => MachineDetailModel());
    _model.seed(widget.machineId, widget.machineData);
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    logFirebaseEvent('screen_view',
        parameters: {'screen_name': 'MachineDetail'});
    _model.startRealtime();
    SchedulerBinding.instance.addPostFrameCallback((_) => _model.load());
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  void _popBack() {
    context.pop(_model.renamed ? 'renamed' : null);
  }

  Future<void> _rename() async {
    await MachineActions.rename(
      context,
      machineId: _model.machineId,
      currentName: mutils.machineDisplayName(_model.machine),
      firebaseEventName: 'MACHINE_DETAIL_RENAME',
      onSuccess: (updated) async => _model.applyRename(updated),
    );
  }

  Future<void> _remove() async {
    await MachineActions.remove(
      context,
      machineId: _model.machineId,
      firebaseEventName: 'MACHINE_DETAIL_REMOVE',
      onSuccess: () async {
        if (mounted) context.pop('removed');
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();
    final theme = FlutterFlowTheme.of(context);
    final machine = _model.machine;
    final hasMachine = machine != null;

    return Scaffold(
      key: scaffoldKey,
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
        centerTitle: true,
        toolbarHeight: 72.0,
        leading: Align(
          alignment: const AlignmentDirectional(1.0, 0.0),
          child: FlutterFlowIconButton(
            borderColor: Colors.transparent,
            borderRadius: 10.0,
            buttonSize: 40.0,
            fillColor: theme.primaryBackground,
            icon: Icon(Icons.chevron_left_rounded,
                color: theme.secondaryText, size: 24.0),
            onPressed: () async {
              HapticFeedback.lightImpact();
              _popBack();
            },
          ),
        ),
        title: hasMachine
            ? Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    mutils.machineDisplayName(machine),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: theme.titleLarge.override(
                      font: GoogleFonts.sourceSans3(),
                      letterSpacing: 0.0,
                      fontSize: 18.0,
                    ),
                  ),
                  const SizedBox(height: 3.0),
                  _headerStatus(theme, mutils.isMachineOnlineFromMap(machine)),
                ],
              )
            : Text(
                AppLocalizations.of(context).machineDetailMachine,
                style: theme.titleLarge.override(
                  font: GoogleFonts.sourceSans3(),
                  letterSpacing: 0.0,
                  fontSize: 18.0,
                ),
              ),
        actions: [
          if (hasMachine)
            Align(
              alignment: const AlignmentDirectional(-1.0, 0.0),
              child: Padding(
                padding:
                    const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 12.0, 0.0),
                child: FlutterFlowIconButton(
                  borderColor: Colors.transparent,
                  borderRadius: 10.0,
                  buttonSize: 40.0,
                  fillColor: theme.primaryBackground,
                  icon: Icon(Icons.edit_rounded,
                      color: theme.secondaryText, size: 22.0),
                  onPressed: () async {
                    HapticFeedback.lightImpact();
                    await _rename();
                  },
                ),
              ),
            ),
        ],
        elevation: 0.0,
      ),
      body: SafeArea(
        bottom: false,
        child: (!hasMachine)
            ? _centerState(theme)
            : ListView(
                padding: const EdgeInsets.fromLTRB(16.0, 8.0, 16.0, 32.0),
                children: [
                  if (!mutils.isMachineOnlineFromMap(machine))
                    _offlineCard(theme),
                  _agentsSection(theme, machine),
                  _systemSection(theme, machine),
                  const SizedBox(height: 8.0),
                  _cautionZone(theme),
                ],
              ),
      ),
    );
  }

  // Offline status surface. Uses `_section` so it shares the Agents /
  // System / Caution Zone chrome (title + primary-background pill +
  // 14-radius + alternate border). Single Row inside: icon vertically
  // centred against the Column's full height (matching `_infoRow` /
  // `_agentRow`), then a Column on the right with "Offline" right-aligned
  // and the instruction text underneath. `vicoa daemon` renders as an
  // inline code chip — long-press to copy.
  Widget _offlineCard(FlutterFlowTheme theme) {
    const command = 'vicoa daemon';
    final l10n = AppLocalizations.of(context);
    return _section(theme, l10n.machineDetailStatus, [
      Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(16.0, 14.0, 16.0, 14.0),
        child: Row(
          children: [
            SizedBox(
              width: 24.0,
              height: 24.0,
              child: Center(
                child: Icon(Icons.cloud_off_rounded,
                    size: 20.0, color: theme.secondaryText),
              ),
            ),
            const SizedBox(width: 14.0),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    l10n.machineDetailOffline,
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      color: theme.primaryText,
                      fontSize: 16.0,
                      letterSpacing: 0.0,
                    ),
                  ),
                  const SizedBox(height: 6.0),
                  GestureDetector(
                    onLongPress: () async {
                      HapticFeedback.lightImpact();
                      await Clipboard.setData(
                          const ClipboardData(text: command));
                    },
                    child: Text.rich(
                      TextSpan(
                        style: theme.bodySmall.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText,
                          fontSize: 13.0,
                          letterSpacing: 0.0,
                          lineHeight: 1.4,
                        ),
                        children: [
                          TextSpan(text: l10n.machineDetailRunPrefix),
                          TextSpan(
                            text: command,
                            style: GoogleFonts.jetBrainsMono(
                              fontSize: 12.0,
                              fontWeight: FontWeight.w600,
                              color: theme.primaryText,
                            ),
                          ),
                          TextSpan(text: l10n.machineDetailRunSuffix),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ]);
  }

  Widget _centerState(FlutterFlowTheme theme) {
    if (_model.isLoading) {
      return Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
        ),
      );
    }
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline_rounded,
                size: 48.0, color: theme.secondaryText),
            const SizedBox(height: 12.0),
            Text(
              _model.notFound
                  ? AppLocalizations.of(context).machineDetailNotFound
                  : AppLocalizations.of(context).machineDetailCouldNotLoad,
              style: theme.titleMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.primaryText,
                  letterSpacing: 0.0),
            ),
          ],
        ),
      ),
    );
  }

  Widget _headerStatus(FlutterFlowTheme theme, bool online) {
    final color = online ? theme.success : theme.secondaryText;
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 7.0,
          height: 7.0,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6.0),
        Text(
          online
              ? AppLocalizations.of(context).machineDetailOnline
              : AppLocalizations.of(context).machineDetailOffline,
          style: theme.labelSmall.override(
              font: GoogleFonts.sourceSans3(),
              color: color,
              fontSize: 12.0,
              letterSpacing: 0.0,
              fontWeight: FontWeight.w600),
        ),
      ],
    );
  }

  Widget _agentsSection(FlutterFlowTheme theme, dynamic machine) {
    final agents = mutils.parseAvailableAgents(machine);
    return _section(theme, AppLocalizations.of(context).machineDetailAgents, [
      for (final entry in _kAgents)
        _agentRow(theme, entry[0], entry[1], _stateFor(agents, entry[0])),
    ]);
  }

  Widget _systemSection(FlutterFlowTheme theme, dynamic machine) {
    final l10n = AppLocalizations.of(context);
    return _section(theme, l10n.machineDetailSystem, [
      _infoRow(theme,
          label: l10n.machineDetailHostname,
          value: _valueOr(machine['hostname']),
          icon: Icons.dns_rounded),
      _infoRow(theme,
          label: l10n.machineDetailPlatform,
          value: _valueOr(machine['platform']),
          icon: Icons.memory_rounded),
      _infoRow(theme,
          label: l10n.machineDetailHomeDirectory,
          value: _valueOr(mutils.getMachineHomeDir(machine)),
          icon: Icons.folder_outlined),
      _infoRow(theme,
          label: l10n.machineDetailVicoaCli,
          value: _valueOr(mutils.cliVersion(machine)),
          icon: Icons.terminal_rounded),
      _infoRow(theme,
          label: l10n.machineDetailLastHeartbeat,
          value: _fmt(machine['last_heartbeat_at']),
          icon: Icons.favorite_outline_rounded),
    ]);
  }

  Widget _cautionZone(FlutterFlowTheme theme) {
    final l10n = AppLocalizations.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _section(
          theme,
          l10n.machineDetailCautionZone,
          [
            Material(
              color: Colors.transparent,
              child: InkWell(
                borderRadius: BorderRadius.circular(14.0),
                onTap: () async {
                  HapticFeedback.mediumImpact();
                  await _remove();
                },
                child: Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(
                      16.0, 14.0, 16.0, 14.0),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          l10n.machineDetailRemoveMachine,
                          style: theme.bodyMedium.override(
                              font: GoogleFonts.sourceSans3(),
                              color: theme.error,
                              fontSize: 16.0,
                              letterSpacing: 0.0),
                        ),
                      ),
                      Icon(Icons.delete_rounded,
                          color: theme.error, size: 23.0),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(4.0, 0.0, 4.0, 0.0),
          child: Text(
            l10n.machineDetailRemoveDescription,
            style: theme.labelSmall.override(
              font: GoogleFonts.sourceSans3(),
              color: theme.secondaryText,
              fontSize: 12.0,
              letterSpacing: 0.0,
              lineHeight: 1.4,
            ),
          ),
        ),
      ],
    );
  }

  // --- small building blocks -------------------------------------------------

  Widget _section(FlutterFlowTheme theme, String title, List<Widget> rows) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(4.0, 16.0, 4.0, 8.0),
            child: Text(
              title.toUpperCase(),
              style: theme.labelSmall.override(
                font: GoogleFonts.sourceSans3(),
                color: theme.secondaryText,
                fontSize: 12.0,
                letterSpacing: 0.8,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Container(
            decoration: BoxDecoration(
              color: theme.primaryBackground,
              borderRadius: BorderRadius.circular(14.0),
              border: Border.all(color: theme.alternate, width: 1.0),
            ),
            child: Column(children: rows),
          ),
        ],
      ),
    );
  }

  Widget _infoRow(
    FlutterFlowTheme theme, {
    required String label,
    required String value,
    required IconData icon,
  }) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 14.0, 16.0, 14.0),
      child: Row(
        children: [
          Icon(icon, color: theme.secondaryText, size: 20.0),
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
                      letterSpacing: 0.0),
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
                      letterSpacing: 0.0),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _agentRow(
      FlutterFlowTheme theme, String agentKey, String name, _AgentDisplay d) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 14.0, 16.0, 14.0),
      child: Row(
        children: [
          SizedBox(
            width: 24.0,
            height: 24.0,
            child: Center(
              child: AgentTypeIconWidget(agentTypeName: agentKey, size: 18.0),
            ),
          ),
          const SizedBox(width: 14.0),
          Expanded(
            child: Text(
              name,
              style: theme.bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.primaryText,
                  fontSize: 16.0,
                  letterSpacing: 0.0),
            ),
          ),
          Text(
            d.label,
            style: theme.labelMedium.override(
                font: GoogleFonts.sourceSans3(),
                color: d.color,
                fontSize: 14.0,
                letterSpacing: 0.0),
          ),
        ],
      ),
    );
  }

  _AgentDisplay _stateFor(Map<String, bool>? agents, String agent) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    if (agents == null || agents[agent] == null) {
      return _AgentDisplay(l10n.machineDetailUnknown, theme.secondaryText);
    }
    if (agents[agent] == true) {
      return _AgentDisplay(l10n.machineDetailInstalled, theme.success);
    }
    return _AgentDisplay(l10n.machineDetailAgentNotFound, theme.secondaryText);
  }

  String _valueOr(dynamic v) {
    if (v is String && v.trim().isNotEmpty) return v;
    return AppLocalizations.of(context).machineDetailUnknown;
  }

  String _fmt(dynamic value) {
    final dt = mutils.machineLastHeartbeat(value);
    if (dt == null) return AppLocalizations.of(context).machineDetailUnknown;
    return dateTimeFormat("MMM d, y 'at' h:mm a", dt.toLocal());
  }
}

class _AgentDisplay {
  const _AgentDisplay(this.label, this.color);
  final String label;
  final Color color;
}
