import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import '../agent_chat_model.dart';

class ControlSettingsSelector extends StatefulWidget {
  const ControlSettingsSelector({
    super.key,
    this.selectedPermissionMode,
    this.onPermissionModeSelected,
    this.pendingPermissionMode,
    this.selectedOpencodeMode,
    this.onOpencodeModeSelected,
    this.pendingOpencodeMode,
    this.thinkingEnabled,
    this.onThinkingToggle,
    this.showYoloMode = false,
  });

  final AgentPermissionMode? selectedPermissionMode;
  final ValueChanged<AgentPermissionMode>? onPermissionModeSelected;
  final AgentPermissionMode? pendingPermissionMode;
  final OpencodeAgentMode? selectedOpencodeMode;
  final ValueChanged<OpencodeAgentMode>? onOpencodeModeSelected;
  final OpencodeAgentMode? pendingOpencodeMode;
  final bool? thinkingEnabled;
  final ValueChanged<bool>? onThinkingToggle;
  final bool showYoloMode;

  @override
  State<ControlSettingsSelector> createState() => _ControlSettingsSelectorState();
}

class _ControlSettingsSelectorState extends State<ControlSettingsSelector> {
  final GlobalKey _buttonKey = GlobalKey();
  OverlayEntry? _overlayEntry;

  @override
  void dispose() {
    _removeOverlay();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);

    return Container(
      width: 40.0,
      height: 40.0,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20.0),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          key: _buttonKey,
          borderRadius: BorderRadius.circular(20.0),
          onTap: _toggleMenu,
          child: Icon(
            Icons.settings_outlined,
            size: 20.0,
            color: theme.secondaryText,
          ),
        ),
      ),
    );
  }

  void _toggleMenu() {
    HapticFeedback.lightImpact();
    if (_overlayEntry == null) {
      _showOverlay();
    } else {
      _removeOverlay();
    }
  }

  void _showOverlay() {
    final overlayState = Overlay.of(context);
    final renderBox = _buttonKey.currentContext?.findRenderObject() as RenderBox?;

    if (overlayState == null || renderBox == null) {
      return;
    }

    final overlayRenderBox = overlayState.context.findRenderObject() as RenderBox;
    final buttonOffset = renderBox.localToGlobal(Offset.zero, ancestor: overlayRenderBox);
    final buttonSize = renderBox.size;

    const menuWidth = 220.0;
    const optionHeight = 40.0;
    const headerHeight = 20.0;
    const headerSpacing = 12.0;
    const verticalPadding = 32.0; // top + bottom padding inside the menu
    const thinkingButtonsHeight = 44.0;
    final hasThinkingControl = widget.onThinkingToggle != null;
    final hasPermissionControl = widget.onPermissionModeSelected != null;
    final hasOpencodeControl = widget.onOpencodeModeSelected != null;

    final thinkingSectionHeight = hasThinkingControl
        ? headerHeight + headerSpacing + thinkingButtonsHeight
        : 0.0;

    // Filter permission modes based on showYoloMode
    final visibleModes = widget.showYoloMode
        ? AgentPermissionMode.values
        : AgentPermissionMode.values.where((mode) => mode != AgentPermissionMode.bypassPermissions).toList();

    final permissionSectionHeight = hasPermissionControl
        ? headerHeight + headerSpacing + (visibleModes.length * optionHeight)
        : 0.0;

    final opencodeSectionHeight = hasOpencodeControl
        ? headerHeight + headerSpacing + (OpencodeAgentMode.values.length * optionHeight)
        : 0.0;

    final menuHeight = verticalPadding + permissionSectionHeight + opencodeSectionHeight + thinkingSectionHeight;
    const verticalGap = 8.0;
    const horizontalPadding = 16.0;

    double left = buttonOffset.dx - (menuWidth / 2) + (buttonSize.width / 2);
    if (left + menuWidth > overlayRenderBox.size.width - horizontalPadding) {
      left = overlayRenderBox.size.width - menuWidth - horizontalPadding;
    }
    if (left < horizontalPadding) {
      left = horizontalPadding;
    }

    double top = buttonOffset.dy - menuHeight - verticalGap;
    if (top < horizontalPadding) {
      top = buttonOffset.dy + buttonSize.height + verticalGap;
    }

    _overlayEntry = OverlayEntry(
      builder: (context) {
        return Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onTap: _removeOverlay,
              ),
            ),
            Positioned(
              left: left,
              top: top,
              width: menuWidth,
              child: _ControlSettingsMenu(
                selectedMode: widget.selectedPermissionMode,
                pendingMode: widget.pendingPermissionMode,
                selectedOpencodeMode: widget.selectedOpencodeMode,
                pendingOpencodeMode: widget.pendingOpencodeMode,
                thinkingEnabled: widget.thinkingEnabled,
                onThinkingToggle: widget.onThinkingToggle,
                showYoloMode: widget.showYoloMode,
                onModeSelected: widget.onPermissionModeSelected != null ? (mode) {
                  widget.onPermissionModeSelected!(mode);
                  _removeOverlay();
                } : null,
                onOpencodeModeSelected: widget.onOpencodeModeSelected != null ? (mode) {
                  widget.onOpencodeModeSelected!(mode);
                  _removeOverlay();
                } : null,
                onClose: _removeOverlay,
              ),
            ),
          ],
        );
      },
    );

    overlayState.insert(_overlayEntry!);
  }

  void _removeOverlay() {
    _overlayEntry?.remove();
    _overlayEntry = null;
  }
}

