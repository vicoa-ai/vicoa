import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import '/custom_code/widgets/index.dart' as custom_widgets;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'message_selection_sheet_model.dart';
export 'message_selection_sheet_model.dart';

class MessageSelectionSheetWidget extends StatefulWidget {
  const MessageSelectionSheetWidget({
    super.key,
    required this.messages,
    required this.onShareSelected,
  });

  final List<dynamic> messages;
  final Function(List<dynamic>) onShareSelected;

  @override
  State<MessageSelectionSheetWidget> createState() =>
      _MessageSelectionSheetWidgetState();
}

class _MessageSelectionSheetWidgetState extends State<MessageSelectionSheetWidget>
    with RouteAware {
  late MessageSelectionSheetModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => MessageSelectionSheetModel());

    // Initialize with all messages selected by default
    _model.selectedMessages = Set<int>.from(
      List.generate(widget.messages.length, (index) => index)
    );
  }

  @override
  void dispose() {
    routeObserver.unsubscribe(this);
    _model.maybeDispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(MessageSelectionSheetWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    _model.widget = widget;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final route = DebugModalRoute.of(context);
    if (route != null) {
      routeObserver.subscribe(this, route);
    }
    debugLogGlobalProperty(context);
  }

  @override
  void didPopNext() {
    if (mounted && DebugFlutterFlowModelContext.maybeOf(context) == null) {
      setState(() => _model.isRouteVisible = true);
      debugLogWidgetClass(_model);
    }
  }

  @override
  void didPush() {
    if (mounted && DebugFlutterFlowModelContext.maybeOf(context) == null) {
      setState(() => _model.isRouteVisible = true);
      debugLogWidgetClass(_model);
    }
  }

  @override
  void didPop() {
    _model.isRouteVisible = false;
  }

  @override
  void didPushNext() {
    _model.isRouteVisible = false;
  }

  void _toggleSelectAll() {
    setState(() {
      if (_model.selectedMessages.length == widget.messages.length) {
        // Deselect all
        _model.selectedMessages.clear();
      } else {
        // Select all
        _model.selectedMessages = Set<int>.from(
          List.generate(widget.messages.length, (index) => index)
        );
      }
    });
  }

  void _toggleMessage(int index) {
    setState(() {
      if (_model.selectedMessages.contains(index)) {
        _model.selectedMessages.remove(index);
      } else {
        _model.selectedMessages.add(index);
      }
    });
  }

  Widget _buildMessage(dynamic message, int index, {required bool isSelected}) {
    final senderType = message['sender_type']?.toString() ?? '';
    final isUser = senderType.toLowerCase() == 'user' || 
                   senderType.toLowerCase() == 'human';
    final content = message['content'] ?? '';
    
    return Container(
      margin: EdgeInsetsDirectional.fromSTEB(
        0.0,  // No left margin
        6.0, 
        0.0,  // No right margin
        6.0
      ),
      child: InkWell(
        splashColor: Colors.transparent,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        onTap: () async {
          HapticFeedback.lightImpact();
          _toggleMessage(index);
        },
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Selection indicator - always on the left
            Padding(
              padding: EdgeInsetsDirectional.fromSTEB(0.0, 14.0, 12.0, 0.0),
              child: Icon(
                isSelected ? Icons.check_circle : Icons.radio_button_unchecked,
                color: isSelected
                    ? FlutterFlowTheme.of(context).primary
                    : FlutterFlowTheme.of(context).secondaryText,
                size: 20.0,
              ),
            ),
            
            Expanded(
              child: Container(
                margin: EdgeInsetsDirectional.fromSTEB(
                  0.0,  // No left margin
                  0.0,
                  0.0,  // No right margin
                  0.0
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.start,  // Always align to start (left)
                  children: [
                    Flexible(
                      child: Container(
                        constraints: BoxConstraints(
                          maxWidth: double.infinity,  // Full width for all messages
                        ),
                        padding: EdgeInsetsDirectional.fromSTEB(
                          16.0, 
                          14.0, 
                          16.0, 
                          14.0
                        ),
                        decoration: BoxDecoration(
                          color: isUser 
                              ? FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.15)
                              : FlutterFlowTheme.of(context).secondaryBackground,
                          borderRadius: const BorderRadius.all(
                            Radius.circular(20.0),
                          ),
                          border: isUser ? null : Border.all(
                            color: FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.2),
                            width: 1.0,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Add user indicator for user messages
                            if (isUser) ...[
                              Padding(
                                padding: EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 4.0),
                                child: Text(
                                  AppLocalizations.of(context).messageSelectionSheetYou,
                                  style: FlutterFlowTheme.of(context).bodySmall.override(
                                        color: FlutterFlowTheme.of(context).secondaryText,
                                        fontSize: 11.0,
                                        letterSpacing: 0.0,
                                        fontWeight: FontWeight.w500,
                                      ),
                                ),
                              ),
                            ],
                            _buildMessageContent(content, isUser, index),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMessageContent(String content, bool isUser, int index) {
    final isExpanded = _model.expandedMessages.contains(index);
    final shouldShowExpandButton = _shouldShowExpandButton(content, isExpanded);
    const double maxHeight = 150.0; // Maximum height for collapsed messages
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Message content with height constraint
        Container(
          constraints: BoxConstraints(
            maxHeight: isExpanded ? double.infinity : maxHeight,
          ),
          child: SingleChildScrollView(
            physics: NeverScrollableScrollPhysics(), // Disable scroll, use expand instead
            child: custom_widgets.buildMarkdownText(
              context,
              content,
              isUser,
              onSendMessage: (text) async {
                // No action needed for selection sheet
              },
            ),
          ),
        ),
        
        // Show expand/collapse button only when content actually overflows
        if (shouldShowExpandButton) ...[
          SizedBox(height: 4.0),
          Center(
            child: InkWell(
              onTap: () {
                setState(() {
                  if (isExpanded) {
                    _model.expandedMessages.remove(index);
                  } else {
                    _model.expandedMessages.add(index);
                  }
                });
              },
              child: Padding(
                padding: EdgeInsetsDirectional.fromSTEB(6.0, 0.0, 6.0, 0.0),
                child: Icon(
                  isExpanded ? Icons.keyboard_double_arrow_up_rounded : Icons.keyboard_double_arrow_down_rounded,
                  color: FlutterFlowTheme.of(context).secondaryText,
                  size: 16.0,
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }

  bool _shouldShowExpandButton(String content, bool isExpanded) {
    // Always show button if currently expanded
    if (isExpanded) return true;
    
    // Much more conservative criteria - only show for content that definitely overflows
    final lines = content.split('\n');
    
    // Count actual line breaks and estimate rendered height
    // Each line is roughly 20-24px, so 150px = ~6-7 lines max
    final actualLineCount = lines.length;
    
    // Also count lines that would wrap (assuming ~60-70 chars per line in message bubble)
    int estimatedWrappedLines = 0;
    for (final line in lines) {
      estimatedWrappedLines += (line.length / 65).ceil();
    }
    
    // Only show expand button if we're confident content exceeds ~7 rendered lines
    final hasDefiniteOverflow = actualLineCount > 8 || estimatedWrappedLines > 8;
    
    // Markdown patterns that definitely add height
    final hasLargeCodeBlocks = content.contains('```') && content.split('```').length > 2;
    final hasMultipleLists = content.split(RegExp(r'[\n\r][-*]')).length > 5;
    
    // Very long single paragraphs
    final hasVeryLongContent = content.length > 600;
    
    return hasDefiniteOverflow || hasLargeCodeBlocks || hasMultipleLists || hasVeryLongContent;
  }

  @override
  Widget build(BuildContext context) {
    DebugFlutterFlowModelContext.maybeOf(context)
        ?.parentModelCallback
        ?.call(_model);

    return Container(
      width: double.infinity,
      height: MediaQuery.of(context).size.height * 0.9,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).secondaryBackground,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(0.0),
          bottomRight: Radius.circular(0.0),
          topLeft: Radius.circular(24.0),
          topRight: Radius.circular(24.0),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.max,
        children: [
          // Handle bar
          Row(
            mainAxisSize: MainAxisSize.max,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Padding(
                padding: EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
                child: Container(
                  width: 50.0,
                  height: 4.0,
                  decoration: BoxDecoration(
                    color: FlutterFlowTheme.of(context).alternate,
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
              ),
            ],
          ),
          
          // Header - Close, Title, Done
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
            child: Row(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // Close button
                FlutterFlowIconButton(
                  borderColor: FlutterFlowTheme.of(context).alternate,
                  borderRadius: 10.0,
                  borderWidth: 1.0,
                  buttonSize: 40.0,
                  icon: Icon(
                    Icons.close_rounded,
                    color: FlutterFlowTheme.of(context).secondaryText,
                    size: 20.0,
                  ),
                  onPressed: () async {
                    logFirebaseEvent('MESSAGE_SELECTION_close_rounded_ICN_O');
                    HapticFeedback.lightImpact();
                    Navigator.pop(context);
                  },
                ),
                
                // Title only
                Text(
                  AppLocalizations.of(context).messageSelectionSheetTitle,
                  style: FlutterFlowTheme.of(context).bodyMedium.override(
                        font: GoogleFonts.sourceSans3(
                          fontWeight: FontWeight.w600,
                        ),
                        fontSize: 19.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w600,
                      ),
                ),
                
                // Done button
                FlutterFlowIconButton(
                  borderColor: _model.selectedMessages.isEmpty 
                      ? FlutterFlowTheme.of(context).alternate
                      : FlutterFlowTheme.of(context).primary,
                  borderRadius: 10.0,
                  borderWidth: 1.0,
                  buttonSize: 40.0,
                  fillColor: _model.selectedMessages.isEmpty 
                      ? null
                      : FlutterFlowTheme.of(context).primary,
                  icon: Icon(
                    Icons.check_rounded,
                    color: _model.selectedMessages.isEmpty 
                        ? FlutterFlowTheme.of(context).secondaryText
                        : FlutterFlowTheme.of(context).info,
                    size: 20.0,
                  ),
                  onPressed: _model.selectedMessages.isEmpty ? null : () async {
                    logFirebaseEvent('MESSAGE_SELECTION_check_rounded_ICN_O');
                    HapticFeedback.lightImpact();
                    final selectedMessagesList = _model.selectedMessages
                        .map((index) => widget.messages[index])
                        .toList();
                    Navigator.pop(context);
                    widget.onShareSelected(selectedMessagesList);
                  },
                ),
              ],
            ),
          ),

          // Select All row
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 0.0),
            child: Row(
              mainAxisSize: MainAxisSize.max,
              children: [
                // Clickable Select All part
                Expanded(
                  child: InkWell(
                    splashColor: Colors.transparent,
                    focusColor: Colors.transparent,
                    hoverColor: Colors.transparent,
                    highlightColor: Colors.transparent,
                    onTap: () async {
                      HapticFeedback.lightImpact();
                      _toggleSelectAll();
                    },
                    child: Container(
                      height: 44.0,
                      padding: EdgeInsetsDirectional.fromSTEB(0.0, 10.0, 0.0, 10.0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.start,
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          // Tick on the left
                          Icon(
                            _model.selectedMessages.length == widget.messages.length
                                ? Icons.check_circle
                                : Icons.radio_button_unchecked,
                            color: _model.selectedMessages.length == widget.messages.length
                                ? FlutterFlowTheme.of(context).primary
                                : FlutterFlowTheme.of(context).secondaryText,
                            size: 20.0,
                          ),
                          SizedBox(width: 12.0),
                          // Select All text
                          Text(
                            _model.selectedMessages.length == widget.messages.length
                                ? AppLocalizations.of(context).messageSelectionSheetDeselectAll
                                : AppLocalizations.of(context).messageSelectionSheetSelectAll,
                            style: FlutterFlowTheme.of(context).bodyMedium.override(
                                  font: GoogleFonts.sourceSans3(
                                    fontWeight: FontWeight.w500,
                                  ),
                                  color: FlutterFlowTheme.of(context).primaryText,
                                  fontSize: 16.0,
                                  letterSpacing: 0.0,
                                ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                // Selection count on the right (non-clickable)
                Text(
                  AppLocalizations.of(context).messageSelectionSheetCount(
                      _model.selectedMessages.length, widget.messages.length),
                  style: FlutterFlowTheme.of(context).bodySmall.override(
                        color: FlutterFlowTheme.of(context).secondaryText,
                        fontSize: 14.0,
                        letterSpacing: 0.0,
                        fontWeight: FontWeight.w500,
                      ),
                ),
              ],
            ),
          ),

          // Messages list - Chat format
          Expanded(
            child: Padding(
              padding: EdgeInsetsDirectional.fromSTEB(16.0, 16.0, 16.0, 16.0),
              child: ListView.builder(
                itemCount: widget.messages.length,
                itemBuilder: (context, index) {
                  final message = widget.messages[index];
                  final isSelected = _model.selectedMessages.contains(index);

                  return _buildMessage(message, index, isSelected: isSelected);
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}