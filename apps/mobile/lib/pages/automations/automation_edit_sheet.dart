import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';

import '/app_state.dart';
import '/backend/agent_catalog.dart';
import '/custom_code/actions/index.dart' as actions;
import '/custom_code/utils/automation_utils.dart' as autils;
import '/custom_code/utils/keyboard_utils.dart';
import '/custom_code/utils/machine_utils.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '/pages/common/mention_prompt_field.dart';
import '/pages/common/session_actions.dart';
import '/pages/new_session/components/agent_config_sheet.dart';
import '/pages/new_session/components/directory_picker_sheet.dart';
import '/pages/tasks/task_pickers.dart' show showAnchoredSingleSelect, PickerOption;
import 'automation_controls.dart';
import 'automation_l10n.dart';
import 'automation_run_history.dart';
import 'automation_time_picker.dart';

/// Bottom-sheet editor for creating and editing an automation. Returns the
/// request-body map ({title, prompt, machine_id, directory, session_config,
/// schedule_kind, run_at?, frequency?, timezone}) on save, or null if
/// dismissed. Does NOT call the API — the caller decides create vs. update.
Future<Map<String, dynamic>?> showAutomationEditSheet({
  required BuildContext context,
  dynamic automation,
  required List<dynamic> machines,
  required AgentCatalog catalog,
  ValueChanged<String>? onOpenInstance,
}) {
  return showModalBottomSheet<Map<String, dynamic>>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    enableDrag: true,
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
      child: _AutomationEditSheet(
        automation: automation,
        machines: machines,
        catalog: catalog,
        onOpenInstance: onOpenInstance,
      ),
    ),
  );
}

class _AutomationEditSheet extends StatefulWidget {
  const _AutomationEditSheet({
    required this.automation,
    required this.machines,
    required this.catalog,
    required this.onOpenInstance,
  });

  final dynamic automation;
  final List<dynamic> machines;
  final AgentCatalog catalog;
  final ValueChanged<String>? onOpenInstance;

  @override
  State<_AutomationEditSheet> createState() => _AutomationEditSheetState();
}

class _AutomationEditSheetState extends State<_AutomationEditSheet> {
  late final TextEditingController _titleController;
  late final TextEditingController _promptController;
  String? _machineId;
  late String _directory;
  late SessionConfig _sessionConfig;
  late autils.AutomationScheduleDraft _draft;
  bool _titleError = false;

  // Live machine list, seeded from the passed-in snapshot then kept fresh via
  // `machine-update` WS events + a re-eval ticker. Without this the machine's
  // `last_heartbeat_at` freezes at open time, so `isMachineOnlineFromMap` (90s
  // window vs. now) flips an online machine to "Offline" while the sheet sits
  // open — mirrors the machines list page (MachinesModel).
  late List<dynamic> _machines;
  StreamSubscription<Map<String, dynamic>>? _machineSub;
  Timer? _machineTicker;

  final _repeatKey = GlobalKey();
  final _unitKey = GlobalKey();

  bool get _isEditing => widget.automation != null;

  dynamic get _machine =>
      _machineId == null ? null : _machineForId(_machineId!);

  dynamic _machineForId(String id) => _machines.firstWhere(
        (m) => machineId(m) == id,
        orElse: () => null,
      );

  @override
  void initState() {
    super.initState();
    _machines = List<dynamic>.from(widget.machines);
    final a = widget.automation;
    _titleController =
        TextEditingController(text: a != null ? autils.automationTitle(a) : '');
    _promptController = TextEditingController(
        text: a != null ? autils.automationPrompt(a) : '');
    if (a != null) {
      _machineId = autils.automationMachineId(a);
      _directory = autils.automationDirectory(a);
      _sessionConfig =
          SessionConfig.fromJson(autils.automationSessionConfig(a))
              .reconcileAgainst(widget.catalog);
      _draft = autils.automationToDraft(a);
    } else {
      final defaultMachine = _machines.firstWhere(
        (m) => isMachineOnlineFromMap(m),
        orElse: () => _machines.isNotEmpty ? _machines.first : null,
      );
      _machineId = defaultMachine == null ? null : machineId(defaultMachine);
      _directory = _defaultDirectoryFor(defaultMachine);
      _sessionConfig = SessionConfig.defaultsFor(widget.catalog, 'claude');
      _draft = autils.AutomationScheduleDraft();
    }
    _startMachineRealtime();
  }

