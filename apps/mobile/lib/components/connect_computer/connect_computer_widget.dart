import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/session_actions.dart';
import '/custom_code/actions/index.dart' as actions;

class ConnectComputerWidget extends StatelessWidget {
  const ConnectComputerWidget({
    super.key,
    required this.hasSessions,
    this.onSnackBar,
    this.command,
    this.docsUrl,
  });

  final bool hasSessions;
  final void Function(String message)? onSnackBar;
  final String? command;
  final String? docsUrl;

  static const _url = 'https://vicoa.ai/download';

  /// Surface a "copied" toast. Prefer the host page's handler when supplied
  /// (e.g. Home), otherwise fall back to the shared [SnackBarWidget] so copy
  /// still gives feedback on pages that don't pass one (New/Start Session).
  void _notifyCopied(BuildContext context, String message) {
    if (onSnackBar != null) {
      onSnackBar!(message);
    } else {
      SessionActions.showSnack(context, message, waitTime: 1500);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsetsDirectional.fromSTEB(18.0, 12.0, 18.0, 0.0),
      padding: const EdgeInsets.symmetric(horizontal: 32.0, vertical: 32.0),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            FlutterFlowTheme.of(context).primaryBackground,
            FlutterFlowTheme.of(context).accent1.withValues(alpha: 0.05),
          ],
        ),
        borderRadius: BorderRadius.circular(20.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).alternate.withValues(alpha: 0.2),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.02),
            offset: const Offset(0, 4),
            blurRadius: 12.0,
            spreadRadius: 0,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Icon
          Container(
            width: 72.0,
            height: 72.0,
            decoration: BoxDecoration(
              color: FlutterFlowTheme.of(context).primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(36.0),
            ),
            child: Icon(
              Icons.computer_rounded,
              color: FlutterFlowTheme.of(context).primary,
              size: 36.0,
            ),
          ),
          const SizedBox(height: 16.0),

          // Title
          Text(
            AppLocalizations.of(context).connectComputerTitle,
            style: FlutterFlowTheme.of(context).headlineSmall.override(
                  font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
                  color: FlutterFlowTheme.of(context).primaryText,
                  fontSize: 22.0,
                ),
            textAlign: TextAlign.center,
          ),

          if (!hasSessions) ...[
            const SizedBox(height: 8.0),
            Text(
              AppLocalizations.of(context).connectComputerLoginSameAccount,
              style: FlutterFlowTheme.of(context).bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    color: FlutterFlowTheme.of(context).secondaryText,
                    fontSize: 17.0,
                  ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16.0),
            _UrlRow(
              url: _url,
              onCopied: () => _notifyCopied(context, AppLocalizations.of(context).connectComputerLinkCopied),
            ),
            if (docsUrl != null) ...[
              const SizedBox(height: 20.0),
              _DocsLink(url: docsUrl!),
            ],
          ] else ...[
            const SizedBox(height: 20.0),
            if (command != null)
              _CommandRow(command: command!, onCopied: () => _notifyCopied(context, AppLocalizations.of(context).commonCopied))
            else
              _CommandRow(command: 'vicoa daemon', onCopied: () => _notifyCopied(context, AppLocalizations.of(context).commonCopied)),
          ],
          const SizedBox(height: 4.0),
        ],
      ),
    );
  }
}

class _CommandRow extends StatelessWidget {
  const _CommandRow({required this.command, required this.onCopied});

  final String command;
  final VoidCallback onCopied;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(12.0),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '\$',
            style: FlutterFlowTheme.of(context).bodySmall.override(
                  font: GoogleFonts.firaCode(),
                  color: FlutterFlowTheme.of(context).secondaryText,
                  fontSize: 17.0,
                ),
          ),
          const SizedBox(width: 8.0),
          Text(
            command,
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  font: GoogleFonts.firaCode(),
                  color: FlutterFlowTheme.of(context).primaryText,
                  fontSize: 17.0,
                  fontWeight: FontWeight.w500,
                ),
          ),
          const SizedBox(width: 12.0),
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              HapticFeedback.lightImpact();
              Clipboard.setData(ClipboardData(text: command));
              onCopied();
            },
            child: Icon(
              Icons.copy_rounded,
              color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.6),
              size: 16.0,
            ),
          ),
        ],
      ),
    );
  }
}

class _UrlRow extends StatelessWidget {
  const _UrlRow({required this.url, required this.onCopied});

  final String url;
  final VoidCallback onCopied;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14.0),
        onTap: () async {
          HapticFeedback.lightImpact();
          await launchURL(url);
          logFirebaseEvent('HOME_PAGE_GET_STARTED_ON_TAP');
        },
        child: Ink(
          width: double.infinity,
          decoration: BoxDecoration(
            color: FlutterFlowTheme.of(context).primary.withValues(alpha: 0.06),
            borderRadius: BorderRadius.circular(14.0),
            border: Border.all(
              color: FlutterFlowTheme.of(context).primary.withValues(alpha: 0.2),
              width: 1.5,
            ),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 18.0, vertical: 10.0),
          child: Row(
            children: [
              Icon(
                Icons.download_rounded,
                color: FlutterFlowTheme.of(context).primary,
                size: 20.0,
              ),
              const SizedBox(width: 12.0),
              Expanded(
                child: Text(
                  'vicoa.ai/download',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: FlutterFlowTheme.of(context).bodyLarge.override(
                        font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
                        color: FlutterFlowTheme.of(context).primary,
                        fontSize: 17.0,
                      ),
                ),
              ),
              // Copy
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  HapticFeedback.lightImpact();
                  Clipboard.setData(ClipboardData(text: url));
                  onCopied();
                },
                child: Padding(
                  padding: const EdgeInsets.all(6.0),
                  child: Icon(
                    Icons.copy_rounded,
                    color: FlutterFlowTheme.of(context).primary.withValues(alpha: 0.6),
                    size: 20.0,
                  ),
                ),
              ),
              // Share
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () async {
                  HapticFeedback.lightImpact();
                  await actions.share(context, url, null);
                },
                child: Padding(
                  padding: const EdgeInsets.all(6.0),
                  child: Icon(
                    Icons.ios_share_rounded,
                    color: FlutterFlowTheme.of(context).primary.withValues(alpha: 0.6),
                    size: 18.0,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DocsLink extends StatelessWidget {
  const _DocsLink({required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () async {
        HapticFeedback.lightImpact();
        await launchURL(url);
      },
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            AppLocalizations.of(context).connectComputerViewDocs,
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w500),
                  color: FlutterFlowTheme.of(context).secondaryText,
                  fontSize: 15.0,
                ),
          ),
          const SizedBox(width: 4.0),
          Icon(
            Icons.arrow_forward_rounded,
            color: FlutterFlowTheme.of(context).secondaryText,
            size: 15.0,
          ),
        ],
      ),
    );
  }
}
