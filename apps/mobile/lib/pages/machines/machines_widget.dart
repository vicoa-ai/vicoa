import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '/custom_code/utils/machine_utils.dart' as mutils;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/l10n/app_localizations.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/pages/common/session_actions.dart';
import '/pages/machine_detail/machine_detail_widget.dart';
import 'machine_card.dart';
import 'machines_model.dart';
export 'machines_model.dart';

/// Lists the machines a user runs the daemon on, with live online/offline
/// status and agent availability. Entry point: Profile → Machines.
class MachinesWidget extends StatefulWidget {
  const MachinesWidget({super.key});

  static String routeName = 'Machines';
  static String routePath = '/machines';

  @override
  State<MachinesWidget> createState() => _MachinesWidgetState();
}

class _MachinesWidgetState extends State<MachinesWidget> {
  late MachinesModel _model;
  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => MachinesModel());
    _model.setNotify(() {
      if (mounted) safeSetState(() {});
    });
    logFirebaseEvent('screen_view', parameters: {'screen_name': 'Machines'});
    _model.startRealtime();
    SchedulerBinding.instance.addPostFrameCallback((_) => _model.load());
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  Future<void> _openMachine(dynamic machine) async {
    final id = mutils.machineId(machine);
    if (id == null) return;
    HapticFeedback.lightImpact();
    logFirebaseEvent('MACHINES_PAGE_machine_card_ON_TAP');
    final result = await GoRouter.of(context).pushNamed(
      MachineDetailWidget.routeName,
      pathParameters: {'machineId': id},
      extra: <String, dynamic>{'machineData': machine},
    );
    if (result == 'removed' || result == 'renamed') {
      await _model.load();
    }
    if (result == 'removed' && mounted) {
      await SessionActions.showSnack(
          context, AppLocalizations.of(context).machinesMachineRemoved);
    }
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();
    final theme = FlutterFlowTheme.of(context);

    return Scaffold(
      key: scaffoldKey,
      backgroundColor: theme.secondaryBackground,
      appBar: AppBar(
        backgroundColor: theme.secondaryBackground,
        automaticallyImplyLeading: false,
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
              context.safePop();
            },
          ),
        ),
        title: Text(
          AppLocalizations.of(context).machinesTitle,
          style: theme.titleLarge.override(
            font: GoogleFonts.sourceSans3(),
            letterSpacing: 0.0,
          ),
        ),
        centerTitle: true,
        elevation: 0.0,
      ),
      body: SafeArea(bottom: false, child: _buildBody(theme)),
    );
  }

  Widget _buildBody(FlutterFlowTheme theme) {
    final l10n = AppLocalizations.of(context);
    if (_model.isLoading && _model.machines.isEmpty) {
      return Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
        ),
      );
    }
    if (_model.hasError && _model.machines.isEmpty) {
      return _MessageState(
        icon: Icons.cloud_off_rounded,
        title: l10n.machinesCouldNotLoad,
        subtitle: l10n.machinesPullToRefresh,
        onRetry: () => _model.load(),
      );
    }
    if (_model.machines.isEmpty) {
      return _MessageState(
        icon: Icons.computer_rounded,
        title: l10n.machinesNoMachinesYet,
        subtitle: l10n.machinesNoMachinesSubtitle,
        onRetry: () => _model.load(),
      );
    }
    return RefreshIndicator(
      color: theme.primary,
      onRefresh: () => _model.load(),
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.only(top: 8.0, bottom: 32.0),
        itemCount: _model.machines.length,
        itemBuilder: (context, index) {
          final machine = _model.machines[index];
          return MachineCard(
            machine: machine,
            onTap: () => _openMachine(machine),
          );
        },
      ),
    );
  }
}

class _MessageState extends StatelessWidget {
  const _MessageState({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onRetry,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return RefreshIndicator(
      color: theme.primary,
      onRefresh: onRetry,
      child: LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Padding(
              padding: const EdgeInsets.all(32.0),
              child: Align(
                alignment: const Alignment(0.0, -0.35),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(icon, size: 56.0, color: theme.secondaryText),
                    const SizedBox(height: 16.0),
                    Text(
                      title,
                      textAlign: TextAlign.center,
                      style: theme.titleMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        letterSpacing: 0.0,
                      ),
                    ),
                    const SizedBox(height: 8.0),
                    Text(
                      subtitle,
                      textAlign: TextAlign.center,
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.secondaryText,
                        letterSpacing: 0.0,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
