import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'session_target.dart';

/// The picker's answer: the session every run continues, or a null [target]
/// for a new session each run.
typedef SessionTargetPick = ({AutomationSessionTarget? target});

/// Sessions for a query: recent ones for '', else search matches.
typedef SessionTargetLoader = Future<List<dynamic>> Function(String query);

const _searchDebounce = Duration(milliseconds: 200);
const _recentLimit = 50;
const _searchLimit = 20;

/// The automation editor's "Runs in" picker (the web editor's session picker
/// as a sheet): a new session for every run, the default, or one of your
/// sessions that every run continues. An empty search lists your recent
/// sessions; typing searches all of them by name, folder and message text, as
/// Search does. Styled like [showWorktreePickerSheet]: tap a row to pick it.
///
/// Returns the pick, or null when dismissed.
Future<SessionTargetPick?> showSessionTargetPickerSheet({
  required BuildContext context,
  required String? selectedId,
  @visibleForTesting SessionTargetLoader? loadSessions,
}) {
  return showModalBottomSheet<SessionTargetPick>(
    context: context,
    isScrollControlled: true,
    useSafeArea: false,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _SessionTargetPickerSheet(
      selectedId: selectedId,
      loadSessions: loadSessions ?? _loadSessions,
    ),
  );
}

Future<List<dynamic>> _loadSessions(String query) async {
  final sessions = query.isEmpty
      ? (await actions.apiGetAllAgentInstances(pageSize: _recentLimit))['items']
      : (await actions.apiSearchWorkspace(query, limit: _searchLimit))['sessions'];
  return sessions is List ? sessions : const [];
}

class _SessionTargetPickerSheet extends StatefulWidget {
  const _SessionTargetPickerSheet({required this.selectedId, required this.loadSessions});
  final String? selectedId;
  final SessionTargetLoader loadSessions;

  @override
  State<_SessionTargetPickerSheet> createState() => _SessionTargetPickerSheetState();
}

class _SessionTargetPickerSheetState extends State<_SessionTargetPickerSheet> {
  final _controller = TextEditingController();
  Timer? _debounce;
  // Bumped on every keystroke and load, so a reply to an older query is dropped.
  int _token = 0;
  bool _loading = true;
  List<AutomationSessionTarget> _rows = const [];
  // Kept so clearing the search shows the recent list again without a refetch.
  List<AutomationSessionTarget>? _recent;

  bool get _searching => _controller.text.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _load('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onQueryChanged(String value) {
    _debounce?.cancel();
    _token++;
    final query = value.trim();
    if (query.isEmpty) {
      _load(query);
      return;
    }
    setState(() => _loading = true);
    _debounce = Timer(_searchDebounce, () => _load(query));
  }

  Future<void> _load(String query) async {
    final token = ++_token;
    final recent = _recent;
    if (query.isEmpty && recent != null) {
      setState(() {
        _rows = recent;
        _loading = false;
      });
      return;
    }
    var rows = const <AutomationSessionTarget>[];
    try {
      rows = automationSessionTargets(await widget.loadSessions(query));
      if (query.isEmpty) _recent = rows;
    } catch (e) {
      debugPrint('Session picker load failed: $e');
    }
    if (!mounted || token != _token) return;
    setState(() {
      _rows = rows;
      _loading = false;
    });
  }

  void _pick(AutomationSessionTarget? target) {
    HapticFeedback.lightImpact();
    Navigator.of(context).pop<SessionTargetPick>((target: target));
  }

  String _subtitle(AutomationSessionTarget row) {
    final parts = row.project.split('/').where((p) => p.isNotEmpty).toList();
    final folder = parts.isEmpty ? row.project : parts.last;
    final at = row.at;
    if (at == null) return folder;
    final locale = Localizations.localeOf(context).toString();
    final date = at.year == DateTime.now().year
        ? DateFormat.MMMd(locale).format(at)
        : DateFormat.yMMMd(locale).format(at);
    return '$folder · $date';
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final media = MediaQuery.of(context);
    // A fixed height so the sheet doesn't jump as results come and go; with
    // the keyboard up it rides on top of it and stays clear of the status bar.
    // The sheet route strips the top inset from this MediaQuery, so the status
    // bar's height comes from the view.
    final statusBar = MediaQueryData.fromView(View.of(context)).padding.top;
    final height = math.min(
      media.size.height * 0.75,
      media.size.height - media.viewInsets.bottom - statusBar - 12.0,
    );
    return Padding(
      padding: EdgeInsets.only(bottom: media.viewInsets.bottom),
      child: Container(
        width: double.infinity,
        height: height,
        decoration: BoxDecoration(
          color: theme.secondaryBackground,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(24.0),
            topRight: Radius.circular(24.0),
          ),
        ),
        child: Column(children: [
          _SheetHandle(),
          _SheetHeader(
            title: l10n.automationsRunsIn,
            onClose: () {
              HapticFeedback.lightImpact();
              Navigator.pop(context);
            },
          ),
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(16.0, 8.0, 16.0, 0.0),
            child: _SearchField(controller: _controller, onChanged: _onQueryChanged),
          ),
          Expanded(
            child: ListView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: EdgeInsets.fromLTRB(16.0, 16.0, 16.0, 16.0 + media.padding.bottom),
              children: [
                _TargetRow(
                  icon: Icons.add_rounded,
                  title: l10n.automationsNewSessionEachRun,
                  selected: widget.selectedId == null,
                  onTap: () => _pick(null),
                ),
                const SizedBox(height: 20.0),
                Text(
                  _searching ? l10n.automationsMatchingSessions : l10n.automationsRecentSessions,
                  style: theme.labelMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    fontWeight: FontWeight.w500,
                    color: theme.secondaryText,
                  ),
                ),
                const SizedBox(height: 8.0),
                for (final row in _rows) ...[
                  _TargetRow(
                    icon: Icons.chat_bubble_outline_rounded,
                    title: row.title,
                    subtitle: _subtitle(row),
                    selected: row.id == widget.selectedId,
                    onTap: () => _pick(row),
                  ),
                  const SizedBox(height: 8.0),
                ],
                if (_loading && _rows.isEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 16.0),
                    child: Center(
                      child: SizedBox(
                        width: 22.0,
                        height: 22.0,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.0,
                          valueColor: AlwaysStoppedAnimation<Color>(theme.secondaryText),
                        ),
                      ),
                    ),
                  ),
                if (!_loading && _rows.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8.0),
                    child: Text(
                      _searching ? l10n.automationsNoSessionsMatch : l10n.automationsNoSessionsYet,
                      style: theme.bodySmall.override(
                        font: GoogleFonts.sourceSans3(),
                        fontSize: 13.0,
                        color: theme.secondaryText,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ]),
      ),
    );
  }
}

