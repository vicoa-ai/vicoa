import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/app_state.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import 'getting_started_connect_sheet.dart';

/// Persistent home "Get started" checklist. Three activation steps, each
/// DERIVED from live/persisted account state (never a stored per-step flag),
/// so the card can't drift out of the real state and self-heals across
/// reinstalls / devices:
///
///   1. Connect a computer → user has ≥1 registered machine (apiGetMachines)
///   2. Start a session     → home already has ≥1 agent instance (sessionCount)
///   3. Send a message       → activity.total_user_messages > 0 (apiGetActivity)
///
/// Step 3 deliberately uses the SERVER-side, per-account message count, NOT the
/// device-level `hasSentFirstMobileMessage` flag: that flag isn't reset when a
/// new account signs in on the same device (so it wrongly reads "done" for a
/// genuinely new user), and it's mobile-only. The server count is scoped to the
/// account and is never inflated by the local welcome-demo sample chat (those
/// messages never reach the server). A monotonic per-account cache
/// (`gettingStartedActivated`, reset on logout) seeds it so returning activated
/// users don't see the card flash before the fetch resolves.
///
/// As a fast proxy, having ≥3 sessions is treated as "already onboarded": the
/// card marks itself done and skips the (slightly slower) message-count fetch
/// entirely, so a returning power user's card hides instantly on login.
///
/// The steps are nested (a session implies a connected machine; a message
/// implies a session), so network lookups only fire for users who haven't
/// finished — everyone else reads in-memory / persisted state. The card
/// auto-hides once all three are done or the user dismisses it; only the
/// collapsed / dismissed / activated bits are persisted (FFAppState).
class GettingStartedChecklist extends StatefulWidget {
  const GettingStartedChecklist({
    super.key,
    required this.sessionCount,
    required this.onStartSession,
    this.onOpenLatestSession,
    this.onStateChanged,
  });

  /// How many real agent instances the home model currently has. >0 implies
  /// both "connected a computer" and "started a session"; ≥3 is used as a fast
  /// proxy for "already onboarded" so the card can hide without the message
  /// check.
  final int sessionCount;

  /// Runs the home's New Session flow (same as the app-bar +).
  final Future<void> Function() onStartSession;

  /// Opens the most-recent session's chat, if any (null when there is none).
  final Future<void> Function()? onOpenLatestSession;

  /// Called when the card hides itself (dismiss / complete) so home can drop
  /// any surrounding padding.
  final VoidCallback? onStateChanged;

  @override
  State<GettingStartedChecklist> createState() => _GettingStartedChecklistState();
}

class _GettingStartedChecklistState extends State<GettingStartedChecklist> {
  late bool _collapsed;
  late bool _dismissed;
  bool _machineConnected = false;
  bool _messageSent = false;
  bool _checkedStatus = false;

  bool get _hasSession => widget.sessionCount > 0;
  bool get _manySessions => widget.sessionCount >= 3;

  bool get _step1Done => _hasSession || _machineConnected;
  bool get _step2Done => _hasSession;
  // ≥3 sessions is a proxy for "already messaged" — lets the card hide without
  // the activity fetch.
  bool get _step3Done => _messageSent || _manySessions;

  @override
  void initState() {
    super.initState();
    _collapsed = FFAppState().gettingStartedCollapsed;
    _dismissed = FFAppState().gettingStartedDismissed;
    // Optimistic seed from the per-account cache so an already-activated user
    // doesn't see the card flash before the activity fetch confirms.
    _messageSent = FFAppState().gettingStartedActivated;
    _refreshStatus();
  }

  @override
  void didUpdateWidget(covariant GettingStartedChecklist oldWidget) {
    super.didUpdateWidget(oldWidget);
    if ((oldWidget.sessionCount > 0) != _hasSession) _refreshStatus();
  }