class _ControlSettingsMenu extends StatelessWidget {
  const _ControlSettingsMenu({
    required this.onClose,
    this.selectedMode,
    this.pendingMode,
    this.onModeSelected,
    this.selectedOpencodeMode,
    this.pendingOpencodeMode,
    this.onOpencodeModeSelected,
    this.thinkingEnabled,
    this.onThinkingToggle,
    this.showYoloMode = false,
  });

  final AgentPermissionMode? selectedMode;
  final AgentPermissionMode? pendingMode;
  final ValueChanged<AgentPermissionMode>? onModeSelected;
  final OpencodeAgentMode? selectedOpencodeMode;
  final OpencodeAgentMode? pendingOpencodeMode;
  final ValueChanged<OpencodeAgentMode>? onOpencodeModeSelected;
  final bool? thinkingEnabled;
  final ValueChanged<bool>? onThinkingToggle;
  final VoidCallback onClose;
  final bool showYoloMode;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final thinkingHandler = onThinkingToggle;
    final hasThinkingControl = thinkingHandler != null;
    final hasPermissionControl = onModeSelected != null;
    final hasOpencodeControl = onOpencodeModeSelected != null;

    // Filter permission modes based on showYoloMode
    final visibleModes = showYoloMode
        ? AgentPermissionMode.values
        : AgentPermissionMode.values.where((mode) => mode != AgentPermissionMode.bypassPermissions).toList();

