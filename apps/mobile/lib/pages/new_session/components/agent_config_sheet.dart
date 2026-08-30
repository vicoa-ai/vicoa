import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/backend/agent_catalog.dart';
import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

/// Bottom-sheet for choosing agent + per-agent model / effort / permission.
///
/// Default shape: new-session usage — all dimensions editable, title "Agent",
/// 0.55 screen height.
///
/// Chat usage: pass [hideAgentSelector] = true to hide the Agent dropdown
/// (agent can't change mid-session), [title] = 'Model Config',
/// [heightFraction] = 0.5 for a more compact sheet, [freezeModelAndEffort] =
/// true so the Model + Thinking + Reasoning dropdowns are visible but
/// disabled (only Permission / Mode are live-editable mid-chat), and
/// [footerNote] to surface the "coming soon" affordance.
Future<SessionConfig?> showAgentConfigSheet({
  required BuildContext context,
  required AgentCatalog catalog,
  required SessionConfig initial,
  bool hideAgentSelector = false,
  String? title,
  double heightFraction = 0.65,
  bool freezeModelAndEffort = false,
  bool freezePermission = false,
  bool freezeOpencodeMode = false,
  String? footerNote,
  Map<String, bool>? availableAgents,
}) async {
  return showModalBottomSheet<SessionConfig>(
    context: context,
    isScrollControlled: true,
    useSafeArea: false,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _AgentConfigSheet(
      catalog: catalog,
      initial: initial,
      hideAgentSelector: hideAgentSelector,
      title: title,
      heightFraction: heightFraction,
      freezeModelAndEffort: freezeModelAndEffort,
      freezePermission: freezePermission,
      freezeOpencodeMode: freezeOpencodeMode,
      footerNote: footerNote,
      availableAgents: availableAgents,
    ),
  );
}

class _AgentConfigSheet extends StatefulWidget {
  const _AgentConfigSheet({
    required this.catalog,
    required this.initial,
    this.hideAgentSelector = false,
    this.title,
    this.heightFraction = 0.65,
    this.freezeModelAndEffort = false,
    this.freezePermission = false,
    this.freezeOpencodeMode = false,
    this.footerNote,
    this.availableAgents,
  });
  final AgentCatalog catalog;
  final SessionConfig initial;
  final bool hideAgentSelector;
  final String? title;
  final double heightFraction;
  final bool freezeModelAndEffort;
  final bool freezePermission;
  final bool freezeOpencodeMode;
  final String? footerNote;

  /// Machine `available_agents` map. When provided, the Agent dropdown only
  /// offers agents the selected machine's daemon reports as installed
  /// (mirrors the machine-detail Agents section). Null = no metadata (old
  /// daemon) → show the full catalog.
  final Map<String, bool>? availableAgents;

  @override
  State<_AgentConfigSheet> createState() => _AgentConfigSheetState();
}

class _AgentConfigSheetState extends State<_AgentConfigSheet> {
  late SessionConfig _config;

  /// Set to the id of an uninstalled agent the user just tapped, so we can
  /// show an inline "not installed" explanation under the Agent dropdown.
  String? _unavailableNoticeAgentId;

  @override
  void initState() {
    super.initState();
    _config = widget.initial.reconcileAgainst(widget.catalog);
    // If the initial agent isn't available on this machine, land on the
    // first one that is — never open pointing at an agent the daemon
    // would reject.
    if (!widget.hideAgentSelector && !_isAgentAvailable(_config.agent)) {
      final agents = _visibleAgents();
      if (agents.isNotEmpty) {
        _config = SessionConfig.defaultsFor(widget.catalog, agents.first.id);
      }
    }
  }

  bool _isAgentAvailable(String agentId) {
    final available = widget.availableAgents;
    if (available == null) return true;
    return available[agentId] == true;
  }

  /// Catalog agents filtered to what the machine supports. Falls back to the
  /// full catalog when filtering would leave nothing selectable (defensive:
  /// a machine reporting zero installed agents shouldn't brick the sheet).
  List<CatalogAgent> _visibleAgents() {
    final filtered =
        widget.catalog.agents.where((a) => _isAgentAvailable(a.id)).toList();
    return filtered.isNotEmpty ? filtered : widget.catalog.agents;
  }

