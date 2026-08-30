import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/utils/machine_utils.dart' as mutils;
import '/flutter_flow/flutter_flow_theme.dart';

/// One row in the machines list: machine name (hostname fallback) and its
/// online/offline status. Tapping opens the detail page.
class MachineCard extends StatelessWidget {
  const MachineCard({super.key, required this.machine, required this.onTap});

  final dynamic machine;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final online = mutils.isMachineOnlineFromMap(machine);
    final name = mutils.machineDisplayName(machine);

    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 6.0, 16.0, 6.0),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          onTap: onTap,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(18.0),
            decoration: BoxDecoration(
              color: theme.primaryBackground,
              borderRadius: BorderRadius.circular(16.0),
              border: Border.all(color: theme.alternate, width: 1.0),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.bodyLarge.override(
                      font: GoogleFonts.sourceSans3(),
                      color: theme.primaryText,
                      fontSize: 17.0,
                      letterSpacing: 0.0,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                const SizedBox(width: 10.0),
                _StatusDot(online: online),
                const SizedBox(width: 6.0),
                Text(
                  online ? 'Online' : 'Offline',
                  style: theme.labelMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: online ? theme.success : theme.secondaryText,
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusDot extends StatelessWidget {
  const _StatusDot({required this.online});
  final bool online;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      width: 7.0,
      height: 7.0,
      decoration: BoxDecoration(
        color: online ? theme.success : theme.secondaryText,
        shape: BoxShape.circle,
      ),
    );
  }
}
