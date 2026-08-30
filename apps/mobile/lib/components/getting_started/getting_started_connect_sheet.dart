import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/auth/supabase_auth/auth_util.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';

const String _kDownloadUrl = 'https://vicoa.ai/download';

/// Bottom sheet for the checklist's "Connect a computer" step — the phone→
/// desktop bridge. Vicoa runs the agent on a computer, so the whole job here is
/// to get the user set up on their desktop. Reuses the existing get-started
/// email flow (one-shot per device via `welcomeGetStartedEmailSent`) plus the
/// 9pm setup reminder, and offers a direct download link.
Future<void> showGettingStartedConnectSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => const _ConnectSheet(),
  );
}

class _ConnectSheet extends StatefulWidget {
  const _ConnectSheet();

  @override
  State<_ConnectSheet> createState() => _ConnectSheetState();
}

class _ConnectSheetState extends State<_ConnectSheet> {
  bool _sending = false;
  bool _sent = false;

  @override
  void initState() {
    super.initState();
    // Reflect the shared one-shot flag on open: if a get-started link was ever
    // sent (here OR via the Welcome-session CTA), show the "already sent" state
    // instead of offering to send another. Reset per account on logout.
    _sent = FFAppState().setting.welcomeGetStartedEmailSent;
  }

  Future<void> _emailLink() async {
    if (_sending || _sent) return;
    HapticFeedback.lightImpact();
    setState(() => _sending = true);

    // One-shot per account: skip the API call once a link has already gone out,
    // so re-opening the sheet (or the Welcome CTA) never spams the user with
    // duplicate emails. The 9pm reminder id is fixed, so re-scheduling just
    // reschedules — no stack.
    final alreadySent = FFAppState().setting.welcomeGetStartedEmailSent;
    bool ok = alreadySent;
    if (!alreadySent) {
      ok = await actions.apiSendEmail('get_started');
      if (ok) {
        FFAppState().updateSettingStruct((e) => e..welcomeGetStartedEmailSent = true);
      }
    }
    unawaited(actions.scheduleSetupReminder());

    if (!mounted) return;
    setState(() {
      _sending = false;
      _sent = ok || alreadySent;
    });
  }

  Future<void> _openDownload() async {
    HapticFeedback.lightImpact();
    await launchURL(_kDownloadUrl);
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final email = currentUserEmail.isNotEmpty
        ? currentUserEmail
        : l10n.welcomeDemoSetupEmailTargetFallback;

    return Container(
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24.0)),
      ),
      padding: EdgeInsets.only(
        left: 20.0,
        right: 20.0,
        top: 12.0,
        bottom: MediaQuery.of(context).viewInsets.bottom +
            MediaQuery.of(context).padding.bottom +
            20.0,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 40.0,
              height: 4.0,
              decoration: BoxDecoration(
                color: theme.alternate,
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
          ),
          const SizedBox(height: 20.0),
          Row(
            children: [
              Container(
                width: 44.0,
                height: 44.0,
                decoration: BoxDecoration(
                  color: theme.primary.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(12.0),
                ),
                child: Icon(Icons.computer_rounded, color: theme.primary, size: 22.0),
              ),
              const SizedBox(width: 12.0),
              Expanded(
                child: Text(
                  l10n.gettingStartedConnectSheetTitle,
                  style: theme.titleMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontWeight: FontWeight.w700,
                    fontSize: 18.0,
                    letterSpacing: 0.0,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14.0),
          Text(
            l10n.gettingStartedConnectSheetBody,
            style: theme.bodyMedium.override(
              font: GoogleFonts.sourceSans3(),
              color: theme.secondaryText,
              fontSize: 15.0,
              letterSpacing: 0.0,
            ),
          ),
          const SizedBox(height: 22.0),
          _PrimaryButton(
            label: _sent ? l10n.gettingStartedEmailSentCta : l10n.gettingStartedEmailLinkCta,
            icon: _sent ? Icons.check_circle_rounded : Icons.mail_outline_rounded,
            busy: _sending,
            onTap: _sent ? null : _emailLink,
          ),
          if (_sent)
            Padding(
              padding: const EdgeInsets.only(top: 10.0, left: 2.0),
              child: Text(
                l10n.gettingStartedEmailSentToast(email),
                style: theme.bodySmall.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.secondaryText,
                  fontSize: 13.0,
                  letterSpacing: 0.0,
                ),
              ),
            ),
          const SizedBox(height: 12.0),
          _SecondaryButton(
            label: l10n.gettingStartedDownloadCta,
            icon: Icons.open_in_new_rounded,
            onTap: _openDownload,
          ),
        ],
      ),
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({
    required this.label,
    required this.icon,
    required this.busy,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool busy;
  final Future<void> Function()? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14.0),
        onTap: onTap == null ? null : () => onTap!(),
        child: Ink(
          decoration: BoxDecoration(
            color: theme.primary,
            borderRadius: BorderRadius.circular(14.0),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 15.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (busy)
                SizedBox(
                  width: 18.0,
                  height: 18.0,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.0,
                    valueColor: AlwaysStoppedAnimation<Color>(theme.info),
                  ),
                )
              else
                Icon(icon, size: 20.0, color: theme.info),
              const SizedBox(width: 8.0),
              Text(
                label,
                style: theme.bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.info,
                  fontWeight: FontWeight.w600,
                  fontSize: 16.0,
                  letterSpacing: 0.0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SecondaryButton extends StatelessWidget {
  const _SecondaryButton({required this.label, required this.icon, required this.onTap});

  final String label;
  final IconData icon;
  final Future<void> Function() onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14.0),
        onTap: () => onTap(),
        child: Ink(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14.0),
            border: Border.all(color: theme.alternate, width: 1.0),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 13.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 18.0, color: theme.secondaryText),
              const SizedBox(width: 8.0),
              Text(
                label,
                style: theme.bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.primaryText,
                  fontWeight: FontWeight.w500,
                  fontSize: 15.0,
                  letterSpacing: 0.0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
