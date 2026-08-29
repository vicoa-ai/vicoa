import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

/// One session/weekly rate-limit window parsed from the usage blob.
class UsageWindow {
  const UsageWindow(
      {required this.id, required this.label, required this.usedPct, this.resetsAt});
  final String id;
  final String label;
  final double usedPct;
  final DateTime? resetsAt;

  /// Parse a single window map — `{id, label, used_pct, resets_at}` — from
  /// either in-band `instance_metadata.usage` or the `fetch-claude-usage` RPC
  /// result, so both paths share one mapping and can't drift. Returns null for
  /// a malformed entry (no map, or no numeric `used_pct`).
  static UsageWindow? fromRaw(dynamic v) {
    final m = _asMap(v);
    final pct = m == null ? null : _asDouble(m['used_pct']);
    if (m == null || pct == null) return null;
    return UsageWindow(
      id: m['id']?.toString() ?? '',
      label: m['label']?.toString() ?? '',
      usedPct: pct.clamp(0, 100).toDouble(),
      resetsAt: _asDate(m['resets_at']),
    );
  }
}

/// Live usage parsed from `instance_metadata.usage` (Claude + Codex). See
/// plans/todos/usage-indicators.md for the canonical contract.
class SessionUsage {
  const SessionUsage(
      {this.usedTokens,
      this.maxTokens,
      this.costUsd,
      this.windows = const [],
      this.creditsRemaining});
  final int? usedTokens;
  final int? maxTokens;
  final double? costUsd;
  final List<UsageWindow> windows;
  final double? creditsRemaining;

  /// Context fill 0-100, or null when the model's window size is unknown.
  double? get contextPct =>
      (usedTokens != null && maxTokens != null && maxTokens! > 0)
          ? (usedTokens! / maxTokens! * 100).clamp(0, 100).toDouble()
          : null;

  /// Highest used_pct across limit windows — the collapsed-chip fallback.
  double? get tightestWindowPct =>
      windows.isEmpty ? null : windows.map((w) => w.usedPct).reduce(math.max);

  bool get hasContext => usedTokens != null || costUsd != null;
  bool get hasAnything =>
      hasContext || windows.isNotEmpty || creditsRemaining != null;

  /// Same usage with its rate-limit [windows] replaced by a fresher set (the
  /// context/cost/credits are kept). Used to overlay the daemon-fetched Claude
  /// windows onto the possibly-stale in-band ones.
  SessionUsage withWindows(List<UsageWindow> freshWindows) => SessionUsage(
        usedTokens: usedTokens,
        maxTokens: maxTokens,
        costUsd: costUsd,
        windows: freshWindows,
        creditsRemaining: creditsRemaining,
      );

  static SessionUsage? fromInstanceData(dynamic instanceData) {
    final meta = _asMap(_index(instanceData, 'instance_metadata'));
    final usage = _asMap(meta?['usage']);
    if (usage == null) return null;
    final context = _asMap(usage['context']);
    final limits = _asMap(usage['limits']);

    final windows = <UsageWindow>[];
    final rawWindows = limits?['windows'];
    if (rawWindows is List) {
      for (final w in rawWindows) {
        final parsed = UsageWindow.fromRaw(w);
        if (parsed != null) windows.add(parsed);
      }
    }
    final credits = _asMap(limits?['credits']);

    final parsed = SessionUsage(
      usedTokens: _asInt(context?['used_tokens']),
      maxTokens: _asInt(context?['max_tokens']),
      costUsd: _asDouble(context?['cost_usd']),
      windows: windows,
      creditsRemaining: credits == null ? null : _asDouble(credits['remaining']),
    );
    return parsed.hasAnything ? parsed : null;
  }
}

/// Signature of `VicoaWsClient.callRpc`, injected so this file stays free of
/// the WS-client action (and remains widget-test friendly).
typedef UsageRpcCaller = Future<Map<String, dynamic>> Function(
    String machineId, String method, Map<String, dynamic> params);