  /// Inline explanation shown when the user taps an uninstalled agent.
  Widget _unavailableNotice(
      BuildContext context, FlutterFlowTheme theme, String agentId) {
    final l10n = AppLocalizations.of(context);
    final label = widget.catalog.agentById(agentId)?.label ?? agentId;
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Icon(Icons.info_outline_rounded, size: 15.0, color: theme.secondaryText),
      const SizedBox(width: 8.0),
      Expanded(
        child: Text.rich(
          TextSpan(
            style: theme.bodySmall.override(
              font: GoogleFonts.sourceSans3(),
              fontSize: 13.0,
              color: theme.secondaryText,
              lineHeight: 1.4,
            ),
            children: [
              TextSpan(text: l10n.agentConfigNotInstalledPrefix(label)),
              TextSpan(
                text: 'vicoa daemon',
                style: GoogleFonts.jetBrainsMono(fontSize: 12.0, color: theme.primaryText),
              ),
              TextSpan(text: l10n.agentConfigNotInstalledSuffix),
            ],
          ),
        ),
      ),
    ]);
  }

  /// When the user switches agents inside the sheet, swap to a freshly-derived
  /// config for that agent. Plan §3.5: per-agent memory is per-AGENT, not
  /// global, so we don't carry [model] etc. across agent boundaries.
  void _switchAgent(String nextAgentId) {
    if (_config.agent == nextAgentId) return;
    setState(() => _config = SessionConfig.defaultsFor(widget.catalog, nextAgentId));
  }

  void _updateConfig({String? model, String? thinkingEffort, String? reasoningEffort, String? permissionMode, String? opencodeMode}) {
    setState(() {
      var next = SessionConfig(
        agent: _config.agent,
        model: model ?? _config.model,
        thinkingEffort: thinkingEffort ?? _config.thinkingEffort,
        reasoningEffort: reasoningEffort ?? _config.reasoningEffort,
        permissionMode: permissionMode ?? _config.permissionMode,
        opencodeMode: opencodeMode ?? _config.opencodeMode,
      );
      // When the model changes, reconcile per-model-gated fields against
      // the new model's allowlists so we don't submit an invalid combo
      // (e.g. `permission_mode=auto` after switching to Sonnet).
      if (model != null && model != _config.model) {
        next = _reconcilePerModelFilters(next);
      }
      _config = next;
    });
  }

  /// If the model's `permission_modes` / `thinking_efforts` allowlists
  /// exclude the currently-selected value, swap it for the model's default.
  /// Mirrors the dropdown's display-time fallback so the dropdown shows
  /// what we'd actually submit.
  SessionConfig _reconcilePerModelFilters(SessionConfig config) {
    final agent = widget.catalog.agentById(config.agent);
    if (agent == null || agent.models == null || config.model == null) return config;
    final modelDef = agent.models!.firstWhere(
      (m) => m.id == config.model,
      orElse: () => CatalogModel(id: config.model!, label: config.model!),
    );

    // Common + opt-ins: drop opt_in entries that the new model doesn't name.
    String? pickDefault(List<CatalogEnumEntry> entries, Set<String> optIns) {
      final filtered = entries.where((e) => !e.optIn || optIns.contains(e.id)).toList();
      if (filtered.isEmpty) return null;
      return filtered.firstWhere((e) => e.isDefault, orElse: () => filtered.first).id;
    }

    final permOptIns = modelDef.permissionModes?.toSet() ?? <String>{};
    final permVisible = agent.permissionModes.where((e) => !e.optIn || permOptIns.contains(e.id)).map((e) => e.id).toSet();
    String? nextPerm = config.permissionMode;
    if (nextPerm == null || !permVisible.contains(nextPerm)) {
      nextPerm = pickDefault(agent.permissionModes, permOptIns);
    }

    final thinkOptIns = modelDef.thinkingEfforts?.toSet() ?? <String>{};
    final thinkVisible = agent.thinkingEfforts.where((e) => !e.optIn || thinkOptIns.contains(e.id)).map((e) => e.id).toSet();
    String? nextThink = config.thinkingEffort;
    if (nextThink == null || !thinkVisible.contains(nextThink)) {
      nextThink = pickDefault(agent.thinkingEfforts, thinkOptIns);
    }

    return SessionConfig(
      agent: config.agent,
      model: config.model,
      thinkingEffort: nextThink,
      reasoningEffort: config.reasoningEffort,
      permissionMode: nextPerm,
      opencodeMode: config.opencodeMode,
    );
  }

  void _confirm() {
    HapticFeedback.lightImpact();
    Navigator.of(context).pop(_config);
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      width: double.infinity,
      height: MediaQuery.of(context).size.height * widget.heightFraction,
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.only(topLeft: Radius.circular(24.0), topRight: Radius.circular(24.0)),
      ),
      child: Column(mainAxisSize: MainAxisSize.max, children: [
        _SheetHandle(),
        _SheetHeader(
          title: widget.title ?? AppLocalizations.of(context).agentConfigAgent,
          canConfirm: true,
          onClose: () { HapticFeedback.lightImpact(); Navigator.pop(context); },
          onConfirm: _confirm,
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: _buildBody(theme)),
          ),
        ),
      ]),
    );
  }

  /// Wraps a section in IgnorePointer + half opacity when its corresponding
  /// freeze flag is set. Used to grey out Model / Thinking / Reasoning (and
  /// Permission too, for Codex) when the sheet opens from a live chat that
  /// can't yet change those dimensions mid-session.
  Widget _freeze(Widget child, bool active) {
    if (!active) return child;
    return Opacity(opacity: 0.5, child: IgnorePointer(child: child));
  }

  List<Widget> _buildBody(FlutterFlowTheme theme) {
    final widgets = <Widget>[];
    if (!widget.hideAgentSelector) {
      // Show EVERY agent we support, but disable the ones this machine's
      // daemon doesn't have installed (mirrors the machine-detail Agents
      // section's "Not installed" affordance). The user can see what's
      // available elsewhere without being able to pick it here.
      //
      // Installed agents come first, then the uninstalled ones — each group
      // keeps the catalog's given order.
      final catalogAgents = widget.catalog.agents;
      final allAgents = [
        ...catalogAgents.where((a) => _isAgentAvailable(a.id)),
        ...catalogAgents.where((a) => !_isAgentAvailable(a.id)),
      ];
      final disabledAgentIds = <String>{
        for (final a in allAgents)
          if (!_isAgentAvailable(a.id)) a.id,
      };
      final items = [
        for (final a in allAgents)
          DropdownMenuItem<String>(
            value: a.id,
            child: _OptionRow(
              label: a.label,
              leading: AgentTypeIconWidget(agentTypeName: a.id, size: 20.0),
              trailing: disabledAgentIds.contains(a.id)
                  ? AppLocalizations.of(context).agentConfigNotInstalled
                  : null,
              dimmed: disabledAgentIds.contains(a.id),
            ),
          ),
        // Catalog drift guard: keep the current agent selectable even if it
        // isn't in the catalog (so the dropdown never renders blank).
        if (!allAgents.any((a) => a.id == _config.agent))
          DropdownMenuItem<String>(
            value: _config.agent,
            child: _OptionRow(
              label: _config.agent,
              leading: AgentTypeIconWidget(agentTypeName: _config.agent, size: 20.0),
            ),
          ),
      ];
      widgets.addAll([
        _sectionLabel(context, AppLocalizations.of(context).agentConfigAgent),
        const SizedBox(height: 8),
        _StyledDropdown<String>(
          value: _config.agent,
          items: items,
          onChanged: (v) {
            if (v == null) return;
            // Tapping an uninstalled agent doesn't switch to it — instead we
            // surface an inline explanation telling the user to install it and
            // restart the daemon. Selecting an installed agent clears it.
            if (disabledAgentIds.contains(v)) {
              setState(() => _unavailableNoticeAgentId = v);
              return;
            }
            setState(() => _unavailableNoticeAgentId = null);
            _switchAgent(v);
          },
        ),
        if (_unavailableNoticeAgentId != null &&
            disabledAgentIds.contains(_unavailableNoticeAgentId)) ...[
          const SizedBox(height: 10),
          _unavailableNotice(context, theme, _unavailableNoticeAgentId!),
        ],
        const SizedBox(height: 20),
      ]);
    }

    final agent = widget.catalog.agentById(_config.agent);
    if (agent == null) {
      widgets.add(Text(AppLocalizations.of(context).agentConfigUnknownAgent));
      return widgets;
    }

    if (agent.models != null && agent.models!.isNotEmpty) {
      widgets.add(_sectionLabel(context, AppLocalizations.of(context).agentConfigModel));
      widgets.add(const SizedBox(height: 8));
      // If the running model isn't in the catalog (catalog drift — e.g.
      // Codex's actual gpt-5-codex vs the catalog's gpt-5.5 placeholder),
      // prepend it as a synthetic item so the dropdown shows the truth
      // about what's running instead of either rendering blank or
      // silently swapping to a catalog default the session isn't using.
      final items = <DropdownMenuItem<String>>[
        for (final m in agent.models!)
          DropdownMenuItem<String>(value: m.id, child: _OptionRow(label: m.label, description: m.description)),
      ];
      if (_config.model != null && !agent.models!.any((m) => m.id == _config.model)) {
        items.insert(0, DropdownMenuItem<String>(
          value: _config.model,
          child: _OptionRow(label: _config.model!),
        ));
      }
      widgets.add(_freeze(_StyledDropdown<String>(
        value: _config.model,
        items: items,
        onChanged: (v) => _updateConfig(model: v),
      ), widget.freezeModelAndEffort));
      widgets.add(const SizedBox(height: 16));
    }

    if (agent.thinkingEfforts.isNotEmpty) {
      // Common + per-model opt-ins: every non-opt_in entry is shown; opt_in
      // entries appear only when the active model names them in its array.
      final optIns = <String>{};
      String? perModelDefault;
      if (_config.model != null && agent.models != null) {
        final m = agent.models!.firstWhere((m) => m.id == _config.model, orElse: () => CatalogModel(id: _config.model!, label: _config.model!));
        if (m.thinkingEfforts != null) optIns.addAll(m.thinkingEfforts!);
        perModelDefault = m.defaultThinkingEffort;
      }
      final efforts = agent.thinkingEfforts.where((e) => !e.optIn || optIns.contains(e.id)).toList();
      String? selected;
      if (efforts.any((e) => e.id == _config.thinkingEffort)) {
        selected = _config.thinkingEffort;
      } else if (perModelDefault != null && efforts.any((e) => e.id == perModelDefault)) {
        // Per-model default overrides agent-level is_default — Opus 4.7+
        // surface `xhigh` rather than the catalog's `low` baseline.
        selected = perModelDefault;
      } else if (efforts.isNotEmpty) {
        selected = efforts.firstWhere((e) => e.isDefault, orElse: () => efforts.first).id;
      }
      widgets.add(_sectionLabel(context, AppLocalizations.of(context).agentConfigThinkingEffort));
      widgets.add(const SizedBox(height: 8));
      widgets.add(_freeze(_StyledDropdown<String>(
        value: selected,
        items: efforts.map((e) => DropdownMenuItem<String>(value: e.id, child: _OptionRow(label: e.label))).toList(),
        onChanged: (v) => _updateConfig(thinkingEffort: v),
      ), widget.freezeModelAndEffort));
      widgets.add(const SizedBox(height: 16));
    }

    if (agent.reasoningEfforts.isNotEmpty) {
      widgets.add(_sectionLabel(context, AppLocalizations.of(context).agentConfigReasoningEffort));
      widgets.add(const SizedBox(height: 8));
      widgets.add(_freeze(_StyledDropdown<String>(
        value: agent.reasoningEfforts.any((e) => e.id == _config.reasoningEffort) ? _config.reasoningEffort : null,
        items: agent.reasoningEfforts.map((e) => DropdownMenuItem<String>(value: e.id, child: _OptionRow(label: e.label))).toList(),
        onChanged: (v) => _updateConfig(reasoningEffort: v),
      ), widget.freezeModelAndEffort));
      widgets.add(const SizedBox(height: 16));
    }

    if (agent.permissionModes.isNotEmpty) {
      // Same common + opt-ins shape as thinkingEfforts above. `auto` only
      // appears for Opus 4.7+ because only those models name it in their
      // per-model array.
      final optInsPerm = <String>{};
      if (_config.model != null && agent.models != null) {
        final m = agent.models!.firstWhere((m) => m.id == _config.model, orElse: () => CatalogModel(id: _config.model!, label: _config.model!));
        if (m.permissionModes != null) optInsPerm.addAll(m.permissionModes!);
      }
      final modes = agent.permissionModes.where((e) => !e.optIn || optInsPerm.contains(e.id)).toList();
      final selectedPerm = modes.any((e) => e.id == _config.permissionMode)
          ? _config.permissionMode
          : (modes.isNotEmpty ? (modes.firstWhere((e) => e.isDefault, orElse: () => modes.first).id) : null);
      widgets.add(_sectionLabel(context, AppLocalizations.of(context).agentConfigPermission));
      widgets.add(const SizedBox(height: 8));
      widgets.add(_freeze(_StyledDropdown<String>(
        value: selectedPerm,
        items: modes.map((e) => DropdownMenuItem<String>(value: e.id, child: _OptionRow(label: e.label))).toList(),
        onChanged: (v) => _updateConfig(permissionMode: v),
      ), widget.freezePermission));
      widgets.add(const SizedBox(height: 16));
    }

    if (agent.modes.isNotEmpty) {
      widgets.add(_sectionLabel(context, AppLocalizations.of(context).agentConfigMode));
      widgets.add(const SizedBox(height: 8));
      widgets.add(_freeze(_StyledDropdown<String>(
        value: agent.modes.any((e) => e.id == _config.opencodeMode) ? _config.opencodeMode : null,
        items: agent.modes.map((e) => DropdownMenuItem<String>(value: e.id, child: _OptionRow(label: e.label))).toList(),
        onChanged: (v) => _updateConfig(opencodeMode: v),
      ), widget.freezeOpencodeMode));
    }

    final note = widget.footerNote;
    if (note != null && note.isNotEmpty) {
      widgets.add(const SizedBox(height: 16));
      widgets.add(Text(
        note,
        style: theme.bodySmall.override(
          font: GoogleFonts.sourceSans3(fontStyle: FontStyle.italic),
          fontSize: 15.0,
          color: theme.secondaryText,
          fontStyle: FontStyle.italic,
        ),
      ));
      widgets.add(const SizedBox(height: 8));
    }

    return widgets;
  }
}

