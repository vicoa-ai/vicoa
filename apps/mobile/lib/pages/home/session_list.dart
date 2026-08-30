import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/agent_type_icon/agent_type_icon_widget.dart';
import '/flutter_flow/custom_functions.dart' as functions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/index.dart';
import '/custom_code/actions/index.dart' as actions;

class SessionCard extends StatelessWidget {
  const SessionCard({
    super.key,
    required this.instance,
    required this.status,
    this.groupBy = 'Time',
    required this.onAction,
    required this.onRemoveInstance,
    required this.onReload,
    required this.onSnackBar,
    this.onLongPressMenu,
  });

  final Map<String, dynamic> instance;
  final String status;
  final String groupBy;
  final Future<void> Function(Map<String, dynamic>, String) onAction;
  final void Function(String id) onRemoveInstance;
  final Future<void> Function() onReload;
  final void Function(String msg) onSnackBar;
  final void Function(Map<String, dynamic> instance, Offset globalPosition)?
      onLongPressMenu;

  @override
  Widget build(BuildContext context) {
    final canComplete =
        status == 'ACTIVE' || status == 'AWAITING_INPUT' || status == 'REVIEWED';

    return _SessionSlideAction(
      canComplete: canComplete,
      onAction: (action) async => onAction(instance, action),
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: 12.0),
        decoration: BoxDecoration(
          color: FlutterFlowTheme.of(context).primaryBackground,
          borderRadius: BorderRadius.circular(20.0),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.04),
              offset: const Offset(0, 2),
              blurRadius: 8.0,
              spreadRadius: 0,
            ),
          ],
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(16.0),
          splashColor:
              FlutterFlowTheme.of(context).primary.withValues(alpha: 0.1),
          focusColor: Colors.transparent,
          hoverColor:
              FlutterFlowTheme.of(context).primary.withValues(alpha: 0.05),
          highlightColor: Colors.transparent,
          onLongPress: onLongPressMenu == null
              ? null
              : () {
                  HapticFeedback.mediumImpact();
                  final box = context.findRenderObject() as RenderBox?;
                  if (box == null) return;
                  final pos = box.localToGlobal(
                    Offset(box.size.width, box.size.height),
                  );
                  onLongPressMenu!(instance, pos);
                },
          onTap: () async {
            logFirebaseEvent('HOME_PAGE_session_card_ON_TAP');
            HapticFeedback.lightImpact();
            final result = await GoRouter.of(context).pushNamed(
              AgentChatWidget.routeName,
              pathParameters: {
                'instanceId': instance['id'],
              },
              extra: <String, dynamic>{
                'instanceData': instance,
                kTransitionInfoKey: const TransitionInfo(
                  hasTransition: true,
                  transitionType: PageTransitionType.rightToLeft,
                ),
              },
            );

            if (result == 'deleted' || result == 'renamed' || result == 'closed') {
              if (result == 'deleted') {
                onRemoveInstance(instance['id'] as String);
              }
              await onReload();
            }

            if (result == 'deleted') {
              onSnackBar(AppLocalizations.of(context).sessionListDeleted);
            } else if (result == 'closed') {
              onSnackBar(AppLocalizations.of(context).sessionListClosed);
            }
          },
          child: Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
            child: SessionCardContent(
                instance: instance, status: status, groupBy: groupBy),
          ),
        ),
      ),
    );
  }
}

class SessionCardContent extends StatelessWidget {
  const SessionCardContent({
    super.key,
    required this.instance,
    required this.status,
    this.groupBy = 'Time',
  });

  final Map<String, dynamic> instance;
  final String status;
  final String groupBy;

  bool get _hasTitle => instance['name']?.toString().isNotEmpty == true;

  String _displayAgentType(String? raw) {
    if (raw == null) return 'Agent';
    if (raw.toLowerCase() == 'claude') return 'Claude Code';
    return raw;
  }

  String _getLatestMessage() {
    final msg = instance['latest_message']?.toString().trim() ?? '';
    return (msg.isNotEmpty &&
            !msg.contains('API Error') &&
            !msg.contains('error'))
        ? msg
        : '';
  }

  String _getProjectLabel() {
    final project = instance['project']?.toString().trim() ?? '';
    if (project.isEmpty) return '';
    final clean = project.endsWith('/')
        ? project.substring(0, project.length - 1)
        : project;
    final last = clean.split('/').last;
    return last.isNotEmpty ? last : '';
  }