/// Fetch the Claude account's live Session/Weekly rate-limit windows from the
/// machine's daemon (`fetch-claude-usage` RPC). The daemon reads the local
/// Claude Code OAuth credential and calls Anthropic's usage endpoint, so this
/// returns fresher data than the last end-of-turn stamp on
/// `instance_metadata.usage` and works even with no turn having completed yet.
///
/// Best-effort by design: an old daemon (`no_handler`), an offline machine, an
/// API-key-only Claude setup, or any transport/parse failure all resolve to
/// `null` so callers silently keep whatever stale windows they already show.
Future<List<UsageWindow>?> fetchClaudeUsageWindows(
    {required UsageRpcCaller call, required String machineId}) async {
  try {
    final result = await call(machineId, 'fetch-claude-usage', const <String, dynamic>{});
    final limits = _asMap(result['limits']);
    final raw = limits?['windows'];
    if (raw is! List) return null;
    final windows = <UsageWindow>[];
    for (final w in raw) {
      final parsed = UsageWindow.fromRaw(w);
      if (parsed != null) windows.add(parsed);
    }
    // A daemon that routed the call but had no usable data (no_oauth_token,
    // http_401, ...) reports an `error` instead — treated the same as stale.
    return windows.isEmpty ? null : windows;
  } catch (_) {
    // `no_handler` means the daemon predates the RPC (CLI update pending);
    // `target_disconnected`/`timeout` mean the machine is unreachable. All
    // fall back silently to the in-band windows.
    return null;
  }
}

// --- defensive coercion over dynamic JSON --------------------------------

dynamic _index(dynamic obj, String key) {
  if (obj is Map) return obj[key];
  return null;
}

Map? _asMap(dynamic v) => v is Map ? v : null;

int? _asInt(dynamic v) {
  if (v is int) return v;
  if (v is double) return v.round();
  if (v is String) return int.tryParse(v);
  return null;
}

double? _asDouble(dynamic v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

DateTime? _asDate(dynamic v) => v is String ? DateTime.tryParse(v) : null;

// --- formatting ----------------------------------------------------------

String formatUsageTokens(int n) {
  if (n >= 1000000) {
    final m = n / 1000000;
    return '${m == m.roundToDouble() ? m.round() : m.toStringAsFixed(1)}m';
  }
  if (n >= 1000) return '${(n / 1000).round()}k';
  return '$n';
}

String formatUsageCost(double usd) =>
    usd < 0.01 ? '\$${usd.toStringAsFixed(4)}' : '\$${usd.toStringAsFixed(2)}';

const _resetMonths = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Viewer-local clock: English "1:40pm"/"11pm" (minutes dropped on the hour),
// Chinese 24-hour "13:40".
String _formatResetClock(bool zh, DateTime d) {
  if (zh) return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  final ampm = d.hour < 12 ? 'am' : 'pm';
  final h = d.hour % 12 == 0 ? 12 : d.hour % 12;
  final mm = d.minute == 0 ? '' : ':${d.minute.toString().padLeft(2, '0')}';
  return '$h$mm$ampm';
}

String _formatResetDate(bool zh, DateTime d, {required bool includeYear}) {
  if (zh) return includeYear ? '${d.year}年${d.month}月${d.day}日' : '${d.month}月${d.day}日';
  final md = '${_resetMonths[d.month - 1]} ${d.day}';
  return includeYear ? '$md, ${d.year}' : md;
}

/// Absolute reset time in the viewer's local zone: just the clock ("Resets
/// 1:40pm") when it lands today, month + day ("Resets Aug 19 at 11pm") for a
/// later day, with the year added across a year boundary. "Resetting now" once
/// it has elapsed. Returns null when there is no reset timestamp.
String? formatUsageReset(BuildContext context, DateTime? resetsAt,
    {DateTime? now}) {
  if (resetsAt == null) return null;
  final loc = AppLocalizations.of(context);
  final localNow = (now ?? DateTime.now()).toLocal();
  final localReset = resetsAt.toLocal();
  if (!localReset.isAfter(localNow)) return loc.sessionUsageResettingNow;

  final zh = Localizations.localeOf(context).languageCode == 'zh';
  final time = _formatResetClock(zh, localReset);
  final sameDay = localReset.year == localNow.year &&
      localReset.month == localNow.month &&
      localReset.day == localNow.day;
  if (sameDay) return loc.sessionUsageResetsAtTime(time);
  final date = _formatResetDate(zh, localReset,
      includeYear: localReset.year != localNow.year);
  return loc.sessionUsageResetsOnDate(date, time);
}

// The indicator is intentionally monochrome: the ring and every meter use one
// neutral tone (secondaryText) regardless of fill, so a high context/limit
// reading never turns the composer amber or red.

// --- ring painter --------------------------------------------------------

class _UsageRingPainter extends CustomPainter {
  _UsageRingPainter(
      {required this.pct, required this.color, required this.trackColor});
  final double pct;
  final Color color;
  final Color trackColor;

  @override
  void paint(Canvas canvas, Size size) {
    final strokeWidth = size.width * 0.14;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - strokeWidth) / 2;
    final track = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..color = trackColor;
    canvas.drawCircle(center, radius, track);

    final sweep = 2 * math.pi * (pct.clamp(0, 100) / 100);
    final progress = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..color = color;
    canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius), -math.pi / 2, sweep,
        false, progress);
  }

  @override
  bool shouldRepaint(_UsageRingPainter old) =>
      old.pct != pct || old.color != color || old.trackColor != trackColor;
}