  @override
  void dispose() {
    _stopMachineRealtime();
    _titleController.dispose();
    _promptController.dispose();
    super.dispose();
  }

  /// Merge live `machine-update` WS events into [_machines] and re-evaluate
  /// liveness on a 30s ticker, so the "Runs on" online dot tracks reality
  /// instead of freezing at open time (matches MachinesModel).
  void _startMachineRealtime() {
    final client = actions.VicoaWsClient.instance;
    client.retain();
    _machineSub = client.machineEvents.listen((e) {
      if (e['event'] == 'machine_updated') _mergeMachineUpdate(e['data']);
    });
    _machineTicker = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted) setState(() {});
    });
  }

  void _stopMachineRealtime() {
    _machineSub?.cancel();
    _machineSub = null;
    _machineTicker?.cancel();
    _machineTicker = null;
    actions.VicoaWsClient.instance.release();
  }

  void _mergeMachineUpdate(dynamic data) {
    final incoming = normalizeMachine(data);
    final id = incoming['machine_id']?.toString();
    if (id == null) return;
    final idx = _machines.indexWhere((m) => machineId(m) == id);
    if (idx == -1) {
      _machines = [..._machines, incoming];
    } else {
      final merged = {
        ...Map<String, dynamic>.from(_machines[idx] as Map),
        ...incoming,
      };
      _machines = List<dynamic>.from(_machines)..[idx] = merged;
    }
    if (mounted) setState(() {});
  }

  String _defaultDirectoryFor(dynamic machine) {
    final recents = _recentDirectoriesFor(machine);
    if (recents.isNotEmpty) return recents.first;
    return getMachineHomeDir(machine) ?? '~/';
  }

  /// The bound directory expanded to an absolute path (`~` → home), for the
  /// `@` file index. Null when there's no directory yet.
  String? _absolutePromptDirectory() {
    final dir = _directory.trim();
    if (dir.isEmpty) return null;
    return functions.toAbsolutePath(dir, getMachineHomeDir(_machine));
  }

  List<String> _recentDirectoriesFor(dynamic machine) {
    final out = <String>[];
    if (machine is Map) {
      final dirs = machine['recent_directories'];
      if (dirs is List) out.addAll(dirs.map((d) => d.toString()));
    }
    for (final d in FFAppState().cachedDirectories) {
      if (!out.contains(d)) out.add(d);
    }
    return out.take(20).toList();
  }

  bool get _canSave =>
      _titleController.text.trim().isNotEmpty &&
      _promptController.text.trim().isNotEmpty &&
      _machineId != null &&
      _directory.trim().isNotEmpty &&
      _draft.isComplete;

  void _save() {
    // An automation needs a machine to run on. When none is selected — which,
    // given the auto-select on open, means no computer is connected — nudge the
    // user to connect one rather than silently doing nothing.
    if (_machineId == null) {
      SessionActions.showSnack(
          context, AppLocalizations.of(context).automationsConnectMachineFirst);
      return;
    }
    if (_titleController.text.trim().isEmpty) {
      setState(() => _titleError = true);
      return;
    }
    if (!_canSave) return;
    HapticFeedback.lightImpact();
    Navigator.pop(context, <String, dynamic>{
      'title': _titleController.text.trim(),
      'prompt': _promptController.text.trim(),
      'machine_id': _machineId,
      'directory': _directory.trim(),
      'session_config': _sessionConfig.toJson(),
      ..._draft.toScheduleApi(),
    });
  }

  // --- pickers ---------------------------------------------------------------

  Future<void> _pickDirectory() async {
    dismissKeyboard();
    final picked = await showDirectoryPickerSheet(
      context: context,
      initial: _directory,
      recentDirectories: _recentDirectoriesFor(_machine),
    );
    if (picked == null) return;
    setState(() => _directory = picked);
  }

  Future<void> _pickAgentConfig() async {
    dismissKeyboard();
    final picked = await showAgentConfigSheet(
      context: context,
      catalog: widget.catalog,
      initial: _sessionConfig,
      availableAgents: parseAvailableAgents(_machine),
    );
    if (picked == null) return;
    setState(() => _sessionConfig = picked);
  }

  Icon _repeatIcon(String mode) {
    final theme = FlutterFlowTheme.of(context);
    final icon = switch (mode) {
      'once' => Icons.event_rounded,
      'minutely' => Icons.av_timer_rounded,
      'hourly' => Icons.schedule_rounded,
      'daily' => Icons.today_rounded,
      'weekdays' => Icons.work_outline_rounded,
      'weekly' => Icons.date_range_rounded,
      'monthly' => Icons.calendar_month_rounded,
      _ => Icons.tune_rounded,
    };
    return Icon(icon, size: 16.0, color: theme.secondaryText);
  }

  Future<void> _pickRepeat(AppLocalizations l10n) async {
    final picked = await showAnchoredSingleSelect<String>(
      context: context,
      anchorKey: _repeatKey,
      selected: _draft.repeat,
      alignRight: true,
      options: [
        for (final mode in autils.kAutomationRepeatModes)
          PickerOption(
            value: mode,
            leading: _repeatIcon(mode),
            label: automationRepeatLabel(l10n, mode),
          ),
      ],
    );
    if (picked != null) setState(() => _draft.repeat = picked);
  }

  Future<void> _pickCustomUnit(AppLocalizations l10n) async {
    final picked = await showAnchoredSingleSelect<String>(
      context: context,
      anchorKey: _unitKey,
      selected: _draft.customUnit,
      alignRight: true,
      options: [
        for (final unit in autils.kAutomationCustomUnits)
          PickerOption(
            value: unit,
            leading: _repeatIcon(unit),
            label: automationRepeatLabel(l10n, unit),
          ),
      ],
    );
    if (picked != null) {
      setState(() {
        _draft.customUnit = picked;
        // "Every N minutes" carries a floor; other units start at 1.
        _draft.interval =
            picked == 'minutely' ? autils.kMinMinutelyInterval * 3 : 1;
      });
    }
  }

  Future<void> _pickOnceDate(AppLocalizations l10n) async {
    final now = DateTime.now();
    final initial = _draft.runAt ?? now.add(const Duration(hours: 1));
    final picked = await showWheelDatePicker(
      context: context,
      title: l10n.automationsDate,
      initial: initial.isBefore(now) ? now : initial,
      minimum: DateTime(now.year, now.month, now.day),
      maximum: now.add(const Duration(days: 365 * 2)),
    );
    if (picked == null) return;
    setState(() {
      final prior = _draft.runAt ?? now.add(const Duration(hours: 1));
      _draft.runAt = DateTime(
          picked.year, picked.month, picked.day, prior.hour, prior.minute);
    });
  }

  Future<void> _pickOnceTime(AppLocalizations l10n) async {
    final prior = _draft.runAt ?? DateTime.now().add(const Duration(hours: 1));
    final picked = await showWheelTimePicker(
      context: context,
      title: l10n.automationsTime,
      initial: TimeOfDay(hour: prior.hour, minute: prior.minute),
    );
    if (picked == null) return;
    setState(() {
      _draft.runAt = DateTime(
          prior.year, prior.month, prior.day, picked.hour, picked.minute);
    });
  }

  Future<void> _pickTimeOfDay(AppLocalizations l10n) async {
    final picked = await showWheelTimePicker(
      context: context,
      title: l10n.automationsTime,
      initial: TimeOfDay(hour: _draft.timeHour, minute: _draft.timeMinute),
    );
    if (picked == null) return;
    setState(() {
      _draft.timeHour = picked.hour;
      _draft.timeMinute = picked.minute;
    });
  }

  Future<void> _pickWindowStart(AppLocalizations l10n) async {
    final picked = await showWheelTimePicker(
      context: context,
      title: l10n.automationsWindowFrom,
      initial:
          TimeOfDay(hour: _draft.windowStartHour, minute: _draft.windowStartMinute),
    );
    if (picked == null) return;
    setState(() {
      _draft.windowStartHour = picked.hour;
      _draft.windowStartMinute = picked.minute;
    });
  }

  Future<void> _pickWindowEnd(AppLocalizations l10n) async {
    final picked = await showWheelTimePicker(
      context: context,
      title: l10n.automationsWindowTo,
      initial:
          TimeOfDay(hour: _draft.windowEndHour, minute: _draft.windowEndMinute),
    );
    if (picked == null) return;
    setState(() {
      _draft.windowEndHour = picked.hour;
      _draft.windowEndMinute = picked.minute;
    });
  }

  // --- build -----------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final l10n = AppLocalizations.of(context);
    final maxHeight = MediaQuery.of(context).size.height * 0.92;

    return Container(
      constraints: BoxConstraints(maxHeight: maxHeight),
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24.0)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              margin: const EdgeInsets.only(top: 12.0, bottom: 4.0),
              width: 40.0,
              height: 4.0,
              decoration: BoxDecoration(
                color: theme.alternate,
                borderRadius: BorderRadius.circular(2.0),
              ),
            ),
            Padding(
              padding:
                  const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 8.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  FlutterFlowIconButton(
                    borderColor: theme.alternate,
                    borderRadius: 10.0,
                    borderWidth: 1.0,
                    buttonSize: 40.0,
                    icon: Icon(Icons.close_rounded,
                        color: theme.secondaryText, size: 20.0),
                    onPressed: () => Navigator.pop(context),
                  ),
                  Text(
                    _isEditing ? l10n.automationsEditTitle : l10n.automationsNew,
                    style: theme.titleLarge.override(
                      font: GoogleFonts.sourceSans3(),
                      color: theme.primaryText,
                      fontSize: 19.0,
                      letterSpacing: 0.0,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  FlutterFlowIconButton(
                    borderColor: _canSave ? theme.primary : theme.alternate,
                    borderRadius: 10.0,
                    borderWidth: 1.0,
                    buttonSize: 40.0,
                    fillColor: _canSave ? theme.primary : null,
                    icon: Icon(
                      Icons.check_rounded,
                      color: _canSave ? theme.info : theme.secondaryText,
                      size: 20.0,
                    ),
                    onPressed: _save,
                  ),
                ],
              ),
            ),
            Flexible(
              // Tapping empty space in the form drops the keyboard.
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: dismissKeyboard,
                child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20.0, 12.0, 20.0, 24.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      controller: _titleController,
                      autofocus: !_isEditing,
                      textCapitalization: TextCapitalization.sentences,
                      onChanged: (_) => setState(() => _titleError = false),
                      style: theme.titleLarge.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        fontSize: 19.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w600,
                      ),
                      decoration: InputDecoration(
                        isCollapsed: true,
                        border: InputBorder.none,
                        hintText: l10n.automationsTitlePlaceholder,
                        hintStyle: theme.titleLarge.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText.withValues(alpha: 0.5),
                          fontSize: 19.0,
                          letterSpacing: 0.0,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    if (_titleError)
                      Padding(
                        padding: const EdgeInsets.only(top: 6.0),
                        child: Text(
                          l10n.automationsTitleRequired,
                          style: theme.labelSmall.override(
                            font: GoogleFonts.sourceSans3(),
                            color: theme.error,
                            letterSpacing: 0.0,
                          ),
                        ),
                      ),
                    const SizedBox(height: 12.0),
                    MentionPromptField(
                      controller: _promptController,
                      machineId: _machineId,
                      projectPath: _absolutePromptDirectory(),
                      agentType: _sessionConfig.agent,
                      maxLines: 5,
                      minLines: 2,
                      onChanged: (_) => setState(() {}),
                      style: theme.bodyMedium.override(
                        font: GoogleFonts.sourceSans3(),
                        color: theme.primaryText,
                        letterSpacing: 0.0,
                      ),
                      decoration: InputDecoration(
                        isCollapsed: true,
                        border: InputBorder.none,
                        hintText: l10n.automationsPromptPlaceholder,
                        hintStyle: theme.bodyMedium.override(
                          font: GoogleFonts.sourceSans3(),
                          color: theme.secondaryText.withValues(alpha: 0.6),
                          letterSpacing: 0.0,
                        ),
                      ),
                    ),
                    const SizedBox(height: 20.0),
                    AutomationSectionCard(
                      label: l10n.automationsSectionDetails,
                      children: _detailRows(theme, l10n),
                    ),
                    const SizedBox(height: 16.0),
                    AutomationSectionCard(
                      label: l10n.automationsSectionFrequency,
                      children: _frequencyRows(theme, l10n),
                    ),
                    if (_isEditing) ...[
                      const SizedBox(height: 16.0),
                      AutomationSectionCard(
                        label: l10n.automationsSectionRunHistory,
                        children: [
                          AutomationRunHistory(
                            automationId:
                                autils.automationId(widget.automation),
                            onOpenInstance: (id) {
                              Navigator.pop(context);
                              widget.onOpenInstance?.call(id);
                            },
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _directoryBasename(AppLocalizations l10n) {
    final dir = _directory.trim();
    if (dir.isEmpty) return l10n.automationsChooseFolder;
    final parts = dir.split('/').where((s) => s.isNotEmpty).toList();
    return parts.isEmpty ? dir : parts.last;
  }

  /// Inline machine dropdown for the "Runs on" row — the same dropdown-menu
  /// behavior as the New Session page's machine selector (online dots +
  /// "Offline" tags), embedded in the row instead of opening a sheet. Unlike
  /// New Session, offline machines stay selectable: an automation scheduled
  /// on an offline machine simply records missed runs until it comes back.
  Widget _machineDropdown(FlutterFlowTheme theme, AppLocalizations l10n) {
    final ids = {for (final m in _machines) machineId(m)};
    final dropdownValue = ids.contains(_machineId) ? _machineId : null;
    Widget dot(bool isOnline) => Container(
          width: 8.0,
          height: 8.0,
          decoration: BoxDecoration(
            color: isOnline
                ? Colors.green
                : theme.secondaryText.withValues(alpha: 0.3),
            borderRadius: BorderRadius.circular(4.0),
          ),
        );
    return DropdownButton<String>(
      value: dropdownValue,
      isExpanded: true,
      isDense: true,
      underline: const SizedBox.shrink(),
      borderRadius: BorderRadius.circular(14.0),
      dropdownColor: theme.primaryBackground,
      hint: Align(
        alignment: AlignmentDirectional.centerEnd,
        child: Text(
          l10n.newSessionSelectMachine,
          style: theme.bodyMedium.override(
            font: GoogleFonts.sourceSans3(),
            color: theme.secondaryText.withValues(alpha: 0.5),
            fontSize: 15.0,
            letterSpacing: 0.0,
          ),
        ),
      ),
      icon: Icon(Icons.keyboard_arrow_down_rounded,
          color: theme.secondaryText, size: 18.0),
      // Drop the keyboard before the native menu opens over the sheet.
      onTap: dismissKeyboard,
      // Collapsed view: compact, right-aligned dot + name (the menu items
      // below keep the full New Session layout).
      selectedItemBuilder: (context) => [
        for (final machine in _machines)
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                dot(isMachineOnlineFromMap(machine)),
                const SizedBox(width: 7.0),
                Flexible(
                  child: Text(
                    machineDisplayName(machine),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.bodyMedium.override(
                      font: GoogleFonts.sourceSans3(),
                      letterSpacing: 0.0,
                      color: theme.secondaryText,
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
      items: _machines.map<DropdownMenuItem<String>>((machine) {
        final id = machineId(machine);
        final isOnline = isMachineOnlineFromMap(machine);
        return DropdownMenuItem<String>(
          value: id,
          child: Row(
            children: [
              dot(isOnline),
              const SizedBox(width: 12.0),
              Expanded(
                child: Text(
                  machineDisplayName(machine),
                  overflow: TextOverflow.ellipsis,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 15.0,
                    letterSpacing: 0.0,
                    color: theme.primaryText,
                  ),
                ),
              ),
              if (!isOnline)
                Text(
                  l10n.newSessionOffline,
                  style: theme.bodySmall.override(
                    fontSize: 13.0,
                    letterSpacing: 0.0,
                    color: theme.secondaryText.withValues(alpha: 0.5),
                  ),
                ),
            ],
          ),
        );
      }).toList(),
      onChanged: (value) {
        if (value == null || value == _machineId) return;
        HapticFeedback.lightImpact();
        setState(() {
          _machineId = value;
          _directory = _defaultDirectoryFor(_machineForId(value));
        });
      },
    );
  }

  List<Widget> _detailRows(FlutterFlowTheme theme, AppLocalizations l10n) {
    return [
      AutomationFieldRow(
        label: l10n.automationsRunsOn,
        showChevron: false,
        valueWidget: _machineDropdown(theme, l10n),
      ),
      AutomationFieldRow(
        label: l10n.automationsProject,
        value: _directoryBasename(l10n),
        onTap: _pickDirectory,
      ),
      AutomationFieldRow(
        label: l10n.automationsAgent,
        value: sessionConfigSummary(widget.catalog, _sessionConfig),
        onTap: _pickAgentConfig,
      ),
    ];
  }

  /// The optional "only during a daily window" rows for sub-daily units: a
  /// toggle, then From/To time pickers (with an inline hint on a bad span).
  void _addWindowRows(
      List<Widget> rows, FlutterFlowTheme theme, AppLocalizations l10n) {
    rows.add(AutomationFieldRow(
      label: l10n.automationsTimeWindow,
      showChevron: false,
      valueWidget: Align(
        alignment: AlignmentDirectional.centerEnd,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              _draft.windowEnabled
                  ? l10n.automationsWindowCustom
                  : l10n.automationsWindowAllDay,
              style: theme.bodyMedium.override(
                font: GoogleFonts.sourceSans3(),
                letterSpacing: 0.0,
                color: theme.secondaryText,
              ),
            ),
            const SizedBox(width: 8.0),
            // Scaled to the stepper's ~30px so this row's height matches the
            // others; brand-colored on (primary track, light thumb) instead of
            // the platform default green.
            SizedBox(
              height: 30.0,
              child: FittedBox(
                fit: BoxFit.contain,
                child: Switch(
                  value: _draft.windowEnabled,
                  onChanged: (v) {
                    HapticFeedback.lightImpact();
                    setState(() => _draft.windowEnabled = v);
                  },
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  activeThumbColor: theme.primaryText,
                  activeTrackColor: theme.secondaryText,
                  inactiveThumbColor: theme.info,
                  inactiveTrackColor: theme.alternate,
                ),
              ),
            ),
          ],
        ),
      ),
    ));
    if (!_draft.windowEnabled) return;
    rows.add(AutomationFieldRow(
      label: l10n.automationsWindowFrom,
      value: TimeOfDay(
              hour: _draft.windowStartHour, minute: _draft.windowStartMinute)
          .format(context),
      onTap: () => _pickWindowStart(l10n),
    ));
    rows.add(AutomationFieldRow(
      label: l10n.automationsWindowTo,
      value: TimeOfDay(
              hour: _draft.windowEndHour, minute: _draft.windowEndMinute)
          .format(context),
      onTap: () => _pickWindowEnd(l10n),
    ));
    if (!_draft.windowValid) {
      rows.add(Padding(
        padding: const EdgeInsets.fromLTRB(14.0, 0.0, 14.0, 12.0),
        child: Align(
          alignment: AlignmentDirectional.centerStart,
          child: Text(
            l10n.automationsWindowInvalid,
            style: theme.labelSmall.override(
              font: GoogleFonts.sourceSans3(),
              color: theme.error,
              letterSpacing: 0.0,
            ),
          ),
        ),
      ));
    }
  }

  List<Widget> _frequencyRows(FlutterFlowTheme theme, AppLocalizations l10n) {
    final locale = Localizations.localeOf(context).toString();
    final rows = <Widget>[
      SizedBox(
        key: _repeatKey,
        child: AutomationFieldRow(
          label: l10n.automationsRepeat,
          value: automationRepeatLabel(l10n, _draft.repeat),
          onTap: () => _pickRepeat(l10n),
        ),
      ),
    ];

    Widget timeRow() => AutomationFieldRow(
          label: l10n.automationsTime,
          value: TimeOfDay(hour: _draft.timeHour, minute: _draft.timeMinute)
              .format(context),
          onTap: () => _pickTimeOfDay(l10n),
        );

    Widget minuteRow() => AutomationFieldRow(
          label: l10n.automationsAtMinute,
          showChevron: false,
          valueWidget: Align(
            alignment: AlignmentDirectional.centerEnd,
            child: NumberStepper(
              value: _draft.minuteOfHour,
              min: 0,
              max: 59,
              displayValue:
                  ':${_draft.minuteOfHour.toString().padLeft(2, '0')}',
              pickerTitle: l10n.automationsAtMinute,
              wheelItemLabel: (v) => v.toString().padLeft(2, '0'),
              onChanged: (v) => setState(() => _draft.minuteOfHour = v),
            ),
          ),
        );

    Widget weekdayRow() => Padding(
          padding:
              const EdgeInsets.symmetric(horizontal: 14.0, vertical: 12.0),
          child: WeekdayChips(
            selected: _draft.weekdays,
            onToggle: (d) => setState(() {
              if (!_draft.weekdays.remove(d)) _draft.weekdays.add(d);
            }),
          ),
        );

    switch (_draft.repeat) {
      case 'once':
        rows.add(AutomationFieldRow(
          label: l10n.automationsDate,
          value: _draft.runAt == null
              ? '—'
              : DateFormat.yMMMd(locale).format(_draft.runAt!),
          onTap: () => _pickOnceDate(l10n),
        ));
        rows.add(AutomationFieldRow(
          label: l10n.automationsTime,
          value: _draft.runAt == null
              ? '—'
              : TimeOfDay(
                      hour: _draft.runAt!.hour, minute: _draft.runAt!.minute)
                  .format(context),
          onTap: () => _pickOnceTime(l10n),
        ));
        break;
      case 'hourly':
        rows.add(minuteRow());
        break;
      case 'daily':
      case 'weekdays':
        rows.add(timeRow());
        break;
      case 'weekly':
        rows.add(weekdayRow());
        rows.add(timeRow());
        break;
      case 'custom':
        rows.add(SizedBox(
          key: _unitKey,
          child: AutomationFieldRow(
            label: l10n.automationsRepeats,
            value: automationRepeatLabel(l10n, _draft.customUnit),
            onTap: () => _pickCustomUnit(l10n),
          ),
        ));
        final maxInterval = switch (_draft.customUnit) {
          'minutely' => 1439,
          'hourly' => 168,
          'daily' => 365,
          'weekly' => 52,
          _ => 24,
        };
        final minInterval =
            _draft.customUnit == 'minutely' ? autils.kMinMinutelyInterval : 1;
        rows.add(AutomationFieldRow(
          label: l10n.automationsEvery,
          showChevron: false,
          valueWidget: Align(
            alignment: AlignmentDirectional.centerEnd,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                NumberStepper(
                  value: _draft.interval,
                  min: minInterval,
                  max: maxInterval,
                  pickerTitle: l10n.automationsEvery,
                  onChanged: (v) => setState(() => _draft.interval = v),
                ),
                const SizedBox(width: 10.0),
                Text(
                  automationEveryUnitLabel(l10n, _draft.customUnit, _draft.interval),
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    letterSpacing: 0.0,
                    color: theme.secondaryText,
                  ),
                ),
              ],
            ),
          ),
        ));
        if (_draft.customUnit == 'minutely') {
          _addWindowRows(rows, theme, l10n);
        } else if (_draft.customUnit == 'hourly') {
          // A window supersedes the ":MM" phase, so only offer it all-day.
          if (!_draft.windowEnabled) rows.add(minuteRow());
          _addWindowRows(rows, theme, l10n);
        } else {
          if (_draft.customUnit == 'weekly') rows.add(weekdayRow());
          if (_draft.customUnit == 'monthly') {
            rows.add(Padding(
              padding:
                  const EdgeInsets.symmetric(horizontal: 14.0, vertical: 12.0),
              child: MonthdayGrid(
                selected: _draft.monthdays,
                onToggle: (d) => setState(() {
                  if (!_draft.monthdays.remove(d)) _draft.monthdays.add(d);
                }),
              ),
            ));
          }
          rows.add(timeRow());
        }
        break;
    }
    return rows;
  }
}