  String _getRow1Text() {
    if (_hasTitle) return instance['name'] as String;
    final msg = _getLatestMessage();
    if (msg.isNotEmpty) return msg;
    return _displayAgentType(instance['agent_type_name']?.toString());
  }

  String _getRow2Text() {
    final agentType =
        _displayAgentType(instance['agent_type_name']?.toString());
    if (groupBy == 'Project') {
      if (_hasTitle) {
        final msg = _getLatestMessage();
        return msg.isNotEmpty ? msg : agentType;
      }
      return agentType;
    }
    final label = _getProjectLabel();
    return label.isNotEmpty ? label : agentType;
  }

  @override
  Widget build(BuildContext context) {
    final row1Text = _getRow1Text();
    final row2Text = _getRow2Text();
    final agentTypeName = instance['agent_type_name']?.toString();
    final timeRaw = instance['latest_message_at'] ?? instance['started_at'] ?? '';
    final time = functions.formatRelativeTimeShort(
      DateTime.tryParse(timeRaw) ?? DateTime.now(),
    );

    // `status` is self-reported and freezes at ACTIVE when an agent dies, so
    // the spinner kept animating for a session that was gone. Gate it on the
    // server-derived liveness instead.
    final liveState = (instance is Map) ? instance['live_state']?.toString() : null;
    // A just-resumed session's relaunched agent hasn't heartbeated yet, so the
    // server still reports `agent_stopped`. Suppress the stopped dot during the
    // resume grace so it doesn't linger until a manual refresh — same registry
    // the chat composer uses, so the two never disagree.
    final resumeGrace = actions.isWithinResumeGrace(instance['id']?.toString());
    final liveStateForUi = resumeGrace ? actions.kLiveStateLive : liveState;
    final isReachable =
        liveStateForUi == null || actions.liveStateIsReachable(liveStateForUi);
    final stoppedLabel = actions.liveStateShortLabel(liveStateForUi);

    final isActive = status == 'ACTIVE' && isReachable;
    final isAwaiting = status == 'AWAITING_INPUT';
    final isReviewed = status == 'REVIEWED';
    final isClosed = !isActive && !isAwaiting && !isReviewed;

    final titleWeight =
        (isAwaiting || isActive) ? FontWeight.w500 : FontWeight.w400;
    final titleColor = isClosed
        ? FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.5)
        : FlutterFlowTheme.of(context).primaryText;
    final subtitleColor = isClosed
        ? FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.4)
        : FlutterFlowTheme.of(context).secondaryText;

    return Row(
      children: [
        SizedBox(
          width: 36.0,
          height: 36.0,
          child: Center(
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                AgentTypeIconWidget(
                  agentTypeName: agentTypeName,
                  size: 16.0,
                  spinning: isActive,
                  withBackground: true,
                ),
                // Status badges over the icon, split by meaning: the blue
                // "needs a reply" dot sits top-right like a notification badge
                // (mirrors the web sidebar's sky-400 dot), the grey "not
                // reachable" dot sits bottom-right as a presence indicator.
                // Awaiting-input wins when both would apply. The grey dot only
                // shows for a session that still claims to be usable — a closed
                // one already reads as closed from its dimmed styling.
                if (isAwaiting)
                  Positioned(
                    right: -1.0,
                    top: -2.0,
                    child: Container(
                      width: 12.0,
                      height: 12.0,
                      decoration: BoxDecoration(
                        color: const Color(0xFF38BDF8),
                        shape: BoxShape.circle,
                        border: Border.all(color: FlutterFlowTheme.of(context).primaryBackground, width: 1.5),
                      ),
                    ),
                  )
                else if (stoppedLabel != null && !isClosed)
                  Positioned(
                    right: -1.0,
                    bottom: -1.0,
                    child: Container(
                      width: 12.0,
                      height: 12.0,
                      decoration: BoxDecoration(
                        color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.6),
                        shape: BoxShape.circle,
                        border: Border.all(color: FlutterFlowTheme.of(context).primaryBackground, width: 1.5),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 12.0),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                row1Text,
                style: FlutterFlowTheme.of(context).titleMedium.override(
                      font: GoogleFonts.sourceSans3(fontWeight: titleWeight),
                      color: titleColor,
                      fontSize: 17.0,
                      fontWeight: titleWeight,
                    ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 3.0),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      row2Text,
                      style: FlutterFlowTheme.of(context).bodySmall.override(
                            color: subtitleColor,
                            fontSize: 14.0,
                          ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8.0),
                  Text(
                    time,
                    style: FlutterFlowTheme.of(context).bodySmall.override(
                          color: subtitleColor,
                          fontSize: 13.0,
                        ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(width: 8.0),
      ],
    );
  }
}

class _SessionSlideAction extends StatefulWidget {
  final Widget child;
  final bool canComplete;
  final Function(String) onAction;

  const _SessionSlideAction({
    required this.child,
    required this.canComplete,
    required this.onAction,
  });

  @override
  State<_SessionSlideAction> createState() => _SessionSlideActionState();
}

class _SessionSlideActionState extends State<_SessionSlideAction>
    with TickerProviderStateMixin {
  late AnimationController _slideController;
  late Animation<double> _slideAnimation;
  double _slideOffset = 0.0;
  bool _isSliding = false;

  @override
  void initState() {
    super.initState();
    _slideController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    _slideAnimation = Tween<double>(
      begin: 0.0,
      end: 0.0,
    ).animate(CurvedAnimation(
      parent: _slideController,
      curve: Curves.easeOut,
    ));
  }

  @override
  void dispose() {
    _slideController.dispose();
    super.dispose();
  }

  Widget _buildBackground() {
    final progress = _slideOffset.abs();
    final screenWidth = MediaQuery.of(context).size.width;
    final normalizedProgress = (progress / screenWidth).clamp(0.0, 1.0);

    final bool showComplete = widget.canComplete && normalizedProgress < 0.3;

    Color backgroundColor;
    IconData icon;
    String text;

    if (showComplete) {
      backgroundColor = FlutterFlowTheme.of(context).accent2;
      icon = Icons.archive_rounded;
      text = AppLocalizations.of(context).sessionActionsArchive;
    } else {
      backgroundColor = Colors.red;
      icon = Icons.delete_rounded;
      text = AppLocalizations.of(context).commonDelete;
    }

    return Positioned.fill(
      child: Container(
        margin: const EdgeInsets.only(bottom: 12.0),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20.0),
          child: Container(
            decoration: BoxDecoration(
              color: backgroundColor,
              boxShadow: [
                BoxShadow(
                  color: backgroundColor.withValues(alpha: 0.3),
                  offset: const Offset(0, 2),
                  blurRadius: 4.0,
                  spreadRadius: 0,
                ),
              ],
            ),
            alignment: Alignment.centerRight,
            padding: const EdgeInsets.only(right: 20.0),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  text,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16.0,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 8.0),
                Icon(
                  icon,
                  color: Colors.white,
                  size: 24.0,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onPanStart: (details) {
        _isSliding = true;
        _slideController.stop();
      },
      onPanUpdate: (details) {
        if (_isSliding) {
          setState(() {
            _slideOffset += details.delta.dx;
            if (_slideOffset > 0) _slideOffset = 0;
            final maxSlide = -MediaQuery.of(context).size.width * 0.5;
            if (_slideOffset < maxSlide) _slideOffset = maxSlide;
          });

          final slideProgress =
              _slideOffset.abs() / (MediaQuery.of(context).size.width * 0.5);
          if (slideProgress > 0.2 && slideProgress < 0.21) {
            HapticFeedback.selectionClick();
          } else if (slideProgress > 0.3 &&
              slideProgress < 0.31 &&
              widget.canComplete) {
            HapticFeedback.selectionClick();
          }
        }
      },
      onPanEnd: (details) {
        if (!_isSliding) return;
        _isSliding = false;

        final screenWidth = MediaQuery.of(context).size.width;
        final slideThreshold = screenWidth * 0.15;
        final deleteThreshold = screenWidth * 0.3;

        if (_slideOffset.abs() > deleteThreshold) {
          widget.onAction('delete');
        } else if (_slideOffset.abs() > slideThreshold && widget.canComplete) {
          widget.onAction('complete');
        } else if (_slideOffset.abs() > slideThreshold) {
          widget.onAction('delete');
        }

        _slideAnimation = Tween<double>(
          begin: _slideOffset,
          end: 0.0,
        ).animate(CurvedAnimation(
          parent: _slideController,
          curve: Curves.easeOut,
        ));

        _slideController.forward(from: 0.0).then((_) {
          setState(() {
            _slideOffset = 0.0;
          });
        });

        _slideAnimation.addListener(() {
          setState(() {
            _slideOffset = _slideAnimation.value;
          });
        });
      },
      child: Stack(
        children: [
          if (_slideOffset < 0) _buildBackground(),
          Transform.translate(
            offset: Offset(_slideOffset, 0),
            child: widget.child,
          ),
        ],
      ),
    );
  }
}