Widget _sectionLabel(BuildContext context, String label) {
  final theme = FlutterFlowTheme.of(context);
  return Text(
    label,
    style: theme.labelMedium.override(
      font: GoogleFonts.sourceSans3(),
      fontSize: 15.0,
      fontWeight: FontWeight.w500,
      color: theme.secondaryText,
    ),
  );
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
  const _SheetHeader({required this.title, required this.canConfirm, required this.onClose, required this.onConfirm});
  final String title;
  final bool canConfirm;
  final VoidCallback onClose;
  final VoidCallback onConfirm;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
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
        FlutterFlowIconButton(
          borderColor: canConfirm ? theme.primary : theme.alternate,
          borderRadius: 10.0,
          borderWidth: 1.0,
          buttonSize: 40.0,
          fillColor: canConfirm ? theme.primary : null,
          icon: Icon(
            Icons.check_rounded,
            color: canConfirm ? theme.info : theme.secondaryText,
            size: 20.0,
          ),
          onPressed: canConfirm ? onConfirm : null,
        ),
      ]),
    );
  }
}

class _OptionRow extends StatelessWidget {
  const _OptionRow({required this.label, this.description, this.trailing, this.dimmed = false, this.leading});
  final String label;
  final String? description;

  /// Right-aligned note (e.g. "Not installed") for a disabled option.
  final String? trailing;

