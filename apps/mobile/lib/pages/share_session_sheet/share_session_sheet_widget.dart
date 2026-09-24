import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/l10n/app_localizations.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import '/pages/snack_bar/snack_bar_widget.dart';
import 'share_option_picker.dart';
import 'share_session_sheet_model.dart';

export 'share_session_sheet_model.dart';

/// The one Share entry point for a session, with two sections that do
/// genuinely different things:
///
/// * **Link** — a live, revocable URL. Whoever opens it follows the session as
///   it runs and keeps seeing what happens next, until the link is revoked.
/// * **Export** — the existing "pick messages, share as text or a file" flow:
///   a copy of the transcript, taken now, that never changes again.
///
/// They sit in one sheet because "share" is one intention on a phone, and
/// separate because sending someone a snapshot is not the same promise as
/// sending them a window. [onExport] is null where the caller has no messages
/// loaded (the session list), and then only the Link section is drawn — a link
/// needs the session's id and nothing else.
///
/// Settings apply as you change them: each control PATCHes the link it is
/// showing, so editing never mints a second URL and the one already sent out
/// keeps working. A switch that needed a separate Save would read as broken.
class ShareSessionSheetWidget extends StatefulWidget {
  const ShareSessionSheetWidget({
    super.key,
    required this.instanceId,
    this.sessionTitle,
    this.onExport,
  });

  final String instanceId;
  final String? sessionTitle;

  /// Opens the message-selection → share-as-text/file flow. Null hides the
  /// whole Export section.
  final Future<void> Function()? onExport;

  @override
  State<ShareSessionSheetWidget> createState() => _ShareSessionSheetWidgetState();
}

class _ShareSessionSheetWidgetState extends State<ShareSessionSheetWidget> with RouteAware {
  late ShareSessionSheetModel _model;