/// Compact context-window ring + tap-to-open usage sheet for the composer.
/// Renders nothing until the session reports usage, so it self-hides for
/// agents/sessions that don't (ACP, or before the first turn).
///
/// When [fetchLimits] is provided (Claude sessions on a reachable machine),
/// opening the sheet fetches a fresh rate-limit snapshot from the machine's
/// daemon and overlays it on the (possibly stale) in-band windows — the
/// in-band ones only refresh at end of turn, so they go stale on idle
/// sessions. [fetchOnMount] additionally fetches as soon as the widget mounts
/// (for surfaces with no in-band usage yet, e.g. a new-session composer).
class ChatUsageIndicator extends StatefulWidget {
  const ChatUsageIndicator(
      {super.key, required this.usage, this.fetchLimits, this.fetchOnMount = false});
  final SessionUsage? usage;

  /// Fetches fresh Claude rate-limit windows from the machine's daemon;
  /// null = keep the in-band windows (non-Claude agents, offline machines).
  final Future<List<UsageWindow>?> Function()? fetchLimits;

  /// Also fetch immediately on mount, not just when the sheet opens.
  final bool fetchOnMount;

  @override
  State<ChatUsageIndicator> createState() => _ChatUsageIndicatorState();
}

// Client-side spacing between daemon fetches. The daemon caches for 30s too;
// this just avoids pointless RPC round-trips on rapid re-taps.
const Duration _fetchInterval = Duration(seconds: 30);

class _ChatUsageIndicatorState extends State<ChatUsageIndicator> {
  // Fresh windows from the daemon override the (possibly stale) in-band ones.
  List<UsageWindow>? _freshWindows;
  DateTime? _lastFetchAt;

  // The open bottom sheet is a separate route built once, so it observes the
  // usage snapshot / fetching flag through these notifiers to update live as a
  // daemon fetch lands. Mutated ONLY from async fetch results and the tap
  // handler — never during build — so notifying their listeners can never
  // collide with the framework's build phase. The composer ring does NOT use
  // them: it reads `_effectiveUsage` inline (see build), because a parent
  // rebuild would otherwise have to push a fresh value through a notifier
  // mid-build, which marks a listener dirty during build (setState-in-build).
  final ValueNotifier<SessionUsage?> _sheetUsage =
      ValueNotifier<SessionUsage?>(null);
  final ValueNotifier<bool> _fetching = ValueNotifier<bool>(false);

  @override
  void initState() {
    super.initState();
    if (widget.fetchOnMount) _refreshLimits();
  }

  @override
  void dispose() {
    _sheetUsage.dispose();
    _fetching.dispose();
    super.dispose();
  }

  // In-band usage with the daemon-fetched windows (if any) overlaid. Recomputed
  // on demand so the composer ring reflects the latest `widget.usage` on every
  // parent rebuild for free (build runs after didUpdateWidget) — no notifier,
  // no state write during build.
  SessionUsage? get _effectiveUsage {
    final base = widget.usage;
    final fresh = _freshWindows;
    return fresh == null
        ? base
        : (base ?? const SessionUsage()).withWindows(fresh);
  }