  /// Mute the label + icon — used for unselectable (uninstalled) agents.
  final bool dimmed;

  /// Optional leading widget (the agent logo in the agent picker).
  final Widget? leading;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final labelStyle = theme.bodyMedium.override(
      font: GoogleFonts.sourceSans3(),
      fontSize: 16.0,
      color: dimmed ? theme.secondaryText.withValues(alpha: 0.5) : null,
    );

    final leadingWidget = leading == null
        ? null
        : (dimmed ? Opacity(opacity: 0.4, child: leading!) : leading!);

    // Label-only row (no description, no trailing note).
    if (description == null && trailing == null) {
      if (leadingWidget == null) {
        return Text(label, style: labelStyle, overflow: TextOverflow.ellipsis);
      }
      return Row(children: [
        leadingWidget,
        const SizedBox(width: 10),
        Flexible(child: Text(label, style: labelStyle, overflow: TextOverflow.ellipsis)),
      ]);
    }

    return Row(children: [
      if (leadingWidget != null) ...[leadingWidget, const SizedBox(width: 10)],
      // Expanded when there's a right-pinned trailing note (so it hugs the
      // right edge consistently); Flexible when sharing the row with a
      // description instead.
      if (trailing != null)
        Expanded(child: Text(label, style: labelStyle, overflow: TextOverflow.ellipsis))
      else
        Flexible(child: Text(label, style: labelStyle, overflow: TextOverflow.ellipsis)),
      if (description != null) ...[
        const SizedBox(width: 8),
        Flexible(child: Text(description!, style: theme.bodySmall.override(font: GoogleFonts.sourceSans3(), fontSize: 13.0, color: theme.secondaryText), overflow: TextOverflow.ellipsis)),
      ],
      if (trailing != null) ...[
        const SizedBox(width: 8),
        Text(trailing!, style: theme.labelSmall.override(font: GoogleFonts.sourceSans3(), fontSize: 13.0, color: theme.secondaryText.withValues(alpha: 0.6))),
      ],
    ]);
  }
}

