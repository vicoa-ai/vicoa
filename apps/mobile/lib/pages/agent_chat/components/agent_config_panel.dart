import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '/backend/agent_catalog.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '../agent_chat_model.dart';

/// Chrome-less radio-panel body for the chat trigger overlay.
///
/// Caller wraps this in a positioned Card / floating container with its own
/// dismiss behavior (see `_AgentConfigPill` in `chat_input_area.dart`).
///
/// v1 scope: Permission column is the only editable surface; Model +
/// Thinking/Reasoning rows are rendered for layout preview but disabled —
/// wiring them needs `instance_metadata.{model, thinking_effort,
/// reasoning_effort}` to be plumbed from the backend through `instanceData`
/// first.
class ChatAgentConfigBody extends StatefulWidget {
  const ChatAgentConfigBody({super.key, required this.model, this.showYoloMode = false});
  final AgentChatModel model;
  final bool showYoloMode;

  @override
  State<ChatAgentConfigBody> createState() => _ChatAgentConfigBodyState();
}

class _ChatAgentConfigBodyState extends State<ChatAgentConfigBody> {
  // Local mirror so radio taps feel instant; the backend confirms via the
  // chat model's existing pending→confirmed cycle.
  late AgentPermissionMode _localPermission;
  late OpencodeAgentMode _localOpencode;
  // TODO: swap to live AgentCatalog once the chat side fetches it (today only
  // new_session_model loads it). Fallback covers v1.
  final AgentCatalog _catalog = agentCatalogFallback();

  @override
  void initState() {
    super.initState();
    _localPermission = widget.model.pendingPermissionMode ?? widget.model.permissionMode;
    _localOpencode = widget.model.pendingOpencodeAgentMode ?? widget.model.opencodeAgentMode;
  }

  String _agentId() {
    if (widget.model.isOpencodeAgent()) return 'opencode';
    if (widget.model.supportsControlSettings()) return 'claude';
    return 'codex';
  }

  void _selectPermission(AgentPermissionMode mode) {
    if (_localPermission == mode) return;
    setState(() => _localPermission = mode);
    HapticFeedback.lightImpact();
    widget.model.requestPermissionModeChange(mode);
  }

  void _selectOpencodeMode(OpencodeAgentMode mode) {
    if (_localOpencode == mode) return;
    setState(() => _localOpencode = mode);
    HapticFeedback.lightImpact();
    widget.model.requestOpencodeAgentModeChange(mode);
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final agentId = _agentId();
    final agent = _catalog.agentById(agentId);
    if (agent == null) {
      return Padding(padding: const EdgeInsets.all(8.0), child: Text(AppLocalizations.of(context).agentConfigPanelUnknownAgent));
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: _buildSections(theme, agent, agentId),
    );
  }

  List<Widget> _buildSections(FlutterFlowTheme theme, CatalogAgent agent, String agentId) {
    final widgets = <Widget>[];
    if (agent.models != null && agent.models!.isNotEmpty) {
      widgets.add(_SectionLabel(label: AppLocalizations.of(context).agentConfigPanelModel));
      widgets.add(const SizedBox(height: 10));
      widgets.add(_RadioGrid(
        options: agent.models!.map((m) => _RadioOption(id: m.id, label: m.label)).toList(),
        selectedId: null,
        disabled: true,
        onChanged: (_) {},
      ));
      widgets.add(const SizedBox(height: 20));
      widgets.add(const _Divider());
      widgets.add(const SizedBox(height: 20));
    }
    widgets.add(_buildBottomRow(theme, agent, agentId));
    return widgets;
  }

