import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '/flutter_flow/flutter_flow_theme.dart';

class EmptyFilterStateWidget extends StatelessWidget {
  const EmptyFilterStateWidget({
    super.key,
    required this.statusLabel,
  });

  final String statusLabel;

  @override
  Widget build(BuildContext context) {
    final label = statusLabel.isEmpty ? 'No Sessions' : 'No $statusLabel Sessions';
    return Container(
      width: double.infinity,
      margin: const EdgeInsetsDirectional.fromSTEB(18.0, 12.0, 18.0, 0.0),
      padding: const EdgeInsets.symmetric(horizontal: 32.0, vertical: 40.0),
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primaryBackground,
        borderRadius: BorderRadius.circular(20.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).alternate.withValues(alpha: 0.2),
          width: 1.0,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.inbox_rounded,
            color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.4),
            size: 48.0,
          ),
          const SizedBox(height: 12.0),
          Text(
            label,
            style: FlutterFlowTheme.of(context).titleMedium.override(
                  font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500),
                  color: FlutterFlowTheme.of(context).secondaryText,
                  fontSize: 18.0,
                ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