/// Dropdown matching the machine-card style on the new-session screen:
/// primaryBackground card, 16-radius corners, source-sans 16pt items.
class _StyledDropdown<T> extends StatelessWidget {
  const _StyledDropdown({required this.value, required this.items, required this.onChanged});
  final T? value;
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T?> onChanged;

  // Fixed item height + known menu top padding lets us compute the offset that
  // lands the selected item directly on top of the trigger (spinner behavior).
  static const double _itemHeight = 48.0; // kMinInteractiveDimension
  static const double _menuPaddingTop = 8.0; // kMaterialListPadding.top
  static const AnimationStyle _menuAnimation = AnimationStyle(
    duration: Duration(milliseconds: 240),
    reverseDuration: Duration(milliseconds: 200),
    curve: Curves.easeOutCubic,
    reverseCurve: Curves.easeInCubic,
  );

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final itemStyle = theme.bodyMedium.override(font: GoogleFonts.sourceSans3(), fontSize: 16.0);
    final selectedIndex = items.indexWhere((i) => i.value == value);
    final selected = selectedIndex >= 0 ? items[selectedIndex] : null;
    // Anchor over the trigger and shift up by (selectedIndex * itemHeight + menu top padding)
    // so the selected row replaces the trigger in place — no "appear-then-reposition" jump.
    // Flutter's _fitInsideScreen still nudges the menu if it would clip; that's an acceptable fallback.
    final selectedOffset = selectedIndex >= 0 ? -(selectedIndex * _itemHeight + _menuPaddingTop) : 0.0;
    // PopupMenuButton (not DropdownButtonFormField) so we can put a border on the popup PANEL via `shape`.
    // LayoutBuilder measures the trigger width so the popup panel matches it exactly.
    return LayoutBuilder(builder: (context, constraints) {
      final triggerWidth = constraints.maxWidth;
      return PopupMenuButton<T>(
        initialValue: selected?.value,
        color: theme.primaryBackground,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16.0),
          side: BorderSide(color: theme.secondaryText.withValues(alpha: 0.25), width: 0.75),
        ),
        constraints: BoxConstraints.tightFor(width: triggerWidth),
        position: PopupMenuPosition.over,
        offset: Offset(0, selectedOffset),
        popUpAnimationStyle: _menuAnimation,
        itemBuilder: (context) => items.map((item) => PopupMenuItem<T>(
          value: item.value,
          height: _itemHeight,
          child: DefaultTextStyle(style: itemStyle, child: item.child),
        )).toList(),
        onSelected: onChanged,
        child: Container(
          decoration: BoxDecoration(
            color: theme.primaryBackground,
            borderRadius: BorderRadius.circular(16.0),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 14.0),
          child: DefaultTextStyle(
            style: itemStyle,
            child: Row(children: [
              Expanded(child: selected?.child ?? const SizedBox.shrink()),
              Icon(Icons.keyboard_arrow_down_rounded, color: theme.secondaryText, size: 24.0),
            ]),
          ),
        ),
      );
    });
  }
}