  /// Resolve the derived step state from the server, but only the parts we
  /// can't already infer for free: machines (step 1) only when there's no
  /// session, and the per-account message count (step 3) only when it isn't
  /// already known. Skips entirely for done/dismissed users, so the card makes
  /// no network calls once onboarding is finished.
  Future<void> _refreshStatus({bool force = false}) async {
    if (force) _checkedStatus = false;
    if (_dismissed || _checkedStatus) return;

    final machinesFut = (!_hasSession && !_machineConnected)
        ? actions.apiGetMachines()
        : null;
    // Skip the message check when it's already known OR the ≥3-session proxy
    // has marked step 3 done.
    final activityFut = _step3Done ? null : actions.apiGetActivity();
    if (machinesFut == null && activityFut == null) return;
    _checkedStatus = true;

    try {
      if (machinesFut != null) {
        final machines = await machinesFut;
        if (mounted && machines.isNotEmpty) _machineConnected = true;
      }
      if (activityFut != null) {
        final activity = await activityFut;
        final count = (activity['total_user_messages'] as num?)?.toInt() ?? 0;
        if (count > 0) {
          _messageSent = true;
          FFAppState().gettingStartedActivated = true;
        }
      }
      if (mounted) setState(() {});
    } catch (_) {
      // Transient network/auth hiccup → allow a retry on the next rebuild
      // (e.g. after pull-to-refresh).
      _checkedStatus = false;
    }
  }

  void _toggleCollapsed() {
    HapticFeedback.selectionClick();
    setState(() => _collapsed = !_collapsed);
    FFAppState().gettingStartedCollapsed = _collapsed;
  }

  void _dismiss() {
    HapticFeedback.lightImpact();
    FFAppState().gettingStartedDismissed = true;
    setState(() => _dismissed = true);
    widget.onStateChanged?.call();
  }

