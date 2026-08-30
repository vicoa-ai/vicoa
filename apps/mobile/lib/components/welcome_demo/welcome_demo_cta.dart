import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

/// The two call-to-action buttons rendered at the end of the welcome demo
/// conversation. Unlike the OPTIONS / AskUserQuestion paths, tapping these
/// triggers local actions (send an email / expand the waitlist question)
/// rather than messaging an agent — the wiring lives in the chat widget.
class WelcomeDemoCta extends StatelessWidget {
  const WelcomeDemoCta({
    super.key,
    required this.onSetupCli,
    required this.onNoComputer,
    this.busy = false,
  });

  /// "I'll set up the CLI on my computer" — emails a get-started link.
  final Future<void> Function() onSetupCli;

  /// "I don't have a computer with me" — expands the in-chat waitlist question.
  final Future<void> Function() onNoComputer;

  /// Disables both buttons (e.g. while the email request is in flight).
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0, 12, 0, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          _CtaButton(
            icon: Icons.computer_rounded,
            title: l10n.welcomeDemoSetupCliTitle,
            subtitle: l10n.welcomeDemoSetupCliSubtitle,
            filled: true,
            onTap: busy ? null : onSetupCli,
          ),
          const SizedBox(height: 16),
          _CtaButton(
            icon: Icons.phone_iphone_rounded,
            title: l10n.welcomeDemoNoComputerTitle,
            subtitle: l10n.welcomeDemoNoComputerSubtitle,
            filled: false,
            onTap: busy ? null : onNoComputer,
          ),
        ],
      ),
    );
  }
}

class _CtaButton extends StatelessWidget {
  const _CtaButton({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.filled,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final bool filled;
  final Future<void> Function()? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final accent = theme.primary;
    final bg = filled ? accent.withValues(alpha: 0.10) : Colors.transparent;
    final borderColor =
        filled ? accent.withValues(alpha: 0.35) : theme.secondaryText.withValues(alpha: 0.3);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap == null
            ? null
            : () {
                HapticFeedback.lightImpact();
                onTap!();
              },
        child: Ink(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: borderColor, width: filled ? 1.2 : 0.8),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Icon(icon, size: 22, color: filled ? accent : theme.secondaryText),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: theme.bodyMedium.override(
                        color: theme.primaryText,
                        fontWeight: FontWeight.w600,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.arrow_forward_rounded,
                size: 18,
                color: theme.secondaryText.withValues(alpha: 0.7),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