  Widget _buildBottomRow(FlutterFlowTheme theme, CatalogAgent agent, String agentId) {
    final cols = <Widget>[];
    if (agentId == 'opencode' && agent.modes.isNotEmpty) {
      cols.add(Expanded(child: _RadioColumn(
        title: AppLocalizations.of(context).agentConfigPanelMode,
        options: agent.modes.map((m) => _RadioOption(id: m.id, label: m.label)).toList(),
        selectedId: _localOpencode.apiValue,
        pendingId: widget.model.pendingOpencodeAgentMode?.apiValue,
        onChanged: (id) => _selectOpencodeMode(OpencodeAgentMode.values.firstWhere((e) => e.apiValue == id, orElse: () => OpencodeAgentMode.build)),
      )));
    } else if (agent.permissionModes.isNotEmpty) {
      final modes = agent.permissionModes.where((m) => widget.showYoloMode || m.id != 'bypassPermissions').toList();
      cols.add(Expanded(child: _RadioColumn(
        title: AppLocalizations.of(context).agentConfigPanelPermission,
        options: modes.map((m) => _RadioOption(id: m.id, label: m.label)).toList(),
        selectedId: _localPermission.controlValue,
        pendingId: widget.model.pendingPermissionMode?.controlValue,
        onChanged: (id) => _selectPermission(AgentPermissionMode.values.firstWhere((e) => e.controlValue == id, orElse: () => AgentPermissionMode.defaultMode)),
      )));
    }

    final isCodex = agentId == 'codex';
    final efforts = isCodex ? agent.reasoningEfforts : agent.thinkingEfforts;
    if (agentId != 'opencode' && efforts.isNotEmpty) {
      if (cols.isNotEmpty) cols.add(const SizedBox(width: 12));
      cols.add(Expanded(child: _RadioColumn(
        title: isCodex
            ? AppLocalizations.of(context).agentConfigPanelReasoning
            : AppLocalizations.of(context).agentConfigPanelThinking,
        options: efforts.map((e) => _RadioOption(id: e.id, label: e.label)).toList(),
        selectedId: null,
        disabled: true,
        onChanged: (_) {},
      )));
    }
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: cols);
  }
}

class _RadioOption {
  const _RadioOption({required this.id, required this.label});
  final String id;
  final String label;
}

/// Same radio panel design as the chat trigger, but fully editable: agent
/// chips on top, then model grid, then bottom row (Permission + Thinking /
/// Reasoning, or Mode for OpenCode). Used by the new-session screen.
///
/// `agent_config_sheet.dart` is left on disk unchanged so it can be re-enabled
/// or A/B-tested without touching this file.
Future<SessionConfig?> showAgentConfigPanelForNewSession({
  required BuildContext context,
  required AgentCatalog catalog,
  required SessionConfig initial,
}) async {
  return showModalBottomSheet<SessionConfig>(
    context: context,
    isScrollControlled: true,
    useSafeArea: false,
    backgroundColor: Colors.transparent,
    builder: (ctx) => _AgentConfigPanelForNewSession(catalog: catalog, initial: initial),
  );
}

class _AgentConfigPanelForNewSession extends StatefulWidget {
  const _AgentConfigPanelForNewSession({required this.catalog, required this.initial});
  final AgentCatalog catalog;
  final SessionConfig initial;

  @override
  State<_AgentConfigPanelForNewSession> createState() => _AgentConfigPanelForNewSessionState();
}

class _AgentConfigPanelForNewSessionState extends State<_AgentConfigPanelForNewSession> {
  late SessionConfig _config;

  @override
  void initState() {
    super.initState();
    _config = widget.initial.reconcileAgainst(widget.catalog);
  }

  void _switchAgent(String nextAgentId) {
    if (_config.agent == nextAgentId) return;
    setState(() => _config = SessionConfig.defaultsFor(widget.catalog, nextAgentId));
  }