class _SearchField extends StatelessWidget {
  const _SearchField({required this.controller, required this.onChanged});
  final TextEditingController controller;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      decoration: BoxDecoration(
        color: theme.primaryBackground,
        borderRadius: BorderRadius.circular(16.0),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 2.0),
      child: Row(children: [
        Icon(Icons.search_rounded, size: 18.0, color: theme.secondaryText),
        const SizedBox(width: 10.0),
        Expanded(
          child: TextField(
            controller: controller,
            onChanged: onChanged,
            textInputAction: TextInputAction.search,
            // Session names and folders aren't prose: keep the keyboard from
            // rewriting them (same as the Search page).
            autocorrect: false,
            enableSuggestions: false,
            cursorColor: theme.primary,
            style: theme.bodyMedium.override(
              font: GoogleFonts.sourceSans3(),
              fontSize: 15.0,
              letterSpacing: 0.0,
            ),
            decoration: InputDecoration(
              hintText: AppLocalizations.of(context).automationsSearchSessions,
              hintStyle: theme.bodyMedium.override(
                font: GoogleFonts.sourceSans3(),
                fontSize: 15.0,
                letterSpacing: 0.0,
                color: theme.secondaryText.withValues(alpha: 0.5),
              ),
              border: InputBorder.none,
            ),
          ),
        ),
      ]),
    );
  }
}

/// One choice: "New session each run" or a session. The selected row reads as
/// a soft tinted surface with a check, like the worktree picker's rows.
class _TargetRow extends StatelessWidget {
  const _TargetRow({
    required this.icon,
    required this.title,
    this.subtitle,
    required this.selected,
    required this.onTap,
  });
  final IconData icon;
  final String title;
  final String? subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final accent = theme.primaryText;
    final subtitleText = subtitle;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12.0),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14.0, vertical: 12.0),
        decoration: BoxDecoration(
          color: selected ? accent.withValues(alpha: 0.10) : theme.primaryBackground,
          borderRadius: BorderRadius.circular(12.0),
        ),
        child: Row(children: [
          Icon(icon, size: 18.0, color: selected ? accent : theme.secondaryText),
          const SizedBox(width: 12.0),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    fontWeight: FontWeight.w500,
                    color: selected ? accent : theme.primaryText,
                  ),
                ),
                if (subtitleText != null) ...[
                  const SizedBox(height: 2.0),
                  Text(
                    subtitleText,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.bodySmall.override(
                      font: GoogleFonts.sourceSans3(),
                      fontSize: 12.0,
                      color: theme.secondaryText,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (selected) ...[
            const SizedBox(width: 8.0),
            Icon(Icons.check_rounded, color: accent, size: 18.0),
          ],
        ]),
      ),
    );
  }
}

class _SheetHandle extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
      child: Container(
        width: 50.0,
        height: 4.0,
        decoration: BoxDecoration(
          color: FlutterFlowTheme.of(context).alternate,
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({required this.title, required this.onClose});
  final String title;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 8.0),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        FlutterFlowIconButton(
          borderColor: theme.alternate,
          borderRadius: 10.0,
          borderWidth: 1.0,
          buttonSize: 40.0,
          icon: Icon(Icons.close_rounded, color: theme.secondaryText, size: 20.0),
          onPressed: onClose,
        ),
        Text(
          title,
          style: theme.bodyMedium.override(
            font: GoogleFonts.sourceSans3(fontWeight: FontWeight.w600),
            fontSize: 19.0,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(width: 40.0),
      ]),
    );
  }
}