  // No cancellation on purpose (mirrors the web): a late resolution is
  // harmless — we guard `mounted` before touching state. Throttled so rapid
  // re-taps don't re-probe the daemon (on macOS a failed Keychain read can pop
  // a GUI prompt). Runs only from a tap handler or initState, never build.
  Future<void> _refreshLimits() async {
    final fetch = widget.fetchLimits;
    if (fetch == null) return;
    final now = DateTime.now();
    if (_lastFetchAt != null && now.difference(_lastFetchAt!) < _fetchInterval) {
      return;
    }
    _lastFetchAt = now;
    _fetching.value = true;
    try {
      final windows = await fetch();
      if (windows != null && mounted) {
        setState(() => _freshWindows = windows); // refresh the composer ring
        _sheetUsage.value = _effectiveUsage; // and any open sheet
      }
    } finally {
      if (mounted) _fetching.value = false;
    }
  }

  void _showUsageSheet(BuildContext context) {
    // Seed the sheet with the current snapshot before it builds; a pending
    // fetch pushes a fresher one through `_sheetUsage` while it stays open.
    _sheetUsage.value = _effectiveUsage;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => _UsageSheet(usage: _sheetUsage, fetching: _fetching),
    );
  }

  @override
  Widget build(BuildContext context) {
    final u = _effectiveUsage;
    if (u == null || !u.hasAnything) return const SizedBox.shrink();
    final theme = FlutterFlowTheme.of(context);
    final triggerPct = u.contextPct ?? u.tightestWindowPct;
    final color = theme.secondaryText;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(20.0),
        onTap: () {
          HapticFeedback.lightImpact();
          FocusManager.instance.primaryFocus?.unfocus();
          // Refresh in the background; the sheet reflects it live.
          _refreshLimits();
          _showUsageSheet(context);
        },
        child: Container(
          width: 40.0,
          height: 40.0,
          alignment: Alignment.center,
          // Ring only in the composer — no percentage text; the breakdown
          // lives in the bottom sheet. A 40x40 box with the circular InkWell
          // (radius 20) makes the tap highlight match the icon buttons.
          child: triggerPct != null
              ? SizedBox(
                  width: 18.0,
                  height: 18.0,
                  child: CustomPaint(
                    painter: _UsageRingPainter(
                      pct: triggerPct,
                      color: color,
                      trackColor: theme.secondaryText.withValues(alpha: 0.2),
                    ),
                  ),
                )
              : (u.usedTokens != null
                  ? Text(formatUsageTokens(u.usedTokens!),
                      style: theme.bodyMedium.override(
                          color: theme.secondaryText, fontSize: 12.0))
                  : const SizedBox.shrink()),
        ),
      ),
    );
  }
}

class _UsageSheet extends StatelessWidget {
  const _UsageSheet({required this.usage, required this.fetching});
  // Listenables so the sheet updates in place when a daemon fetch lands after
  // it has already opened.
  final ValueListenable<SessionUsage?> usage;
  final ValueListenable<bool> fetching;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final loc = AppLocalizations.of(context);