  void _update({String? model, String? thinkingEffort, String? reasoningEffort, String? permissionMode, String? opencodeMode}) {
    setState(() => _config = SessionConfig(
          agent: _config.agent,
          model: model ?? _config.model,
          thinkingEffort: thinkingEffort ?? _config.thinkingEffort,
          reasoningEffort: reasoningEffort ?? _config.reasoningEffort,
          permissionMode: permissionMode ?? _config.permissionMode,
          opencodeMode: opencodeMode ?? _config.opencodeMode,
        ));
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final agent = widget.catalog.agentById(_config.agent);
    final maxHeight = MediaQuery.of(context).size.height * 0.85;
    return Container(
      width: double.infinity,
      constraints: BoxConstraints(maxHeight: maxHeight),
      decoration: BoxDecoration(
        color: theme.secondaryBackground,
        borderRadius: const BorderRadius.only(topLeft: Radius.circular(24.0), topRight: Radius.circular(24.0)),
      ),
      child: SafeArea(
        top: false,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          _Handle(),
          _Header(
            title: AppLocalizations.of(context).agentConfigPanelAgent,
            onClose: () { HapticFeedback.lightImpact(); Navigator.pop(context); },
            onDone: () { HapticFeedback.lightImpact(); Navigator.pop(context, _config); },
          ),
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 16.0),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                _SectionLabel(label: AppLocalizations.of(context).agentConfigPanelAgent),
                const SizedBox(height: 10),
                _AgentChipRow(
                  agents: widget.catalog.agents,
                  selectedId: _config.agent,
                  onChanged: _switchAgent,
                ),
                if (agent == null)
                  Padding(padding: const EdgeInsets.only(top: 24.0), child: Text(AppLocalizations.of(context).agentConfigPanelUnknownAgent))
                else ...[
                  const SizedBox(height: 24),
                  const _Divider(),
                  const SizedBox(height: 24),
                  ..._buildAgentSections(theme, agent),
                ],
              ]),
            ),
          ),
        ]),
      ),
    );
  }

  List<Widget> _buildAgentSections(FlutterFlowTheme theme, CatalogAgent agent) {
    final widgets = <Widget>[];
    if (agent.models != null && agent.models!.isNotEmpty) {
      widgets.add(_SectionLabel(label: AppLocalizations.of(context).agentConfigPanelModel));
      widgets.add(const SizedBox(height: 10));
      widgets.add(_RadioGrid(
        options: agent.models!.map((m) => _RadioOption(id: m.id, label: m.label)).toList(),
        selectedId: _config.model,
        onChanged: (id) => _update(model: id),
      ));
      widgets.add(const SizedBox(height: 24));
      widgets.add(const _Divider());
      widgets.add(const SizedBox(height: 24));
    }

    // Effort lists may be model-restricted (Opus carries `xhigh`; Sonnet/Haiku
    // don't). Filter to the intersection so users only see legal options.
    List<CatalogEnumEntry> filteredThinking() {
      if (_config.model == null || agent.models == null) return agent.thinkingEfforts;
      final model = agent.models!.firstWhere((m) => m.id == _config.model, orElse: () => CatalogModel(id: _config.model!, label: _config.model!));
      if (model.thinkingEfforts == null) return agent.thinkingEfforts;
      final allowed = model.thinkingEfforts!.toSet();
      return agent.thinkingEfforts.where((e) => allowed.contains(e.id)).toList();
    }

    final isOpencode = _config.agent == 'opencode';
    final cols = <Widget>[];
    if (isOpencode && agent.modes.isNotEmpty) {
      cols.add(Expanded(child: _RadioColumn(
        title: AppLocalizations.of(context).agentConfigPanelMode,
        options: agent.modes.map((m) => _RadioOption(id: m.id, label: m.label)).toList(),
        selectedId: _config.opencodeMode,
        onChanged: (id) => _update(opencodeMode: id),
      )));
    } else if (agent.permissionModes.isNotEmpty) {
      cols.add(Expanded(child: _RadioColumn(
        title: AppLocalizations.of(context).agentConfigPanelPermission,
        options: agent.permissionModes.map((m) => _RadioOption(id: m.id, label: m.label)).toList(),
        selectedId: _config.permissionMode,
        onChanged: (id) => _update(permissionMode: id),
      )));
    }

    if (!isOpencode) {
      final thinkings = filteredThinking();
      if (thinkings.isNotEmpty) {
        if (cols.isNotEmpty) cols.add(const SizedBox(width: 12));
        cols.add(Expanded(child: _RadioColumn(
          title: AppLocalizations.of(context).agentConfigPanelThinking,
          options: thinkings.map((e) => _RadioOption(id: e.id, label: e.label)).toList(),
          selectedId: thinkings.any((e) => e.id == _config.thinkingEffort) ? _config.thinkingEffort : null,
          onChanged: (id) => _update(thinkingEffort: id),
        )));
      } else if (agent.reasoningEfforts.isNotEmpty) {
        if (cols.isNotEmpty) cols.add(const SizedBox(width: 12));
        cols.add(Expanded(child: _RadioColumn(
          title: AppLocalizations.of(context).agentConfigPanelReasoning,
          options: agent.reasoningEfforts.map((e) => _RadioOption(id: e.id, label: e.label)).toList(),
          selectedId: _config.reasoningEffort,
          onChanged: (id) => _update(reasoningEffort: id),
        )));
      }
    }

    if (cols.isNotEmpty) {
      widgets.add(Row(crossAxisAlignment: CrossAxisAlignment.start, children: cols));
    }
    return widgets;
  }
}

