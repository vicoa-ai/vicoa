// Persistent "machine offline" row used by FilesScreen and FileViewer.
// Tapping pushes the machine detail page so the user can act on the
// connection state. Caller-tunable `detail` suffix lets each surface say
// what's stale (cached files, cached file, file-not-cached, …).

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/machine_detail/machine_detail_widget.dart' show MachineDetailWidget;

class MachineOfflineBanner extends StatelessWidget {
  const MachineOfflineBanner({
    super.key,
    required this.machineId,
    this.detail,
  });

  final String machineId;
  // Text after the "Machine offline, " prefix; trailing period is added.
  // Null falls back to the default "files could be outdated" copy.
  final String? detail;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final detailText =
        detail ?? AppLocalizations.of(context).filesXOfflineDetailDefault;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          context.pushNamed(
            MachineDetailWidget.routeName,
            pathParameters: {'machineId': machineId},
          );
        },
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(16, 10, 12, 10),
          decoration: BoxDecoration(
            // Same surface as the host scaffold; hair-line borders above and
            // below carry the visual separation instead of a tint.
            color: theme.secondaryBackground,
            border: Border(
              top: BorderSide(color: theme.alternate, width: 1),
              bottom: BorderSide(color: theme.alternate, width: 1),
            ),
          ),
          child: Row(
            children: [
              Icon(Icons.cloud_off_rounded, size: 18, color: theme.primaryText),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  AppLocalizations.of(context).filesXMachineOffline(detailText),
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15,
                    color: theme.primaryText,
                    letterSpacing: 0.0,
                  ),
                ),
              ),
              Icon(Icons.chevron_right_rounded, size: 18, color: theme.secondaryText),
            ],
          ),
        ),
      ),
    );
  }
}