  /// The link whose URL was last copied, so the row can say so briefly.
  String? _copiedId;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ShareSessionSheetModel());
    logFirebaseEvent('SHARE_SESSION_SHEET_open');
    _load();
  }

  @override
  void dispose() {
    routeObserver.unsubscribe(this);
    _model.maybeDispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final route = DebugModalRoute.of(context);
    if (route != null) routeObserver.subscribe(this, route);
    debugLogGlobalProperty(context);
  }

  // --- data ---------------------------------------------------------------

  Future<void> _load() async {
    try {
      final rows = await actions.apiListShareLinks(widget.instanceId);
      final links = rows.whereType<Map>().map((r) => Map<String, dynamic>.from(r)).toList()
        ..sort((a, b) => (b['created_at']?.toString() ?? '').compareTo(a['created_at']?.toString() ?? ''));
      if (!mounted) return;
      safeSetState(() {
        _model.links = links;
        _model.loadFailed = false;
      });
    } catch (_) {
      if (!mounted) return;
      safeSetState(() {
        _model.links = null;
        _model.loadFailed = true;
      });
    }
  }

  Future<void> _create() async {
    if (_model.creating) return;
    safeSetState(() => _model.creating = true);
    logFirebaseEvent('SHARE_SESSION_SHEET_create_link');
    final link = await actions.apiCreateSessionShareLink(widget.instanceId);
    if (!mounted) return;
    safeSetState(() {
      _model.creating = false;
      if (link != null) _model.links = [link, ...(_model.links ?? [])];
    });
    if (link == null) {
      await _snack(AppLocalizations.of(context).shareLinkCreateFailed);
      return;
    }
    // On the clipboard, ready to paste, and nothing further. The OS share
    // sheet used to open itself here, which put a full-screen prompt in front
    // of someone who may only have wanted the link to exist; Share is one tap
    // away below when sending it is the intent.
    await _copy(link);
  }

  /// Apply one setting to the current link. Optimistic: the row moves at once
  /// and snaps back if the server refuses, which is what a switch should do.
  Future<void> _patch(
    Map<String, dynamic> link,
    Map<String, dynamic> optimistic, {
    String? audience,
    bool? showOwner,
    bool? showBranch,
    int? expiresInDays,
    bool clearExpiry = false,
  }) async {
    if (_model.busy) return;
    final before = Map<String, dynamic>.from(link);
    safeSetState(() {
      _model.busy = true;
      link.addAll(optimistic);
    });
    final updated = await actions.apiUpdateShareLink(
      link['id']?.toString() ?? '',
      audience: audience,
      showOwner: showOwner,
      showBranch: showBranch,
      expiresInDays: expiresInDays,
      clearExpiry: clearExpiry,
    );
    if (!mounted) return;
    safeSetState(() {
      _model.busy = false;
      if (updated != null) {
        link
          ..clear()
          ..addAll(updated);
      } else {
        link
          ..clear()
          ..addAll(before);
      }
    });
    if (updated == null) await _snack(AppLocalizations.of(context).shareLinkUpdateFailed);
  }

  Future<void> _revoke(Map<String, dynamic> link) async {
    final l10n = AppLocalizations.of(context);
    final confirmed = await showDialog<bool>(
          context: context,
          barrierDismissible: false,
          builder: (_) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConfirmDialogWidget(
              title: l10n.shareLinkRevokeTitle,
              content: l10n.shareLinkRevokeContent,
            ),
          ),
        ) ??
        false;
    if (!confirmed || !mounted) return;
    logFirebaseEvent('SHARE_SESSION_SHEET_revoke_link');
    HapticFeedback.mediumImpact();
    safeSetState(() => _model.busy = true);
    final ok = await actions.apiRevokeShareLink(link['id']?.toString() ?? '');
    if (!mounted) return;
    safeSetState(() {
      _model.busy = false;
      if (ok) _model.links = (_model.links ?? []).where((l) => l['id'] != link['id']).toList();
    });
    if (!ok) await _snack(AppLocalizations.of(context).shareLinkRevokeFailed);
  }

  // --- small actions ------------------------------------------------------

  Future<void> _snack(String message) async {
    if (!mounted) return;
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.transparent,
      builder: (_) => Padding(
        padding: MediaQuery.viewInsetsOf(context),
        child: SnackBarWidget(content: message),
      ),
    );
  }

  Future<void> _copy(Map<String, dynamic> link) async {
    HapticFeedback.lightImpact();
    await Clipboard.setData(ClipboardData(text: _urlOf(link)));
    if (!mounted) return;
    safeSetState(() => _copiedId = link['id']?.toString());
    await _snack(AppLocalizations.of(context).shareLinkCopied);
  }

  Future<void> _shareNative(String url) async {
    HapticFeedback.lightImpact();
    await actions.share(context, url, widget.sessionTitle);
  }

  String _urlOf(Map<String, dynamic> link) => actions.shareLinkUrl(link['token']?.toString() ?? '');

  // --- formatting ---------------------------------------------------------

  String _audienceLabel(String audience) {
    final l10n = AppLocalizations.of(context);
    return audience == 'authenticated' ? l10n.shareLinkAudienceAuthenticated : l10n.shareLinkAudiencePublic;
  }

  String _expiryLabel(Map<String, dynamic> link) {
    final l10n = AppLocalizations.of(context);
    final raw = link['expires_at']?.toString();
    if (raw == null || raw.isEmpty) return l10n.shareLinkNeverExpires;
    final when = DateTime.tryParse(raw)?.toLocal();
    if (when == null) return l10n.shareLinkNeverExpires;
    if (when.isBefore(DateTime.now())) return l10n.shareLinkExpired;
    return l10n.shareLinkExpiresOn(dateTimeFormat('MMMd', when));
  }

  /// "Anyone with the link · Never expires · 3 views".
  String _facts(Map<String, dynamic> link) {
    final l10n = AppLocalizations.of(context);
    final views = (link['view_count'] as num?)?.toInt() ?? 0;
    return [
      _audienceLabel(link['audience']?.toString() ?? 'public'),
      _expiryLabel(link),
      l10n.shareLinkViews(views),
    ].join(' · ');
  }

  // --- settings controls --------------------------------------------------

  Future<void> _pickAudience(Map<String, dynamic> link) async {
    final l10n = AppLocalizations.of(context);
    final current = link['audience']?.toString() ?? 'public';
    final picked = await showShareOptionPicker<String>(
      context,
      title: l10n.shareLinkAudience,
      current: current,
      options: [
        ShareOption(value: 'public', label: l10n.shareLinkAudiencePublic, icon: Icons.public_rounded),
        ShareOption(value: 'authenticated', label: l10n.shareLinkAudienceAuthenticated, icon: Icons.lock_outline_rounded),
      ],
    );
    if (picked == null || picked == current || !mounted) return;
    await _patch(link, {'audience': picked}, audience: picked);
  }

  Future<void> _pickExpiry(Map<String, dynamic> link) async {
    final l10n = AppLocalizations.of(context);
    // `expires_at` is a date; the picker speaks in "in N days" and cannot tell
    // which option minted an existing deadline. 0 stands for "never", and a
    // link that already expires simply matches none of the rows — picking one
    // always restates the deadline from now.
    final picked = await showShareOptionPicker<int>(
      context,
      title: l10n.shareLinkExpiry,
      current: (link['expires_at']?.toString().isEmpty ?? true) ? 0 : -1,
      options: [
        ShareOption(value: 0, label: l10n.shareLinkExpiryNever),
        for (final days in const [1, 7, 30, 90])
          ShareOption(value: days, label: l10n.shareLinkExpiryInDays(days)),
      ],
    );
    if (picked == null || !mounted) return;
    await _patch(
      link,
      {'expires_at': picked == 0 ? null : DateTime.now().toUtc().add(Duration(days: picked)).toIso8601String()},
      expiresInDays: picked == 0 ? null : picked,
      clearExpiry: picked == 0,
    );
  }

  // --- build --------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    DebugFlutterFlowModelContext.maybeOf(context)?.parentModelCallback?.call(_model);

    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);

    return Padding(
      padding: MediaQuery.viewInsetsOf(context),
      child: Container(
        width: double.infinity,
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
        decoration: BoxDecoration(
          color: theme.secondaryBackground,
          borderRadius: const BorderRadius.only(topLeft: Radius.circular(24.0), topRight: Radius.circular(24.0)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
              child: Container(
                width: 50.0,
                height: 4.0,
                decoration: BoxDecoration(color: theme.alternate, borderRadius: BorderRadius.circular(8.0)),
              ),
            ),
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(18.0, 8.0, 16.0, 0.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    l10n.shareLinkSheetTitle,
                    style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 20.0, letterSpacing: 0.0),
                  ),
                  FlutterFlowIconButton(
                    borderColor: theme.alternate,
                    borderRadius: 10.0,
                    borderWidth: 1.0,
                    buttonSize: 40.0,
                    icon: Icon(Icons.close_rounded, color: theme.secondaryText, size: 20.0),
                    onPressed: () async {
                      HapticFeedback.lightImpact();
                      Navigator.pop(context);
                    },
                  ),
                ],
              ),
            ),
            Flexible(
              child: SingleChildScrollView(
                // The last row needs its own clearance: a content-sized sheet
                // ends where the content does, which may be under the home
                // indicator.
                padding: EdgeInsetsDirectional.fromSTEB(16.0, 20.0, 16.0, 24.0 + MediaQuery.paddingOf(context).bottom),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _sectionLabel(theme, l10n.shareLinkSectionLink),
                    const SizedBox(height: 8.0),
                    ..._linkSection(theme, l10n),
                    if (widget.onExport != null) ...[
                      const SizedBox(height: 28.0),
                      _sectionLabel(theme, l10n.shareLinkSectionExport),
                      const SizedBox(height: 8.0),
                      _group(theme, [
                        _actionRow(
                          theme,
                          icon: Icons.ios_share_rounded,
                          label: l10n.shareLinkExportRow,
                          subtitle: l10n.shareLinkExportSubtitle,
                          onTap: () async {
                            Navigator.pop(context);
                            await widget.onExport!();
                          },
                        ),
                      ]),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _linkSection(FlutterFlowTheme theme, AppLocalizations l10n) {
    final link = _model.current;

    if (_model.loadFailed) {
      return [
        _group(theme, [
          _actionRow(
            theme,
            icon: Icons.error_outline_rounded,
            label: l10n.shareLinkLoadFailed,
            subtitle: l10n.commonRetry,
            onTap: () async {
              safeSetState(() => _model.loadFailed = false);
              await _load();
            },
          ),
        ]),
      ];
    }

    if (_model.links == null) {
      return [
        _group(theme, [
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(16.0, 18.0, 16.0, 18.0),
            child: Row(
              children: [
                SizedBox(
                  width: 16.0,
                  height: 16.0,
                  child: CircularProgressIndicator(strokeWidth: 2.0, color: theme.secondaryText),
                ),
                const SizedBox(width: 12.0),
                Text(
                  l10n.commonLoading,
                  style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), color: theme.secondaryText, letterSpacing: 0.0),
                ),
              ],
            ),
          ),
        ]),
      ];
    }

    if (link == null) {
      return [
        Text(
          l10n.shareLinkDescription,
          style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 13.0, color: theme.secondaryText, letterSpacing: 0.0),
        ),
        const SizedBox(height: 14.0),
        _primaryButton(
          theme,
          label: _model.creating ? l10n.shareLinkCreating : l10n.shareLinkCreate,
          icon: Icons.link_rounded,
          onPressed: _model.creating ? null : _create,
        ),
      ];
    }

    return [
      _group(theme, [_urlRow(theme, l10n, link)]),
      const SizedBox(height: 16.0),
      _group(theme, [
        _disclosureRow(
          theme,
          icon: Icons.tune_rounded,
          label: l10n.shareLinkSettings,
          open: _model.settingsOpen,
          onTap: () => safeSetState(() => _model.settingsOpen = !_model.settingsOpen),
        ),
        if (_model.settingsOpen) ...[
          _divider(theme),
          _valueRow(theme, label: l10n.shareLinkAudience, value: _audienceLabel(link['audience']?.toString() ?? 'public'), onTap: () => _pickAudience(link)),
          _divider(theme),
          _valueRow(theme, label: l10n.shareLinkExpiry, value: _expiryLabel(link), onTap: () => _pickExpiry(link)),
          _divider(theme),
          _switchRow(
            theme,
            label: l10n.shareLinkShowOwner,
            value: link['show_owner'] == true,
            onChanged: (v) => _patch(link, {'show_owner': v}, showOwner: v),
          ),
          _divider(theme),
          _switchRow(
            theme,
            label: l10n.shareLinkShowBranch,
            value: link['show_branch'] == true,
            onChanged: (v) => _patch(link, {'show_branch': v}, showBranch: v),
          ),
        ],
        _divider(theme),
        _actionRow(theme, icon: Icons.link_off_rounded, label: l10n.shareLinkRevoke, onTap: () => _revoke(link)),
      ]),
      const SizedBox(height: 16.0),
      // The section's one filled button, and the last thing under it: tapping
      // the URL copies, so the OS share sheet is the other way out, not a
      // second version of the same action next to it.
      _primaryButton(theme, label: l10n.commonShare, icon: Icons.ios_share_rounded, onPressed: () => _shareNative(_urlOf(link))),
      if (_model.others.isNotEmpty) ...[
        const SizedBox(height: 16.0),
        _group(theme, [
          _disclosureRow(
            theme,
            icon: Icons.link_rounded,
            label: l10n.shareLinkOtherLinks(_model.others.length),
            open: _model.othersOpen,
            onTap: () => safeSetState(() => _model.othersOpen = !_model.othersOpen),
          ),
          if (_model.othersOpen)
            for (final other in _model.others) ...[_divider(theme), _otherLinkRow(theme, other)],
        ]),
      ],
    ];
  }

  // --- pieces -------------------------------------------------------------

  Widget _sectionLabel(FlutterFlowTheme theme, String text) => Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(2.0, 0.0, 0.0, 0.0),
        child: Text(
          text,
          style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 13.0, color: theme.secondaryText, letterSpacing: 0.0),
        ),
      );

  Widget _group(FlutterFlowTheme theme, List<Widget> rows) => Container(
        width: double.infinity,
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(color: theme.primaryBackground, borderRadius: BorderRadius.circular(14.0)),
        child: Column(mainAxisSize: MainAxisSize.min, children: rows),
      );

  Widget _divider(FlutterFlowTheme theme) => Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 0.0, 0.0),
        child: Container(height: 0.5, color: theme.secondaryText.withValues(alpha: 0.12)),
      );

  Widget _urlRow(FlutterFlowTheme theme, AppLocalizations l10n, Map<String, dynamic> link) {
    final url = _urlOf(link);
    final copied = _copiedId == link['id']?.toString();
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _copy(link),
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 16.0),
          child: Row(
            children: [
              Expanded(
                // The whole URL, scheme included: this is the string being
                // sent to someone, and a half-written one reads as a label
                // rather than something you can check before you send it.
                child: Text(
                  url,
                  style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 15.0, color: theme.primaryText, letterSpacing: 0.0),
                  maxLines: 3,
                ),
              ),
              const SizedBox(width: 12.0),
              Icon(copied ? Icons.check_rounded : Icons.content_copy_rounded, size: 18.0, color: theme.secondaryText),
            ],
          ),
        ),
      ),
    );
  }

  Widget _otherLinkRow(FlutterFlowTheme theme, Map<String, dynamic> link) {
    final copied = _copiedId == link['id']?.toString();
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 8.0, 12.0),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  _urlOf(link),
                  style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 13.0, color: theme.primaryText, letterSpacing: 0.0),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2.0),
                Text(
                  _facts(link),
                  style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 11.0, color: theme.secondaryText, letterSpacing: 0.0),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          IconButton(
            icon: Icon(copied ? Icons.check_rounded : Icons.content_copy_rounded, size: 18.0, color: theme.secondaryText),
            onPressed: () => _copy(link),
            tooltip: AppLocalizations.of(context).commonCopy,
          ),
          IconButton(
            icon: Icon(Icons.link_off_rounded, size: 18.0, color: theme.secondaryText),
            onPressed: () => _revoke(link),
            tooltip: AppLocalizations.of(context).shareLinkRevoke,
          ),
        ],
      ),
    );
  }

  Widget _actionRow(
    FlutterFlowTheme theme, {
    required IconData icon,
    required String label,
    String? subtitle,
    required Future<void> Function() onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () async {
          HapticFeedback.lightImpact();
          await onTap();
        },
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 14.0, 16.0, 14.0),
          child: Row(
            children: [
              Icon(icon, size: 18.0, color: theme.secondaryText),
              const SizedBox(width: 14.0),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      label,
                      style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 16.0, color: theme.primaryText, letterSpacing: 0.0),
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 2.0),
                      Text(
                        subtitle,
                        style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 12.0, color: theme.secondaryText, letterSpacing: 0.0),
                      ),
                    ],
                  ],
                ),
              ),
              Icon(Icons.keyboard_arrow_right_rounded, size: 22.0, color: theme.secondaryText),
            ],
          ),
        ),
      ),
    );
  }

  Widget _disclosureRow(
    FlutterFlowTheme theme, {
    required IconData icon,
    required String label,
    required bool open,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 14.0, 16.0, 14.0),
          child: Row(
            children: [
              Icon(icon, size: 18.0, color: theme.secondaryText),
              const SizedBox(width: 14.0),
              Expanded(
                child: Text(
                  label,
                  style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 16.0, color: theme.primaryText, letterSpacing: 0.0),
                ),
              ),
              Icon(open ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded, size: 22.0, color: theme.secondaryText),
            ],
          ),
        ),
      ),
    );
  }

  Widget _valueRow(
    FlutterFlowTheme theme, {
    required String label,
    required String value,
    required Future<void> Function() onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _model.busy
            ? null
            : () async {
                HapticFeedback.lightImpact();
                await onTap();
              },
        child: Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(48.0, 13.0, 16.0, 13.0),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 15.0, color: theme.primaryText, letterSpacing: 0.0),
                ),
              ),
              Text(
                value,
                style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 13.0, color: theme.secondaryText, letterSpacing: 0.0),
              ),
              Icon(Icons.keyboard_arrow_right_rounded, size: 20.0, color: theme.secondaryText),
            ],
          ),
        ),
      ),
    );
  }

  Widget _switchRow(
    FlutterFlowTheme theme, {
    required String label,
    required bool value,
    required Future<void> Function(bool) onChanged,
  }) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(48.0, 4.0, 12.0, 4.0),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 15.0, color: theme.primaryText, letterSpacing: 0.0),
            ),
          ),
          Switch.adaptive(
            value: value,
            onChanged: _model.busy
                ? null
                : (v) async {
                    HapticFeedback.lightImpact();
                    await onChanged(v);
                  },
          ),
        ],
      ),
    );
  }

  Widget _primaryButton(
    FlutterFlowTheme theme, {
    required String label,
    required IconData icon,
    required Future<void> Function()? onPressed,
  }) {
    return FFButtonWidget(
      onPressed: onPressed,
      text: label,
      icon: Icon(icon, size: 18.0, color: Colors.white),
      options: FFButtonOptions(
        width: double.infinity,
        height: 52.0,
        padding: const EdgeInsetsDirectional.fromSTEB(24.0, 0.0, 24.0, 0.0),
        iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
        color: theme.primary,
        textStyle: theme.titleSmall.override(
          font: GoogleFonts.sourceSans3(fontWeight: FontWeight.normal),
          color: Colors.white,
          fontSize: 17.0,
          letterSpacing: 0.0,
          fontWeight: FontWeight.normal,
        ),
        elevation: 0.0,
        borderSide: const BorderSide(color: Colors.transparent, width: 1.0),
        borderRadius: BorderRadius.circular(14.0),
        disabledColor: theme.disabledButton,
      ),
    );
  }
}
