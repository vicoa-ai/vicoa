import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '/constants/slash_commands.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';

class SlashCommandTrigger extends StatelessWidget {
  const SlashCommandTrigger({super.key, required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(20.0),
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        child: Tooltip(
          message: AppLocalizations.of(context).agentChatShowSlashCommands,
          child: Container(
            width: 40.0,
            height: 40.0,
            alignment: Alignment.center,
            child: Container(
              width: 20.0,
              height: 20.0,
              decoration: BoxDecoration(
                color: Colors.transparent,
                borderRadius: BorderRadius.circular(6.0),
                border: Border.all(
                  color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.8),
                  width: 1.0,
                ),
              ),
              child: Transform.translate(
                offset: const Offset(0, -0.8),
                child: Text(
                  '/',
                  textAlign: TextAlign.center,
                  style: FlutterFlowTheme.of(context).bodyMedium.override(
                        color: FlutterFlowTheme.of(context).secondaryText,
                        fontSize: 12.0,
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class SlashCommandSuggestions extends StatelessWidget {
  const SlashCommandSuggestions({
    super.key,
    required this.visible,
    required this.commands,
    required this.onCommandSelected,
    this.margin = const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 12.0, 12.0),
  });

  final bool visible;
  final List<SlashCommand> commands;
  final Future<void> Function(SlashCommand) onCommandSelected;
  final EdgeInsetsGeometry margin;

  @override
  Widget build(BuildContext context) {
    if (!visible || commands.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      constraints: const BoxConstraints(
        maxHeight: 185.0,
      ),
      margin: margin,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).secondaryBackground,
        borderRadius: BorderRadius.circular(16.0),
        border: Border.all(
          color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.15),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 8.0,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: ListView.builder(
        shrinkWrap: true,
        padding: const EdgeInsets.all(0.0),
        itemCount: commands.length,
        itemBuilder: (context, index) {
          final command = commands[index];
          final name = command.command;
          final description = command.description;
          final isFirst = index == 0;
          final isLast = index == commands.length - 1;
          final itemRadius = isFirst
              ? const BorderRadius.vertical(top: Radius.circular(16.0))
              : isLast
                  ? const BorderRadius.vertical(bottom: Radius.circular(16.0))
                  : BorderRadius.zero;

          return Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: itemRadius,
              onTap: () => onCommandSelected(command),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 18.0, vertical: 12.0),
                decoration: BoxDecoration(
                  borderRadius: itemRadius,
                  color: Colors.transparent,
                ),
                child: Row(
                  children: [
                    Text(
                      name,
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
                        fontWeight: FontWeight.w700,
                        fontSize: 15.0,
                        color: FlutterFlowTheme.of(context).primaryText,
                      ),
                    ),
                    if (description.isNotEmpty) ...[
                      const SizedBox(width: 12.0),
                      Expanded(
                        child: Text(
                          description,
                          style: FlutterFlowTheme.of(context).bodySmall.override(
                            fontSize: 14.0,
                            color: FlutterFlowTheme.of(context).secondaryText,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                    if (command.isSkill) ...[
                      const SizedBox(width: 8.0),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6.0, vertical: 2.0),
                        decoration: BoxDecoration(
                          color: FlutterFlowTheme.of(context).primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(4.0),
                        ),
                        child: Text(
                          'Skill',
                          style: FlutterFlowTheme.of(context).bodySmall.override(
                            fontSize: 10.0,
                            fontWeight: FontWeight.w600,
                            color: FlutterFlowTheme.of(context).primary,
                            letterSpacing: 0.4,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