    return Container(
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20.0)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(20.0, 12.0, 20.0, 20.0),
          child: ValueListenableBuilder<SessionUsage?>(
            valueListenable: usage,
            builder: (context, u, _) {
              final usageVal = u ?? const SessionUsage();
              final contextPct = usageVal.contextPct;
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Center(
                    child: Container(
                      width: 36.0,
                      height: 4.0,
                      decoration: BoxDecoration(
                        color: theme.secondaryText.withValues(alpha: 0.3),
                        borderRadius: BorderRadius.circular(2.0),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16.0),
                  // Title + a subtle "Refreshing…" note while a daemon fetch
                  // is in flight (Claude sessions only).
                  Row(children: [
                    Expanded(
                      child: Text(loc.sessionUsageTitle,
                          style: theme.titleSmall.override(fontSize: 16.0)),
                    ),
                    ValueListenableBuilder<bool>(
                      valueListenable: fetching,
                      builder: (context, isFetching, _) => isFetching
                          ? Text(loc.sessionUsageRefreshing,
                              style: theme.bodySmall.override(
                                  color:
                                      theme.secondaryText.withValues(alpha: 0.6),
                                  fontSize: 12.0))
                          : const SizedBox.shrink(),
                    ),
                  ]),
                  if (usageVal.hasContext) ...[
                    const SizedBox(height: 16.0),
                    // "Context Window" + percentage on one row, above the bar.
                    Row(children: [
                      Expanded(
                        child: Text(loc.sessionUsageContext,
                            style: theme.bodyMedium.override(
                                color: theme.secondaryText, fontSize: 14.0)),
                      ),
                      if (contextPct != null)
                        Text('${contextPct.round()}%',
                            style: theme.bodyMedium.override(
                                color: theme.secondaryText, fontSize: 14.0)),
                    ]),
                    if (contextPct != null) ...[
                      const SizedBox(height: 6.0),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(3.0),
                        child: LinearProgressIndicator(
                          value: contextPct / 100,
                          minHeight: 4.0,
                          backgroundColor:
                              theme.secondaryText.withValues(alpha: 0.12),
                          valueColor: AlwaysStoppedAnimation<Color>(
                              theme.secondaryText),
                        ),
                      ),
                    ],
                    const SizedBox(height: 6.0),
                    // Tokens used (left) and session cost (right) share a row.
                    Row(children: [
                      Expanded(
                        child: Text(_contextDetail(loc, usageVal),
                            style: theme.bodySmall.override(
                                color: theme.secondaryText, fontSize: 12.0)),
                      ),
                      if (usageVal.costUsd != null)
                        Text(
                            loc.sessionUsageSessionCost(
                                formatUsageCost(usageVal.costUsd!)),
                            style: theme.bodySmall.override(
                                color:
                                    theme.secondaryText.withValues(alpha: 0.7),
                                fontSize: 12.0)),
                    ]),
                  ],
                  for (final w in usageVal.windows) ...[
                    const SizedBox(height: 16.0),
                    _WindowRow(window: w),
                  ],
                  if (usageVal.creditsRemaining != null) ...[
                    const SizedBox(height: 16.0),
                    Row(children: [
                      Expanded(
                        child: Text(loc.sessionUsageCredits,
                            style: theme.bodyMedium.override(
                                color: theme.secondaryText, fontSize: 14.0)),
                      ),
                      Text(
                          loc.sessionUsageCreditsLeft(
                              formatUsageCost(usageVal.creditsRemaining!)),
                          style: theme.bodyMedium.override(fontSize: 14.0)),
                    ]),
                  ],
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  String _contextDetail(AppLocalizations loc, SessionUsage usage) {
    final used = formatUsageTokens(usage.usedTokens ?? 0);
    if (usage.maxTokens != null) {
      return '$used / ${formatUsageTokens(usage.maxTokens!)} ${loc.sessionUsageTokensSuffix}';
    }
    return '$used ${loc.sessionUsageTokensSuffix}';
  }
}

class _WindowRow extends StatelessWidget {
  const _WindowRow({required this.window});
  final UsageWindow window;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final pct = window.usedPct.clamp(0, 100).toDouble();
    final tone = theme.secondaryText;
    final reset = formatUsageReset(context, window.resetsAt);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(
            child: Text(window.label,
                style: theme.bodyMedium
                    .override(color: theme.secondaryText, fontSize: 13.0)),
          ),
          Text('${pct.round()}%',
              style: theme.bodyMedium.override(color: tone, fontSize: 13.0)),
          if (reset != null) ...[
            const SizedBox(width: 8.0),
            Text(reset,
                style: theme.bodySmall.override(
                    color: theme.secondaryText.withValues(alpha: 0.6),
                    fontSize: 11.0)),
          ],
        ]),
        const SizedBox(height: 6.0),
        ClipRRect(
          borderRadius: BorderRadius.circular(3.0),
          child: LinearProgressIndicator(
            value: pct / 100,
            minHeight: 4.0,
            backgroundColor: theme.secondaryText.withValues(alpha: 0.12),
            valueColor: AlwaysStoppedAnimation<Color>(tone),
          ),
        ),
      ],
    );
  }
}
