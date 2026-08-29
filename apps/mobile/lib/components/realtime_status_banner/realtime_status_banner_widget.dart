import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

class RealtimeStatusBannerWidget extends StatelessWidget {
  const RealtimeStatusBannerWidget({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 8.0),
      child: Align(
        alignment: Alignment.center,
        child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: BorderRadius.circular(12.0),
          border: Border.all(
            color: theme.secondaryText.withValues(alpha: 0.25),
            width: 0.75,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.04),
              blurRadius: 6.0,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 12.0,
              height: 12.0,
              child: CircularProgressIndicator(
                strokeWidth: 1.5,
                valueColor: AlwaysStoppedAnimation<Color>(
                  theme.secondaryText.withValues(alpha: 0.7),
                ),
              ),
            ),
            const SizedBox(width: 10.0),
            Text(
              AppLocalizations.of(context).realtimeStatusBannerReconnecting,
              style: theme.bodySmall.override(
                font: GoogleFonts.sourceSans3(),
                color: theme.secondaryText,
                fontSize: 14.0,
              ),
            ),
          ],
        ),
        ),
      ),
    );
  }
}