  Future<void> _onStepTap(int step) async {
    HapticFeedback.lightImpact();
    switch (step) {
      case 1:
        await showGettingStartedConnectSheet(context);
        // A machine may have registered while the sheet was open.
        await _refreshStatus(force: true);
        break;
      case 2:
        await widget.onStartSession();
        break;
      case 3:
        if (widget.onOpenLatestSession != null) {
          await widget.onOpenLatestSession!();
        } else {
          await widget.onStartSession();
        }
        break;
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);

    final steps = <_StepData>[
      _StepData(1, Icons.computer_rounded, l10n.gettingStartedConnectTitle,
          l10n.gettingStartedConnectHint, _step1Done),
      _StepData(2, Icons.terminal_rounded, l10n.gettingStartedSessionTitle,
          l10n.gettingStartedSessionHint, _step2Done),
      _StepData(3, Icons.forum_rounded, l10n.gettingStartedMessageTitle,
          l10n.gettingStartedMessageHint, _step3Done),
    ];
    final total = steps.length;
    final completed = steps.where((s) => s.done).length;
    final allDone = completed == total;

    if (_dismissed || allDone) return const SizedBox.shrink();

    if (_collapsed) return _buildCollapsed(theme, l10n, completed, total);

    final activeIndex = steps.indexWhere((s) => !s.done);

    return Container(
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
        border: Border.all(color: theme.primary.withValues(alpha: 0.20), width: 1.0),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            offset: const Offset(0, 2),
            blurRadius: 8.0,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 8.0, 10.0),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        l10n.gettingStartedTitle,
                        style: theme.titleSmall.override(
                          font: GoogleFonts.sourceSans3(),
                          fontWeight: FontWeight.w700,
                          fontSize: 16.0,
                          letterSpacing: 0.0,
                        ),
                      ),
                      const SizedBox(height: 2.0),
                      Text(
                        l10n.gettingStartedProgress(completed, total),
                        style: theme.bodySmall.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText,
                          fontSize: 12.5,
                          letterSpacing: 0.0,
                        ),
                      ),
                    ],
                  ),
                ),
                _HeaderIconButton(
                  icon: Icons.keyboard_arrow_up_rounded,
                  tooltip: l10n.gettingStartedCollapse,
                  onTap: _toggleCollapsed,
                ),
                _HeaderIconButton(
                  icon: Icons.close_rounded,
                  tooltip: l10n.gettingStartedDismiss,
                  onTap: _dismiss,
                ),
              ],
            ),
          ),
          // Steps
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(6.0, 0.0, 6.0, 6.0),
            child: Column(
              children: [
                for (var i = 0; i < steps.length; i++)
                  _buildStepRow(theme, steps[i], isActive: i == activeIndex),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStepRow(FlutterFlowTheme theme, _StepData s, {required bool isActive}) {
    final highlight = isActive && !s.done;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12.0),
        onTap: () => _onStepTap(s.index),
        child: Container(
          decoration: highlight
              ? BoxDecoration(
                  color: theme.primary.withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(12.0),
                )
              : null,
          padding: const EdgeInsets.symmetric(horizontal: 10.0, vertical: 10.0),
          child: Row(
            children: [
              // Check circle
              Container(
                width: 20.0,
                height: 20.0,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: s.done ? theme.primary : Colors.transparent,
                  border: Border.all(
                    color: s.done
                        ? theme.primary
                        : theme.secondaryText.withValues(alpha: 0.4),
                    width: 1.5,
                  ),
                ),
                child: s.done
                    ? Icon(Icons.check_rounded, size: 13.0, color: theme.info)
                    : null,
              ),
              const SizedBox(width: 12.0),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      s.title,
                      style: theme.bodyMedium
                          .override(
                            font: GoogleFonts.sourceSans3(),
                            fontSize: 15.0,
                            fontWeight: FontWeight.w600,
                            color: s.done ? theme.secondaryText : theme.primaryText,
                            letterSpacing: 0.0,
                          )
                          .copyWith(
                            decoration:
                                s.done ? TextDecoration.lineThrough : TextDecoration.none,
                          ),
                    ),
                    if (!s.done)
                      Padding(
                        padding: const EdgeInsets.only(top: 1.0),
                        child: Text(
                          s.hint,
                          style: theme.bodySmall.override(
                            font: GoogleFonts.sourceSans3(),
                            fontSize: 12.5,
                            color: theme.secondaryText,
                            letterSpacing: 0.0,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 8.0),
              if (!s.done)
                Icon(
                  Icons.chevron_right_rounded,
                  size: 20.0,
                  color: theme.secondaryText.withValues(alpha: 0.6),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCollapsed(
      FlutterFlowTheme theme, AppLocalizations l10n, int completed, int total) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12.0),
        onTap: _toggleCollapsed,
        child: Container(
          decoration: BoxDecoration(
            color: theme.primaryBackground,
            borderRadius: BorderRadius.circular(12.0),
            border: Border.all(color: theme.primary.withValues(alpha: 0.20), width: 1.0),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 11.0),
          child: Row(
            children: [
              SizedBox(
                width: 18.0,
                height: 18.0,
                child: CircularProgressIndicator(
                  value: total == 0 ? 0 : completed / total,
                  strokeWidth: 2.5,
                  backgroundColor: theme.alternate,
                  valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
                ),
              ),
              const SizedBox(width: 10.0),
              Text(
                l10n.gettingStartedTitle,
                style: theme.bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  fontWeight: FontWeight.w600,
                  fontSize: 15.0,
                  letterSpacing: 0.0,
                ),
              ),
              const Spacer(),
              Text(
                '$completed/$total',
                style: theme.bodySmall.override(
                  font: GoogleFonts.sourceSans3(),
                  color: theme.secondaryText,
                  fontSize: 13.0,
                  letterSpacing: 0.0,
                ),
              ),
              const SizedBox(width: 6.0),
              Icon(Icons.keyboard_arrow_down_rounded, size: 20.0, color: theme.secondaryText),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepData {
  const _StepData(this.index, this.icon, this.title, this.hint, this.done);
  final int index;
  final IconData icon;
  final String title;
  final String hint;
  final bool done;
}

class _HeaderIconButton extends StatelessWidget {
  const _HeaderIconButton({required this.icon, required this.tooltip, required this.onTap});

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(8.0),
        onTap: onTap,
        child: Tooltip(
          message: tooltip,
          child: Padding(
            padding: const EdgeInsets.all(6.0),
            child: Icon(icon, size: 20.0, color: theme.secondaryText),
          ),
        ),
      ),
    );
  }
}