/// Compact horizontal chip-row of agents (claude / codex / opencode).
class _AgentChipRow extends StatelessWidget {
  const _AgentChipRow({required this.agents, required this.selectedId, required this.onChanged});
  final List<CatalogAgent> agents;
  final String selectedId;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Wrap(
      spacing: 8.0,
      runSpacing: 8.0,
      children: agents.map((a) {
        final isSelected = a.id == selectedId;
        return Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(8.0),
            onTap: () { HapticFeedback.lightImpact(); onChanged(a.id); },
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4.0, vertical: 8.0),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                _RadioDot(isSelected: isSelected),
                const SizedBox(width: 8),
                Text(
                  a.label,
                  style: theme.bodyMedium.override(
                    font: GoogleFonts.sourceSans3(),
                    fontSize: 14.0,
                    color: isSelected ? theme.primaryText : theme.secondaryText,
                  ),
                ),
              ]),
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _RadioColumn extends StatelessWidget {
  const _RadioColumn({
    required this.title,
    required this.options,
    required this.selectedId,
    required this.onChanged,
    this.disabled = false,
    this.pendingId,
  });
  final String title;
  final List<_RadioOption> options;
  final String? selectedId;
  final ValueChanged<String> onChanged;
  final bool disabled;
  final String? pendingId;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: disabled ? 0.5 : 1.0,
      child: IgnorePointer(
        ignoring: disabled,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _SectionLabel(label: title),
          const SizedBox(height: 8),
          ...options.map((opt) => _RadioRow(
            label: opt.label,
            isSelected: opt.id == selectedId,
            isPending: pendingId != null && opt.id == pendingId,
            onTap: () => onChanged(opt.id),
          )),
        ]),
      ),
    );
  }
}

class _RadioGrid extends StatelessWidget {
  const _RadioGrid({required this.options, required this.selectedId, required this.onChanged, this.disabled = false});
  final List<_RadioOption> options;
  final String? selectedId;
  final ValueChanged<String> onChanged;
  final bool disabled;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: disabled ? 0.5 : 1.0,
      child: IgnorePointer(
        ignoring: disabled,
        child: LayoutBuilder(builder: (context, constraints) {
          const spacing = 8.0;
          final itemWidth = (constraints.maxWidth - spacing) / 2;
          return Wrap(
            spacing: spacing,
            // Keep row-gap aligned with the column variant (each card already
            // has vertical: 3 padding; no extra runSpacing or models look
            // more "spatial" than Permission/Thinking).
            runSpacing: 0.0,
            children: options.map((opt) => SizedBox(
              width: itemWidth,
              child: _RadioCard(
                label: opt.label,
                isSelected: opt.id == selectedId,
                onTap: () => onChanged(opt.id),
              ),
            )).toList(),
          );
        }),
      ),
    );
  }
}

class _RadioCard extends StatelessWidget {
  const _RadioCard({required this.label, required this.isSelected, required this.onTap});
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(8.0),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4.0, vertical: 6.0),
          child: Row(children: [
            _RadioDot(isSelected: isSelected),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: theme.bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  fontSize: 14.0,
                  color: isSelected ? theme.primaryText : theme.secondaryText,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _RadioRow extends StatelessWidget {
  const _RadioRow({required this.label, required this.isSelected, required this.onTap, this.isPending = false});
  final String label;
  final bool isSelected;
  final bool isPending;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(8.0),
        onTap: isPending ? null : onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4.0, vertical: 6.0),
          child: Row(children: [
            if (isPending)
              SizedBox(
                width: 18.0,
                height: 18.0,
                child: CircularProgressIndicator(strokeWidth: 2.0, valueColor: AlwaysStoppedAnimation<Color>(theme.primary)),
              )
            else
              _RadioDot(isSelected: isSelected),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: theme.bodyMedium.override(
                  font: GoogleFonts.sourceSans3(),
                  fontSize: 14.0,
                  color: isSelected ? theme.primaryText : theme.secondaryText,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ]),
        ),
      ),
    );
  }
}

class _RadioDot extends StatelessWidget {
  const _RadioDot({required this.isSelected});
  final bool isSelected;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Container(
      width: 18.0,
      height: 18.0,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: isSelected ? theme.primary : theme.secondaryText.withValues(alpha: 0.4),
          width: 2.0,
        ),
      ),
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 150),
        opacity: isSelected ? 1.0 : 0.0,
        child: Container(
          margin: const EdgeInsets.all(3.0),
          decoration: BoxDecoration(color: theme.primary, shape: BoxShape.circle),
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    return Text(
      label,
      style: theme.labelMedium.override(
        font: GoogleFonts.sourceSans3(),
        fontSize: 13.0,
        fontWeight: FontWeight.w600,
        color: theme.secondaryText,
        letterSpacing: 0.3,
      ),
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider();
  @override
  Widget build(BuildContext context) {
    return Container(
      height: 1.0,
      color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.08),
    );
  }
}

class _Handle extends StatelessWidget {
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

class _Header extends StatelessWidget {
  const _Header({required this.title, required this.onClose, required this.onDone});
  final String title;
  final VoidCallback onClose;
  final VoidCallback onDone;
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
          borderColor: theme.primary,
          borderRadius: 10.0,
          borderWidth: 1.0,
          buttonSize: 40.0,
          fillColor: theme.primary,
          icon: Icon(Icons.check_rounded, color: theme.info, size: 20.0),
          onPressed: onDone,
        ),
      ]),
    );
  }
}