    return Material(
      color: Colors.transparent,
      child: Container(
        padding: const EdgeInsets.all(16.0),
        decoration: BoxDecoration(
          color: theme.primaryBackground,
          borderRadius: BorderRadius.circular(20.0),
          border: Border.all(
            color: theme.secondaryText.withValues(alpha: 0.1),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.35),
              blurRadius: 20.0,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (hasPermissionControl) ...[
              Text(
                AppLocalizations.of(context).agentChatPermissionMode,
                style: theme.bodyMedium.override(
                  fontWeight: FontWeight.w600,
                  fontSize: 14.0,
                ),
              ),
              const SizedBox(height: 12.0),
              ...visibleModes.map(
                (mode) => _PermissionModeOption(
                  mode: mode,
                  isSelected: selectedMode == mode,
                  isPending: pendingMode == mode,
                  onTap: () => onModeSelected!(mode),
                ),
              ),
            ],
            if (hasOpencodeControl) ...[
              if (hasPermissionControl)
                Container(
                  height: 1.0,
                  margin: const EdgeInsets.symmetric(vertical: 12.0),
                  color: theme.secondaryText.withValues(alpha: 0.08),
                ),
              Text(
                AppLocalizations.of(context).agentChatAgentMode,
                style: theme.bodyMedium.override(
                  fontWeight: FontWeight.w600,
                  fontSize: 14.0,
                ),
              ),
              const SizedBox(height: 12.0),
              ...OpencodeAgentMode.values.map(
                (mode) => _OpencodeModeOption(
                  mode: mode,
                  isSelected: selectedOpencodeMode == mode,
                  isPending: pendingOpencodeMode == mode,
                  onTap: () => onOpencodeModeSelected!(mode),
                ),
              ),
            ],
            if (hasThinkingControl) ...[
              Container(
                height: 1.0,
                margin: const EdgeInsets.symmetric(vertical: 12.0),
                color: theme.secondaryText.withValues(alpha: 0.08),
              ),
              Text(
                AppLocalizations.of(context).agentChatThinking,
                style: theme.bodyMedium.override(
                  fontWeight: FontWeight.w600,
                  fontSize: 14.0,
                ),
              ),
              const SizedBox(height: 10.0),
              Row(
                children: [
                  Expanded(
                    child: _ThinkingToggleButton(
                      label: AppLocalizations.of(context).agentChatThinkingOn,
                      isActive: thinkingEnabled == true,
                      onTap: () {
                        thinkingHandler!(true);
                        onClose();
                      },
                    ),
                  ),
                  const SizedBox(width: 8.0),
                  Expanded(
                    child: _ThinkingToggleButton(
                      label: AppLocalizations.of(context).agentChatThinkingOff,
                      isActive: thinkingEnabled == false,
                      onTap: () {
                        thinkingHandler!(false);
                        onClose();
                      },
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _PermissionModeOption extends StatelessWidget {
  const _PermissionModeOption({
    required this.mode,
    required this.isSelected,
    required this.onTap,
    this.isPending = false,
  });

  final AgentPermissionMode mode;
  final bool isSelected;
  final VoidCallback onTap;
  final bool isPending;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);

    return InkWell(
      onTap: isPending ? null : () {
        HapticFeedback.lightImpact();
        onTap();
      },
      borderRadius: BorderRadius.circular(14.0),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8.0),
        child: Row(
          children: [
            if (isPending)
              SizedBox(
                width: 18.0,
                height: 18.0,
                child: CircularProgressIndicator(
                  strokeWidth: 2.0,
                  valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
                ),
              )
            else
              Container(
                width: 18.0,
                height: 18.0,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: isSelected
                        ? theme.primary
                        : theme.secondaryText.withValues(alpha: 0.4),
                    width: 2.0,
                  ),
                ),
                child: AnimatedOpacity(
                  duration: const Duration(milliseconds: 150),
                  opacity: isSelected ? 1.0 : 0.0,
                  child: Container(
                    margin: const EdgeInsets.all(3.0),
                    decoration: BoxDecoration(
                      color: theme.primary,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            const SizedBox(width: 12.0),
            Expanded(
              child: Text(
                mode.displayName,
                style: theme.bodyMedium.override(
                  fontSize: 14.0,
                  color: isSelected
                      ? theme.primaryText
                      : theme.secondaryText,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OpencodeModeOption extends StatelessWidget {
  const _OpencodeModeOption({
    required this.mode,
    required this.isSelected,
    required this.onTap,
    this.isPending = false,
  });

  final OpencodeAgentMode mode;
  final bool isSelected;
  final VoidCallback onTap;
  final bool isPending;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);

    return InkWell(
      onTap: isPending ? null : () {
        HapticFeedback.lightImpact();
        onTap();
      },
      borderRadius: BorderRadius.circular(14.0),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8.0),
        child: Row(
          children: [
            if (isPending)
              SizedBox(
                width: 18.0,
                height: 18.0,
                child: CircularProgressIndicator(
                  strokeWidth: 2.0,
                  valueColor: AlwaysStoppedAnimation<Color>(theme.primary),
                ),
              )
            else
              Container(
                width: 18.0,
                height: 18.0,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: isSelected
                        ? theme.primary
                        : theme.secondaryText.withValues(alpha: 0.4),
                    width: 2.0,
                  ),
                ),
                child: AnimatedOpacity(
                  duration: const Duration(milliseconds: 150),
                  opacity: isSelected ? 1.0 : 0.0,
                  child: Container(
                    margin: const EdgeInsets.all(3.0),
                    decoration: BoxDecoration(
                      color: theme.primary,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            const SizedBox(width: 12.0),
            Expanded(
              child: Text(
                mode.displayName,
                style: theme.bodyMedium.override(
                  fontSize: 14.0,
                  color: isSelected
                      ? theme.primaryText
                      : theme.secondaryText,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ThinkingToggleButton extends StatelessWidget {
  const _ThinkingToggleButton({
    required this.label,
    required this.isActive,
    required this.onTap,
  });

  final String label;
  final bool isActive;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final backgroundColor = isActive
        ? theme.primary.withValues(alpha: 0.12)
        : theme.secondaryText.withValues(alpha: 0.1);

    return InkWell(
      borderRadius: BorderRadius.circular(18.0),
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(vertical: 8.0),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(18.0),
        ),
        child: Center(
          child: Text(
            label,
            style: theme.bodyMedium.override(
              fontSize: 12.0,
              fontWeight: FontWeight.w600,
              color: isActive ? theme.primary : theme.secondaryText,
            ),
          ),
        ),
      ),
    );
  }
}
