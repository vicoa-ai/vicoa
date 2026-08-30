// Automatic FlutterFlow imports
import '/flutter_flow/flutter_flow_theme.dart';
import '/l10n/app_localizations.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import '/index.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/utils/ansi_text.dart';
import '/custom_code/utils/markdown_diff_utils.dart';
import '/custom_code/widgets/syntax_highlighted_code_block.dart';
import '/custom_code/widgets/tool_icon.dart';


Widget buildMarkdownText(
  BuildContext context,
  String content,
  bool isUser, {
  bool requiresUserInput = false,
  required Function(String content) onSendMessage,
  String Function(String content)? filterProjectRoot,
  String? agentTypeName,
  bool toolUseIsFirst = true,
  bool toolUseIsLast = true,
}) {
  // debugPrint('buildMarkdownText: $content');
  final textStyle = FlutterFlowTheme.of(context).bodyMedium.override(
    color: FlutterFlowTheme.of(context).primaryText,
    fontSize: 18.0,
  );

  final codeStyle = GoogleFonts.jetBrainsMono().copyWith(
    color: FlutterFlowTheme.of(context).primaryText,
    fontSize: 16.0,
  );
  final shouldMergeDiff = agentTypeName?.toLowerCase() != 'codex';

  // Apply project root filtering to content
  var filteredContent = filterProjectRoot?.call(content) ?? content;
  
  // Handle codex status filtering - remove status line and everything after it
  if (!isUser && agentTypeName?.toLowerCase() == 'codex') {
    final lines = filteredContent.split('\n');
    final statusIndex = lines.indexWhere((line) => RegExp(r'\*\*Status:\*\*').hasMatch(line.trim()));
    if (statusIndex != -1) {
      // Keep only lines before the status line
      filteredContent = lines.sublist(0, statusIndex).join('\n');
    }
  }

  // Handle ANSI/local-command output specially
  if (_shouldRenderAsAnsiContent(filteredContent)) {
    return buildAnsiRichText(context, filteredContent, textStyle);
  }

  filteredContent = _preprocessMarkdownContent(filteredContent);

  // Check for options in agent messages - only when explicitly flagged
  if (!isUser && requiresUserInput && _hasValidOptionsBlock(filteredContent)) {
    return _buildMessageWithOptions(context, filteredContent, onSendMessage, agentTypeName);
  }

  // Check for "Using tool" messages and format them specially
  if (filteredContent.trim().startsWith('Using tool:') || filteredContent.trim().startsWith('🔧 Using tool:') ||
      filteredContent.trim().startsWith('**Exec:**') ||
      (filteredContent.contains('✏️ Applying patch to') && filteredContent.contains('file (+'))) {
    return _buildUsingToolMessage(context, filteredContent, agentTypeName: agentTypeName, toolUseIsFirst: toolUseIsFirst, toolUseIsLast: toolUseIsLast);
  }

  final children = <Widget>[];
  final lines = filteredContent.split('\n');
  int codeBlockDepth = 0;
  String? activeFenceChar;
  int activeFenceLength = 0;
  int nestedFenceDepth = 0;
  // When the outer fence is markdown-flavored (```markdown), pin the close to
  // the last matching fence in the document. -1 = not a markdown outer fence.
  int markdownOuterCloseIndex = -1;
  List<String> codeBlockLines = []; // Store raw text lines
  String? codeBlockLanguage;

  // Track table parsing
  bool inTable = false;
  List<String> tableLines = [];

  // Track blockquotes
  bool inBlockquote = false;
  List<String> blockquoteLines = [];

  // Collect text spans for continuous text sections (between code blocks)
  List<InlineSpan> textSpans = [];

  // Track list items for todo formatting
  bool inList = false;
  List<Widget> listItems = [];

  void flushTextSpans() {
    if (textSpans.isNotEmpty) {
      children.add(
        Text.rich(
          TextSpan(children: textSpans),
        ),
      );
      textSpans = [];
    }
  }

  void flushListItems() {
    if (listItems.isNotEmpty) {
      children.add(
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: listItems,
        ),
      );
      listItems = [];
      inList = false;
    }
  }

  void flushTable() {
    if (tableLines.isNotEmpty) {
      children.add(_buildMarkdownTable(context, tableLines));
      tableLines = [];
      inTable = false;
    }
  }

  void flushBlockquote() {
    if (blockquoteLines.isNotEmpty) {
      children.add(
        _buildBlockquote(
          context,
          blockquoteLines,
          textStyle,
          onSendMessage,
          agentTypeName,
        ),
      );
      blockquoteLines = [];
      inBlockquote = false;
    }
  }

  for (int i = 0; i < lines.length; i++) {
    var line = lines[i];
    final trimmedLine = line.trim();
    final fenceMatch = _matchMarkdownFence(line);

    // Check if this is a todo list item (● ◐ ○) or a markdown bullet (*, -)
    final todoMatch = RegExp(r'^([●◐○])\s+(.+)$').firstMatch(line.trim());
    final bulletMatch = RegExp(r'^(?:\*|-)\s+(.+)$').firstMatch(line.trim());
    final orderedMatch = RegExp(r'^(\d+)\.\s+(.+)$').firstMatch(line.trim());
    final isTodoLine = codeBlockDepth == 0 && todoMatch != null;
    final isBulletLine = codeBlockDepth == 0 && bulletMatch != null;
    final isOrderedLine = codeBlockDepth == 0 && orderedMatch != null;
    final isBlockquoteLine = codeBlockDepth == 0 && trimmedLine.startsWith('>');
    final isHorizontalRuleLine = codeBlockDepth == 0 && _isHorizontalRule(trimmedLine);

    // Check if this is a table line (contains |)
    // A new table can only start if the line begins with | — this prevents prose
    // sentences that merely mention | from being mistaken for table rows.
    // Once inTable is true, continuation lines (e.g. separator rows) are accepted.
    final isTableLine = line.trim().isNotEmpty &&
                        _looksLikeMarkdownTableLine(line) &&
                        codeBlockDepth == 0 &&
                        !isTodoLine &&
                        !isBulletLine &&
                        !isOrderedLine &&
                        (inTable || line.trim().startsWith('|'));

    if (isHorizontalRuleLine) {
      flushTextSpans();
      flushTable();
      flushListItems();
      flushBlockquote();
      children.add(_buildHorizontalRule(context));
      continue;
    }

    if (isBlockquoteLine) {
      if (!inBlockquote) {
        flushTextSpans();
        flushTable();
        flushListItems();
        inBlockquote = true;
      }
      blockquoteLines.add(trimmedLine.substring(1).trimLeft());
      continue;
    } else if (inBlockquote) {
      flushBlockquote();
    }

    // Handle todo list items and markdown bullets
    if (isTodoLine || isBulletLine || isOrderedLine) {
      if (!inList) {
        // Starting a new list - flush any pending text, table, and blockquote
        flushTextSpans();
        flushTable();
        flushBlockquote();
        inList = true;
      }
      if (isTodoLine) {
        final symbol = todoMatch.group(1)!;
        final text = todoMatch.group(2)!;
        listItems.add(_buildTodoItem(context, symbol, text, textStyle, codeStyle));
      } else if (isOrderedLine) {
        final number = orderedMatch.group(1)!;
        final text = orderedMatch.group(2)!;
        listItems.add(_buildOrderedListItem(context, number, text, textStyle, codeStyle));
      } else {
        final text = bulletMatch!.group(1)!;
        listItems.add(_buildBulletItem(context, text, textStyle, codeStyle));
      }
      continue;
    } else if (inList) {
      // End of list - flush it
      flushListItems();
    }

    // Handle table state transitions
    if (isTableLine) {
      if (!inTable) {
        // Starting a new table - flush any pending text, list, and blockquote
        flushTextSpans();
        flushListItems();
        flushBlockquote();
        inTable = true;
      }
      tableLines.add(line);
      continue;
    } else if (inTable) {
      // End of table - flush it
      flushTable();
    }

    // Handle code block start/end with proper nesting
    if (fenceMatch != null) {
      final fence = fenceMatch.group(1)!;
      final fenceChar = fence[0];
      final fenceLength = fence.length;
      final fenceInfo = (fenceMatch.group(2) ?? '').trim();

      if (codeBlockDepth > 0) {
        if (fenceChar == activeFenceChar && fenceLength >= activeFenceLength) {
          // Markdown-flavored outer fence: every interior fence-shaped line is
          // content until we reach the prescanned closing index. This stops
          // ambiguous info-less ``` openings inside markdown source from being
          // misread as the outer close.
          if (markdownOuterCloseIndex != -1) {
            if (i == markdownOuterCloseIndex) {
              codeBlockDepth = 0;
              activeFenceChar = null;
              activeFenceLength = 0;
              markdownOuterCloseIndex = -1;
              flushTextSpans();
              if (codeBlockLines.isNotEmpty) {
                children.add(_buildCodeBlock(context, codeBlockLines, isUser, codeBlockLanguage, shouldMergeDiff));
                codeBlockLines = [];
              }
              codeBlockLanguage = null;
              continue;
            }
            codeBlockLines.add(line);
            continue;
          }

          if (fenceInfo.isNotEmpty) {
            nestedFenceDepth++;
            codeBlockLines.add(line);
            continue;
          }

          if (nestedFenceDepth > 0) {
            nestedFenceDepth--;
            codeBlockLines.add(line);
            continue;
          }

          codeBlockDepth = 0;
          activeFenceChar = null;
          activeFenceLength = 0;
          flushTextSpans();
          if (codeBlockLines.isNotEmpty) {
            children.add(_buildCodeBlock(context, codeBlockLines, isUser, codeBlockLanguage, shouldMergeDiff));
            codeBlockLines = [];
          }
          codeBlockLanguage = null;
          continue;
        } else {
          codeBlockLines.add(line);
          continue;
        }
      } else {
        // Start of outermost code block - flush pending block elements first
        flushTextSpans();
        flushTable();
        flushListItems();
        flushBlockquote();
        codeBlockDepth = 1;
        activeFenceChar = fenceChar;
        activeFenceLength = fenceLength;
        nestedFenceDepth = 0;
        codeBlockLanguage = _parseCodeBlockLanguage(line);
        markdownOuterCloseIndex = _isMarkdownLanguage(codeBlockLanguage)
            ? _findLastMatchingFence(lines, i, fenceChar, fenceLength)
            : -1;
        continue;
      }
    }

    if (codeBlockDepth > 0) {
      codeBlockLines.add(line);
      continue;
    }

    // Add spacing before content
    if (textSpans.isNotEmpty && i > 0) {
      textSpans.add(const TextSpan(text: '\n'));
    }

    // Handle markdown headers (only for agent messages, not user messages)
    if (!isUser && line.trim().startsWith('###')) {
      final headerText = line.trim().substring(3).trim().replaceAllMapped(
        RegExp(r'\*\*(.*?)\*\*'),
        (match) => match.group(1) ?? '',
      );
      // Add spacing before header
      if (textSpans.isNotEmpty) {
        textSpans.add(const TextSpan(text: '\n'));
      }
      textSpans.add(
        TextSpan(
          text: '$headerText\n',
          style: textStyle.copyWith(
            fontSize: 17.0,
            fontWeight: FontWeight.w600,
            color: FlutterFlowTheme.of(context).primaryText,
          ),
        ),
      );
    } else if (!isUser && line.trim().startsWith('##')) {
      final headerText = line.trim().substring(2).trim().replaceAllMapped(
        RegExp(r'\*\*(.*?)\*\*'),
        (match) => match.group(1) ?? '',
      );
      // Add spacing before header
      if (textSpans.isNotEmpty) {
        textSpans.add(const TextSpan(text: '\n'));
      }
      textSpans.add(
        TextSpan(
          text: '$headerText\n',
          style: textStyle.copyWith(
            fontSize: 18.0,
            fontWeight: FontWeight.w700,
            color: FlutterFlowTheme.of(context).primaryText,
          ),
        ),
      );
    } else if (!isUser && line.trim().startsWith('#')) {
      final headerText = line.trim().substring(1).trim().replaceAllMapped(
        RegExp(r'\*\*(.*?)\*\*'),
        (match) => match.group(1) ?? '',
      );
      // Add spacing before header
      if (textSpans.isNotEmpty) {
        textSpans.add(const TextSpan(text: '\n'));
      }
      textSpans.add(
        TextSpan(
          text: '$headerText\n',
          style: textStyle.copyWith(
            fontSize: 19.0,
            fontWeight: FontWeight.w800,
            color: FlutterFlowTheme.of(context).primaryText,
          ),
        ),
      );
    } else {
      // Parse inline formatting for regular text lines
      final inlineCodeStyle = codeStyle.copyWith(
        color: FlutterFlowTheme.of(context).inlineCodeColor,
        fontSize: 16.0,
      );
      final linkStyle = textStyle.copyWith(
        color: FlutterFlowTheme.of(context).primary,
        decoration: TextDecoration.underline,
      );
      _parseLineFormatting(context, line, textStyle, inlineCodeStyle, linkStyle, textSpans);
    }
  }

  // Flush any remaining text spans
  flushTextSpans();

  // Flush any remaining table
  flushTable();

  // Flush any remaining list
  flushListItems();

  // Flush any remaining blockquote
  flushBlockquote();

  // Handle case where content ends with a code block
  if (codeBlockDepth > 0 && codeBlockLines.isNotEmpty) {
    children.add(_buildCodeBlock(context, codeBlockLines, isUser, codeBlockLanguage, shouldMergeDiff));
  }

  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: children,
  );
}


bool _hasValidOptionsBlock(String content) {
  // Must contain exact markers
  if (!content.contains('[OPTIONS]') || !content.contains('[/OPTIONS]')) {
    return false;
  }
  
  final optionsStart = content.lastIndexOf('[OPTIONS]');
  final optionsEnd = content.lastIndexOf('[/OPTIONS]');
  
  // Options block must be at the end of the message
  if (optionsStart == -1 || optionsEnd == -1 || optionsEnd <= optionsStart) {
    return false;
  }
  
  // Nothing substantial should come after [/OPTIONS]
  final afterOptions = content.substring(optionsEnd + '[/OPTIONS]'.length).trim();
  if (afterOptions.isNotEmpty) {
    return false;
  }
  
  // Extract options content
  final optionsContent = content.substring(
    optionsStart + '[OPTIONS]'.length,
    optionsEnd
  ).trim();
  
  // Must have at least one numbered option
  final lines = optionsContent.split('\n');
  final validOptions = lines.where((line) => 
    line.trim().isNotEmpty && 
    RegExp(r'^\d+\.\s+.+').hasMatch(line.trim())
  ).length;
  
  return validOptions > 0;
}

Widget _buildMessageWithOptions(BuildContext context, String content, Function(String content) onSendMessage, [String? agentTypeName]) {
  
  // Use last occurrence for safer parsing
  final optionsStartIndex = content.lastIndexOf('[OPTIONS]');
  final optionsEndIndex = content.lastIndexOf('[/OPTIONS]');
  
  final messageText = content.substring(0, optionsStartIndex).trim();
  final optionsText = content.substring(
    optionsStartIndex + '[OPTIONS]'.length, 
    optionsEndIndex
  ).trim();
  
  // Parse only properly formatted options
  final optionLines = optionsText.split('\n')
      .where((line) => line.trim().isNotEmpty && 
                      RegExp(r'^\d+\.\s+.+').hasMatch(line.trim()))
      .toList();
  
  final children = <Widget>[];
  
  // Add main message text if present (render as markdown)
  if (messageText.isNotEmpty) {
    children.add(buildMarkdownText(context, messageText, false, onSendMessage: onSendMessage, agentTypeName: agentTypeName));
    children.add(const SizedBox(height: 12.0));
  }
  
  // Add option buttons
  for (int i = 0; i < optionLines.length; i++) {
    final option = optionLines[i].trim();
    if (option.isNotEmpty) {
      // Extract option text (remove number prefix like "1. ")
      final optionText = option.replaceFirst(RegExp(r'^\d+\.\s*'), '');
      
      children.add(
        Container(
          width: double.infinity,
          margin: EdgeInsets.only(bottom: i < optionLines.length - 1 ? 8.0 : 0.0),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(12.0),
              onTap: () async {
                HapticFeedback.lightImpact();
                onSendMessage(optionText);
              },
              child: Container(
                padding: const EdgeInsetsDirectional.fromSTEB(16.0, 12.0, 16.0, 12.0),
                decoration: BoxDecoration(
                  color: FlutterFlowTheme.of(context).codeBlockBackground,
                  borderRadius: BorderRadius.circular(12.0),
                  border: Border.all(
                    color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                    width: 0.5,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 24.0,
                      height: 24.0,
                      decoration: BoxDecoration(
                        color: FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12.0),
                      ),
                      child: Center(
                        child: Text(
                          '${i + 1}',
                          style: FlutterFlowTheme.of(context).bodySmall.override(
                            color: FlutterFlowTheme.of(context).secondaryText,
                            fontSize: 12.0,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12.0),
                    Expanded(
                      child: Text(
                        optionText,
                        style: FlutterFlowTheme.of(context).bodyMedium.override(
                          color: FlutterFlowTheme.of(context).primaryText,
                          fontSize: 15.0,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    Icon(
                      Icons.arrow_forward_ios_rounded,
                      color: FlutterFlowTheme.of(context).secondaryText,
                      size: 16.0,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    }
  }
  
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: children,
  );
}

const List<String> _webPreviewLinkKeywords = ['trycloudflare.com', 'ngrok'];

bool _shouldOpenInWebPreview(String url) {
  final normalizedUrl = url.trim().toLowerCase();
  if (normalizedUrl.isEmpty) {
    return false;
  }
  return _webPreviewLinkKeywords.any((keyword) => normalizedUrl.contains(keyword));
}

Future<void> _openMarkdownLink(BuildContext context, String url) async {
  if (_shouldOpenInWebPreview(url)) {
    context.pushNamed(
      WebPreviewWidget.routeName,
      extra: <String, dynamic>{
        'initialUrl': url,
        kTransitionInfoKey: const TransitionInfo(
          hasTransition: true,
          transitionType: PageTransitionType.bottomToTop,
        ),
      },
    );
    return;
  }
  await launchURL(url);
}

const int _kCodeCollapseLineThresholdDefault = 8;
// Approximate line height for the code font (12px font + padding)
const double _kCodeLineHeight = 22.0;

class _CollapsibleCodeWrapper extends StatelessWidget {
  const _CollapsibleCodeWrapper({
    required this.lineCount,
    required this.child,
    required this.codeLines,
    required this.language,
    required this.shouldMergeDiff,
    this.outerBorderRadius,
    this.outerBorderColor,
  });
  final int lineCount;
  final Widget child;
  final List<String> codeLines;
  final String? language;
  final bool shouldMergeDiff;
  final BorderRadius? outerBorderRadius;
  final Color? outerBorderColor;

  void _openSheet(BuildContext context) {
    HapticFeedback.lightImpact();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _CodeBottomSheet(
        codeLines: codeLines,
        language: language,
        shouldMergeDiff: shouldMergeDiff,
      ),
    );
  }

  Widget _wrapBareWithChrome(BuildContext context) {
    // When the wrapper owns the chrome but isn't collapsing, the bare child
    // would otherwise shrink to its content. Re-apply the outer container so
    // the background extends to the full available width.
    if (outerBorderRadius == null || outerBorderColor == null) return child;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 0.0, bottom: 8.0),
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).codeBlockBackground,
        border: Border.all(color: outerBorderColor!, width: 0.5),
        borderRadius: outerBorderRadius!,
      ),
      child: child,
    );
  }

  @override
  Widget build(BuildContext context) {
    final setting = FFAppState().setting;
    if (!setting.collapseLongCode) return _wrapBareWithChrome(context);
    final threshold = setting.codeCollapseLineThreshold > 0
        ? setting.codeCollapseLineThreshold
        : _kCodeCollapseLineThresholdDefault;
    if (lineCount <= threshold) return _wrapBareWithChrome(context);

    final collapsedMaxHeight = threshold * _kCodeLineHeight + 24.0;
    final bgColor = FlutterFlowTheme.of(context).codeBlockBackground;
    final radius = outerBorderRadius;
    final borderColor = outerBorderColor;

    final collapsed = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Stack(
          children: [
            ClipRect(
              child: SizedBox(
                height: collapsedMaxHeight,
                child: OverflowBox(
                  alignment: Alignment.topLeft,
                  maxHeight: double.infinity,
                  child: child,
                ),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              height: 40.0,
              child: IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        bgColor.withValues(alpha: 0.0),
                        bgColor.withValues(alpha: 1.0),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
        GestureDetector(
          onTap: () => _openSheet(context),
          behavior: HitTestBehavior.opaque,
          child: Container(
            color: bgColor,
            padding: const EdgeInsets.symmetric(vertical: 6.0),
            child: Center(
              child: Text(
                AppLocalizations.of(context).markdownXMoreLines(lineCount - threshold),
                style: GoogleFonts.jetBrainsMono().copyWith(
                  color: FlutterFlowTheme.of(context).secondaryText,
                  fontSize: 11.0,
                ),
              ),
            ),
          ),
        ),
      ],
    );

    if (radius == null || borderColor == null) return collapsed;

    // Wrap the collapsed block in a ClipRRect + foreground border so the
    // border and rounded corners are painted over the content.
    return ClipRRect(
      borderRadius: radius,
      child: DecoratedBox(
        position: DecorationPosition.foreground,
        decoration: BoxDecoration(
          borderRadius: radius,
          border: Border.all(color: borderColor, width: 0.5),
        ),
        child: collapsed,
      ),
    );
  }
}

class _CodeBottomSheet extends StatelessWidget {
  const _CodeBottomSheet({
    required this.codeLines,
    this.language,
    required this.shouldMergeDiff,
  });
  final List<String> codeLines;
  final String? language;
  final bool shouldMergeDiff;

  ({int additions, int deletions}) _diffStats() {
    int additions = 0;
    int deletions = 0;
    for (final line in codeLines) {
      if (line.startsWith('+') && !line.startsWith('+++')) additions++;
      if (line.startsWith('-') && !line.startsWith('---')) deletions++;
    }
    return (additions: additions, deletions: deletions);
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.sizeOf(context).height;
    final bgColor = FlutterFlowTheme.of(context).secondaryBackground;
    final isDiff = language?.toLowerCase() == 'diff';
    final langLabel = (language != null && language!.isNotEmpty) ? language! : 'code';

    Widget title;
    if (isDiff) {
      final stats = _diffStats();
      title = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (stats.additions > 0) ...[
            Text(
              '+${stats.additions}',
              style: GoogleFonts.jetBrainsMono().copyWith(
                color: FlutterFlowTheme.of(context).success,
                fontSize: 14.0,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(width: 6.0),
          ],
          if (stats.deletions > 0)
            Text(
              '-${stats.deletions}',
              style: GoogleFonts.jetBrainsMono().copyWith(
                color: FlutterFlowTheme.of(context).error,
                fontSize: 14.0,
                fontWeight: FontWeight.w600,
              ),
            ),
        ],
      );
    } else {
      title = Text(
        langLabel,
        style: GoogleFonts.jetBrainsMono().copyWith(
          color: FlutterFlowTheme.of(context).secondaryText,
          fontSize: 15.0,
          fontWeight: FontWeight.w600,
        ),
      );
    }

    return ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(20.0)),
      child: SizedBox(
        height: screenHeight * 0.88,
        child: ColoredBox(
          color: bgColor,
          child: Column(
            children: [
              // Drag handle
              Padding(
                padding: const EdgeInsets.only(top: 12.0, bottom: 8.0),
                child: Center(
                  child: Container(
                    width: 36.0,
                    height: 4.0,
                    decoration: BoxDecoration(
                      color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(2.0),
                    ),
                  ),
                ),
              ),
              // Header row
              Padding(
                padding: const EdgeInsets.fromLTRB(16.0, 0.0, 16.0, 8.0),
                child: Row(
                  children: [
                    Expanded(child: title),
                    GestureDetector(
                      onTap: () {
                        HapticFeedback.lightImpact();
                        Navigator.of(context).pop();
                      },
                      child: Container(
                        width: 36.0,
                        height: 36.0,
                        decoration: BoxDecoration(
                          border: Border.all(
                            color: FlutterFlowTheme.of(context).alternate,
                            width: 1.0,
                          ),
                          borderRadius: BorderRadius.circular(10.0),
                        ),
                        child: Icon(
                          Icons.close_rounded,
                          color: FlutterFlowTheme.of(context).secondaryText,
                          size: 18.0,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              // Divider(height: 1.0, color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.15)),
              // Full code block
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(vertical: 8.0),
                  child: _buildCodeBlock(
                    context,
                    codeLines,
                    false,
                    language,
                    shouldMergeDiff,
                    collapsible: false,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Widget _buildCodeBlock(
  BuildContext context,
  List<String> codeLines,
  bool isUser,
  String? language,
  bool shouldMergeDiff, {
  bool bare = false,
  bool collapsible = true,
}) {
  // Normalize indentation: remove common leading whitespace
  final normalizedLines = _normalizeCodeIndentation(codeLines);

  final codeStyle = GoogleFonts.jetBrainsMono().copyWith(
    color: FlutterFlowTheme.of(context).primaryText,
    fontSize: 13.0,
  );

  final isDiffBlock = language?.toLowerCase() == 'diff';
  final codeBorderColor = FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3);
  const codeBorderRadius = BorderRadius.all(Radius.circular(8.0));

  if (!isDiffBlock) {
    if (!collapsible) {
      return SyntaxHighlightedCodeBlock(
        code: normalizedLines.join('\n'),
        language: resolveCodeLanguage(language),
        textStyle: codeStyle,
        backgroundColor: FlutterFlowTheme.of(context).codeBlockBackground,
        borderColor: codeBorderColor,
        bare: bare,
      );
    }
    // When collapsible, the wrapper owns the outer border/radius; pass bare:true to avoid double border.
    final block = SyntaxHighlightedCodeBlock(
      code: normalizedLines.join('\n'),
      language: resolveCodeLanguage(language),
      textStyle: codeStyle,
      backgroundColor: FlutterFlowTheme.of(context).codeBlockBackground,
      borderColor: codeBorderColor,
      bare: true,
    );
    return _CollapsibleCodeWrapper(
      lineCount: normalizedLines.length,
      codeLines: normalizedLines,
      language: language,
      shouldMergeDiff: shouldMergeDiff,
      outerBorderRadius: bare ? null : codeBorderRadius,
      outerBorderColor: bare ? null : codeBorderColor,
      child: block,
    );
  }

  final codeWidgets = <Widget>[];
  final diffLines = formatDiffLines(
    normalizedLines.join('\n'),
    shouldMergeDiff,
    compactContext: true,
  );

  for (final diffLine in diffLines) {
    final content = diffLine.content.isEmpty ? ' ' : diffLine.content;
    final isEllipsis = diffLine.type == DiffLineType.ellipsis;
    final padding = EdgeInsets.symmetric(
      horizontal: 12.0,
      vertical: isEllipsis
          ? 2.0
          : diffLine.type == DiffLineType.context
              ? 2.0
              : 4.0,
    );
    final alignment = isEllipsis ? Alignment.center : Alignment.centerLeft;
    Color? background;
    TextStyle lineStyle = codeStyle;

    if (diffLine.type == DiffLineType.remove) {
      background = FlutterFlowTheme.of(context).diffDeletedBackground;
      lineStyle = codeStyle.copyWith(
        color: FlutterFlowTheme.of(context).diffDeletedText,
      );
    } else if (diffLine.type == DiffLineType.add) {
      background = FlutterFlowTheme.of(context).diffAddedBackground;
      lineStyle = codeStyle.copyWith(
        color: FlutterFlowTheme.of(context).diffAddedText,
      );
    } else if (diffLine.type == DiffLineType.ellipsis) {
      lineStyle = codeStyle.copyWith(
        color: FlutterFlowTheme.of(context).secondaryText,
      );
    }

    codeWidgets.add(
      Container(
        alignment: alignment,
        decoration: BoxDecoration(
          color: background,
        ),
        padding: padding,
        child: Text(
          content,
          style: lineStyle,
          softWrap: false,
          textAlign: isEllipsis ? TextAlign.center : TextAlign.left,
        ),
      ),
    );
  }

  final scrollContent = SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    padding: const EdgeInsets.symmetric(vertical: 12.0),
    child: SelectionArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: codeWidgets,
      ),
    ),
  );

  if (!collapsible) {
    if (bare) return scrollContent;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8.0, bottom: 8.0),
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).codeBlockBackground,
        border: Border.all(color: codeBorderColor, width: 0.5),
        borderRadius: codeBorderRadius,
      ),
      child: scrollContent,
    );
  }
  // When collapsible, the wrapper owns the outer border/radius; no border on the inner container.
  final diffInner = bare ? scrollContent : ColoredBox(
    color: FlutterFlowTheme.of(context).codeBlockBackground,
    child: scrollContent,
  );
  return _CollapsibleCodeWrapper(
    lineCount: diffLines.length,
    codeLines: normalizedLines,
    language: language,
    shouldMergeDiff: shouldMergeDiff,
    outerBorderRadius: bare ? null : codeBorderRadius,
    outerBorderColor: bare ? null : codeBorderColor,
    child: diffInner,
  );
}

String? _parseCodeBlockLanguage(String line) {
  final fenceMatch = _matchMarkdownFence(line);
  if (fenceMatch == null) {
    return null;
  }
  final language = (fenceMatch.group(2) ?? '').trim();
  if (language.isEmpty) {
    return null;
  }
  return language.split(RegExp(r'\s+')).first;
}

bool _isMarkdownLanguage(String? language) {
  if (language == null) return false;
  final lower = language.toLowerCase();
  return lower == 'markdown' || lower == 'md' || lower == 'mdown';
}

int _findLastMatchingFence(List<String> lines, int startIdx, String fenceChar, int fenceLength) {
  for (int i = lines.length - 1; i > startIdx; i--) {
    final m = _matchMarkdownFence(lines[i]);
    if (m == null) continue;
    final fence = m.group(1)!;
    if (fence[0] == fenceChar && fence.length >= fenceLength) {
      return i;
    }
  }
  return -1;
}

String _preprocessMarkdownContent(String content) {
  return content.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
}

bool _shouldRenderAsAnsiContent(String content) {
  if (!hasAnsiOrLocalCommand(content)) {
    return false;
  }

  final lines = content.replaceAll('\r\n', '\n').replaceAll('\r', '\n').split('\n');
  bool inFence = false;
  String? fenceChar;
  int fenceLength = 0;
  int nestedFenceDepth = 0;

  for (final line in lines) {
    final fenceMatch = _matchMarkdownFence(line);
    if (fenceMatch != null) {
      final fence = fenceMatch.group(1)!;
      final currentFenceChar = fence[0];
      final currentFenceLength = fence.length;
      final fenceInfo = (fenceMatch.group(2) ?? '').trim();

      if (!inFence) {
        inFence = true;
        fenceChar = currentFenceChar;
        fenceLength = currentFenceLength;
        nestedFenceDepth = 0;
        continue;
      }

      if (currentFenceChar == fenceChar && currentFenceLength >= fenceLength) {
        if (fenceInfo.isNotEmpty) {
          nestedFenceDepth++;
          continue;
        }

        if (nestedFenceDepth > 0) {
          nestedFenceDepth--;
          continue;
        }

        inFence = false;
        fenceChar = null;
        fenceLength = 0;
        continue;
      }
    }

    if (!inFence && hasAnsiOrLocalCommand(line)) {
      return true;
    }
  }

  return false;
}

RegExpMatch? _matchMarkdownFence(String line) {
  return RegExp(r'^\s*(`{3,}|~{3,})(.*)$').firstMatch(line);
}

bool _isHorizontalRule(String line) {
  return RegExp(r'^([-*_])(?:\s*\1){2,}\s*$').hasMatch(line);
}

bool _looksLikeMarkdownTableLine(String line) {
  final trimmed = line.trim();
  if (trimmed.isEmpty) {
    return false;
  }

  // Check for separator line first (e.g., |---|---| or ---|---)
  if (RegExp(r'^[\s\-:|]*$').hasMatch(trimmed) && trimmed.contains('-')) {
    return true;
  }

  final pipeCount = '|'.allMatches(trimmed).length;
  // Lines starting with | need only 1 pipe; lines without a leading | need at least 2
  // (prevents sentences that merely mention | from being detected as tables)
  final minPipes = trimmed.startsWith('|') ? 1 : 2;
  if (pipeCount < minPipes) {
    return false;
  }

  // If it has common shell command patterns, it's likely not a table
  if (RegExp(r'\$\(|\bgrep\b|\btail\b|\bhead\b|\bawk\b|\bsed\b|\bfind\b').hasMatch(trimmed)) {
    return false;
  }

  // Count columns including empty ones (strip outer pipes first to avoid phantom cells)
  var checkLine = trimmed;
  if (checkLine.startsWith('|')) checkLine = checkLine.substring(1);
  if (checkLine.endsWith('|')) checkLine = checkLine.substring(0, checkLine.length - 1);
  return checkLine.split('|').length >= 2;
}


/// Removes common leading whitespace from all code lines
/// Handles git diff lines (+ or -) by preserving the prefix and at least one space after it
/// Examples:
///   Input:  ["  line1", "    line2", "  line3"]
///   Output: ["line1", "  line2", "line3"]
///
///   Input:  ["+   added", "-   deleted", "    normal"]
///   Output: ["+ added", "- deleted", " normal"]
List<String> _normalizeCodeIndentation(List<String> lines) {
  if (lines.isEmpty) return lines;

  // Find minimum leading whitespace (excluding empty lines and diff prefixes)
  int minIndent = -1;

  for (final line in lines) {
    if (line.trim().isEmpty) continue;

    final isDiffLine = (line.startsWith('+') || line.startsWith('-')) && !isDiffHeaderLine(line);
    final startIdx = isDiffLine ? 1 : 0;

    // Count leading spaces from the appropriate start position
    int spaces = 0;
    for (int i = startIdx; i < line.length; i++) {
      if (line[i] == ' ' || line[i] == '\t') {
        spaces++;
      } else {
        break;
      }
    }

    // For diff lines, ensure we keep at least 1 space after +/-
    if (isDiffLine && spaces > 0) {
      spaces = spaces - 1; // Reserve 1 space
    }

    if (minIndent == -1 || spaces < minIndent) {
      minIndent = spaces;
    }
  }

  if (minIndent <= 0) return lines;

  // Remove common indentation
  return lines.map((line) {
    if (line.trim().isEmpty) return line;

    final isDiffLine = (line.startsWith('+') || line.startsWith('-')) && !isDiffHeaderLine(line);

    if (isDiffLine) {
      // Preserve +/- and at least 1 space, then remove common indent
      final rest = line.substring(1);
      final toRemove = minIndent + 1; // +1 for the mandatory space
      if (rest.length <= toRemove) return '${line[0]} ${rest.trim()}';
      return '${line[0]} ${rest.substring(toRemove)}';
    }

    // Normal lines: just remove common indent
    return line.length <= minIndent ? line.trim() : line.substring(minIndent);
  }).toList();
}


Widget _buildMarkdownTable(BuildContext context, List<String> tableLines) {
  if (tableLines.isEmpty) {
    return const SizedBox.shrink();
  }

  // Parse table rows
  final rows = <List<String>>[];
  bool hasHeaderSeparator = false;

  for (int i = 0; i < tableLines.length; i++) {
    final line = tableLines[i].trim();

    // Check if this is a separator line (e.g., |---|---|)
    if (RegExp(r'^[\s\-:|]*$').hasMatch(line) && line.contains('-')) {
      hasHeaderSeparator = true;
      continue;
    }

    // Parse cells from the row - handle both formats:
    // Format 1: | Cell 1 | Cell 2 | (with leading/trailing pipes)
    // Format 2: Cell 1 | Cell 2 (without leading/trailing pipes)
    var processedLine = line;
    if (processedLine.startsWith('|')) {
      processedLine = processedLine.substring(1);
    }
    if (processedLine.endsWith('|')) {
      processedLine = processedLine.substring(0, processedLine.length - 1);
    }

    final cells = processedLine
        .split('|')
        .map((cell) => cell.trim())
        .toList();

    if (cells.any((c) => c.isNotEmpty)) {
      rows.add(cells);
    }
  }

  if (rows.isEmpty) {
    return const SizedBox.shrink();
  }

  // Determine number of columns
  final columnCount = rows.map((row) => row.length).reduce((a, b) => a > b ? a : b);

  // Calculate intelligent column widths based on content
  // Table can be wider than screen - prioritize readability over fitting
  final columnWidths = <int, TableColumnWidth>{};

  for (int col = 0; col < columnCount; col++) {
    // Get max character length for this column
    int maxLength = 0;
    for (final row in rows) {
      if (col < row.length) {
        maxLength = maxLength > row[col].length ? maxLength : row[col].length;
      }
    }

    // Adaptive width strategy based on content length:
    // - Very short content (< 8 chars): Min 60px for readability
    // - Short content (8-40 chars): Use intrinsic width (e.g., names, dates)
    // - Medium content (40-100 chars): Cap at 200px and wrap
    // - Long content (> 100 chars): Cap at 250px and wrap for readability

    if (maxLength < 8) {
      // Very short (e.g., ID, #) - set minimum readable width
      columnWidths[col] = const FixedColumnWidth(60.0);
    } else if (maxLength <= 40) {
      // Short - let content determine width naturally
      columnWidths[col] = const IntrinsicColumnWidth();
    } else if (maxLength <= 100) {
      // Medium length - constrain to prevent excessive width
      columnWidths[col] = const FixedColumnWidth(200.0);
    } else {
      // Long content - cap at 250px and wrap
      columnWidths[col] = const FixedColumnWidth(250.0);
    }
  }

  // Build table with horizontal scroll
  return Container(
    width: double.infinity,
    margin: const EdgeInsets.symmetric(vertical: 8.0),
    child: LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: ConstrainedBox(
        constraints: BoxConstraints(minWidth: constraints.maxWidth),
        child: Container(
        decoration: BoxDecoration(
          border: Border.all(
            color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
            width: 0.5,
          ),
          borderRadius: BorderRadius.circular(8.0),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8.0),
          child: Table(
            border: TableBorder.symmetric(
              inside: BorderSide(
                color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                width: 0.5,
              ),
              outside: BorderSide(
                color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3),
                width: 0.5,
              ),
            ),
            columnWidths: columnWidths,
            defaultColumnWidth: const IntrinsicColumnWidth(),
            defaultVerticalAlignment: TableCellVerticalAlignment.middle,
            children: rows.asMap().entries.map((entry) {
              final rowIndex = entry.key;
              final row = entry.value;
              final isHeader = hasHeaderSeparator && rowIndex == 0;

              return TableRow(
                decoration: isHeader
                    ? BoxDecoration(
                        color: FlutterFlowTheme.of(context).codeBlockBackground,
                      )
                    : null,
                children: List.generate(
                  columnCount,
                  (colIndex) {
                    final cellText = colIndex < row.length ? row[colIndex] : '';

                    // Parse markdown formatting in cell text
                    final cellSpans = <InlineSpan>[];
                    final baseStyle = FlutterFlowTheme.of(context).bodyMedium.override(
                      color: FlutterFlowTheme.of(context).primaryText,
                      fontSize: 14.0,
                      fontWeight: isHeader ? FontWeight.w600 : FontWeight.normal,
                    );
                    final codeStyle = GoogleFonts.jetBrainsMono().copyWith(
                      color: FlutterFlowTheme.of(context).inlineCodeColor,
                      fontSize: 14.0,
                    );
                    final linkStyle = baseStyle.copyWith(
                      color: FlutterFlowTheme.of(context).primary,
                      decoration: TextDecoration.underline,
                    );
                    _parseLineFormatting(context, cellText, baseStyle, codeStyle, linkStyle, cellSpans);

                    return Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 10.0),
                      child: Text.rich(
                        TextSpan(children: cellSpans),
                        softWrap: true,
                        overflow: TextOverflow.clip,
                      ),
                    );
                  },
                ),
              );
            }).toList(),
          ),
        ),
        ),
      ),
      ),
    ),
  );
}

Widget _buildHorizontalRule(BuildContext context) {
  return Container(
    width: double.infinity,
    margin: const EdgeInsets.symmetric(vertical: 8.0),
    height: 1.0,
    color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.2),
  );
}

Widget _buildBlockquote(
  BuildContext context,
  List<String> blockquoteLines,
  TextStyle textStyle,
  Function(String content) onSendMessage,
  String? agentTypeName,
) {
  return Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 8.0),
    padding: const EdgeInsets.only(left: 12.0),
    decoration: BoxDecoration(
      border: Border(
        left: BorderSide(
          color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.35),
          width: 3.0,
        ),
      ),
    ),
    child: DefaultTextStyle.merge(
      style: textStyle.copyWith(
        color: FlutterFlowTheme.of(context).secondaryText,
        fontStyle: FontStyle.italic,
      ),
      child: buildMarkdownText(
        context,
        blockquoteLines.join('\n'),
        false,
        requiresUserInput: false,
        onSendMessage: onSendMessage,
        agentTypeName: agentTypeName,
      ),
    ),
  );
}

void _parseLineFormatting(
  BuildContext context,
  String line,
  TextStyle baseStyle,
  TextStyle codeStyle,
  TextStyle linkStyle,
  List<InlineSpan> spans,
) {
  if (line.isEmpty) {
    spans.add(TextSpan(text: '', style: baseStyle));
    return;
  }

  int index = 0;
  
  while (index < line.length) {
    // Find next formatting marker in the remaining string
    final remaining = line.substring(index);
    final boldMatch = RegExp(r'\*\*(.*?)\*\*').firstMatch(remaining);
    // Match inline code with 1+ backtick delimiters (CommonMark): both the
    // opening and closing runs must be complete backtick strings of the same
    // length (not adjacent to other backticks). This allows literal backticks
    // inside, e.g. `` ` `` renders as a single backtick. Without the
    // lookbehind/lookahead, `\1` could land in the middle of a longer run,
    // splitting `` ` `` into two separate code spans.
    final codeMatch =
        RegExp(r'(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)').firstMatch(remaining);
    final linkMatch = RegExp(r'\[([^\]]+)\]\(([^)]+)\)').firstMatch(remaining);
    final plainUrlMatch = RegExp(r'https?:\/\/[^\s<>()\[\]{}]+(?:\([^\s<>()\[\]{}]*\)[^\s<>()\[\]{}]*)*').firstMatch(remaining);
    
    // Calculate absolute positions
    final boldStart = boldMatch != null ? index + boldMatch.start : -1;
    final codeStart = codeMatch != null ? index + codeMatch.start : -1;
    final linkStart = linkMatch != null ? index + linkMatch.start : -1;
    final plainUrlStart = plainUrlMatch != null ? index + plainUrlMatch.start : -1;
    
    // Determine which comes first
    int nextMarker = -1;
    RegExpMatch? activeMatch;
    String markerType = '';
    
    if (boldStart >= 0 &&
        (codeStart < 0 || boldStart < codeStart) &&
        (linkStart < 0 || boldStart < linkStart) &&
        (plainUrlStart < 0 || boldStart < plainUrlStart)) {
      nextMarker = boldStart;
      activeMatch = boldMatch;
      markerType = 'bold';
    } else if (codeStart >= 0 &&
        (linkStart < 0 || codeStart < linkStart) &&
        (plainUrlStart < 0 || codeStart < plainUrlStart)) {
      nextMarker = codeStart;
      activeMatch = codeMatch;
      markerType = 'code';
    } else if (linkStart >= 0 && (plainUrlStart < 0 || linkStart < plainUrlStart)) {
      nextMarker = linkStart;
      activeMatch = linkMatch;
      markerType = 'link';
    } else if (plainUrlStart >= 0) {
      nextMarker = plainUrlStart;
      activeMatch = plainUrlMatch;
      markerType = 'plainUrl';
    }
    
    if (nextMarker < 0) {
      // No more formatting, add remaining text
      spans.add(TextSpan(
        text: line.substring(index),
        style: baseStyle,
      ));
      break;
    }
    
    // Add text before the marker
    if (nextMarker > index) {
      spans.add(TextSpan(
        text: line.substring(index, nextMarker),
        style: baseStyle,
      ));
    }
    
    // Add formatted text and move index past the entire match
    if (markerType == 'bold' && activeMatch != null) {
      final innerContent = activeMatch.group(1) ?? '';
      final boldBase = baseStyle.copyWith(fontWeight: FontWeight.bold);
      final boldCode = codeStyle.copyWith(fontWeight: FontWeight.bold);
      final boldLink = linkStyle.copyWith(fontWeight: FontWeight.bold);
      _parseLineFormatting(context, innerContent, boldBase, boldCode, boldLink, spans);
      index = nextMarker + activeMatch.group(0)!.length;
    } else if (markerType == 'code' && activeMatch != null) {
      var codeText = activeMatch.group(2) ?? '';
      // Per CommonMark: if content begins and ends with a space (and isn't all
      // spaces), strip exactly one space from each side. This is what allows
      // `` ` `` to render as a single backtick.
      if (codeText.length > 1 &&
          codeText.startsWith(' ') &&
          codeText.endsWith(' ') &&
          codeText.trim().isNotEmpty) {
        codeText = codeText.substring(1, codeText.length - 1);
      }
      spans.add(TextSpan(
        text: codeText,
        style: codeStyle,
      ));
      index = nextMarker + activeMatch.group(0)!.length;
    } else if (markerType == 'link' && activeMatch != null) {
      final linkText = activeMatch.group(1) ?? '';
      final linkUrl = activeMatch.group(2) ?? '';
      // Render as a real TextSpan (not a WidgetSpan) so the link stays inside the
      // enclosing SelectionArea and can be selected/copied; the recognizer keeps
      // tap-to-open working.
      spans.add(TextSpan(
        text: linkText,
        style: linkStyle,
        mouseCursor: SystemMouseCursors.click,
        recognizer: TapGestureRecognizer()
          ..onTap = () async {
            HapticFeedback.lightImpact();
            await _openMarkdownLink(context, linkUrl);
          },
      ));
      index = nextMarker + activeMatch.group(0)!.length;
    } else if (markerType == 'plainUrl' && activeMatch != null) {
      final sanitizedUrl = _stripTrailingUrlPunctuation(activeMatch.group(0) ?? '');
      if (sanitizedUrl.isEmpty) {
        spans.add(TextSpan(
          text: activeMatch.group(0) ?? '',
          style: baseStyle,
        ));
      } else {
        // Real TextSpan (not a WidgetSpan) so the URL stays selectable/copyable
        // inside the SelectionArea; the recognizer preserves tap-to-open.
        spans.add(TextSpan(
          text: sanitizedUrl,
          style: linkStyle,
          mouseCursor: SystemMouseCursors.click,
          recognizer: TapGestureRecognizer()
            ..onTap = () async {
              HapticFeedback.lightImpact();
              await _openMarkdownLink(context, sanitizedUrl);
            },
        ));
      }

      final trailingText = (activeMatch.group(0) ?? '').substring(sanitizedUrl.length);
      if (trailingText.isNotEmpty) {
        spans.add(TextSpan(
          text: trailingText,
          style: baseStyle,
        ));
      }
      index = nextMarker + (activeMatch.group(0)?.length ?? 0);
    }
  }
}

String _stripTrailingUrlPunctuation(String url) {
  var sanitized = url;
  while (sanitized.isNotEmpty && RegExp(r'[.,!?;:]+$').hasMatch(sanitized)) {
    sanitized = sanitized.substring(0, sanitized.length - 1);
  }
  while (sanitized.endsWith(')')) {
    final openCount = '('.allMatches(sanitized).length;
    final closeCount = ')'.allMatches(sanitized).length;
    if (closeCount <= openCount) {
      break;
    }
    sanitized = sanitized.substring(0, sanitized.length - 1);
  }
  return sanitized;
}

Widget _buildTodoItem(
  BuildContext context,
  String symbol,
  String text,
  TextStyle baseStyle,
  TextStyle codeStyle,
) {
  // Determine status based on symbol
  // ● = completed (checked, strikethrough)
  // ◐ = in-progress (unchecked, bold with indicator)
  // ○ = pending (unchecked, normal)
  final isCompleted = symbol == '●';
  final isInProgress = symbol == '◐';

  // Parse markdown formatting in the todo text
  final textSpans = <InlineSpan>[];
  final linkStyle = baseStyle.copyWith(
    color: FlutterFlowTheme.of(context).primary,
    decoration: TextDecoration.underline,
  );
  _parseLineFormatting(context, text, baseStyle, codeStyle, linkStyle, textSpans);

  // Apply strikethrough for completed items
  final decoratedSpans = isCompleted
      ? textSpans.map((span) {
          if (span is! TextSpan) {
            return span;
          }
          return TextSpan(
            text: span.text,
            style: (span.style ?? baseStyle).copyWith(
              decoration: TextDecoration.lineThrough,
              color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.6),
            ),
            children: span.children,
          );
        }).toList()
      : isInProgress
          ? textSpans.map((span) {
              if (span is! TextSpan) {
                return span;
              }
              return TextSpan(
                text: span.text,
                style: (span.style ?? baseStyle).copyWith(
                  fontWeight: FontWeight.bold,
                ),
                children: span.children,
              );
            }).toList()
          : textSpans;

  return Container(
    margin: const EdgeInsets.only(bottom: 2.0),
    padding: const EdgeInsets.symmetric(vertical: 2.0),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Checkbox indicator - positioned to align with first line of text
        Container(
          width: 18.0,
          height: 18.0,
          margin: const EdgeInsets.only(right: 8.0, top: 3.0),
          decoration: BoxDecoration(
            color: isCompleted
                ? FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.1)
                : Colors.transparent,
            border: Border.all(
              color: FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.4),
              width: isCompleted ? 0.6 : 1.0,
            ),
            borderRadius: BorderRadius.circular(4.0),
          ),
          child: isCompleted
              ? Icon(
                  Icons.check,
                  size: 11.0,
                  color: FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.3),
                )
              : null,
        ),
        // Text content
        Expanded(
          child: Text.rich(
            TextSpan(children: decoratedSpans),
          ),
        ),
      ],
    ),
  );
}

Widget _buildBulletItem(
  BuildContext context,
  String text,
  TextStyle baseStyle,
  TextStyle codeStyle,
) {
  final textSpans = <InlineSpan>[];
  final linkStyle = baseStyle.copyWith(
    color: FlutterFlowTheme.of(context).primary,
    decoration: TextDecoration.underline,
  );
  _parseLineFormatting(context, text, baseStyle, codeStyle, linkStyle, textSpans);

  return Container(
    margin: const EdgeInsets.only(bottom: 2.0),
    padding: EdgeInsets.zero,
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 18.0,
          alignment: Alignment.topCenter,
          margin: const EdgeInsets.only(right: 8.0, top: 1.0),
          child: Text(
            '•',
            style: baseStyle.copyWith(
              fontSize: 16.0,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Expanded(
          child: Text.rich(
            TextSpan(children: textSpans),
          ),
        ),
      ],
    ),
  );
}

Widget _buildOrderedListItem(
  BuildContext context,
  String number,
  String text,
  TextStyle baseStyle,
  TextStyle codeStyle,
) {
  final textSpans = <InlineSpan>[];
  final linkStyle = baseStyle.copyWith(
    color: FlutterFlowTheme.of(context).primary,
    decoration: TextDecoration.underline,
  );
  _parseLineFormatting(context, text, baseStyle, codeStyle, linkStyle, textSpans);

  return Container(
    margin: const EdgeInsets.only(bottom: 2.0),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 24.0,
          child: Text(
            '$number.',
            style: baseStyle.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Expanded(
          child: Text.rich(
            TextSpan(children: textSpans),
          ),
        ),
      ],
    ),
  );
}

class _ToolMessageFormat {
  const _ToolMessageFormat({
    required this.toolName,
    required this.toolDescription,
    required this.remainingContent,
    required this.isMultilineDescription,
  });

  final String toolName;
  final String toolDescription;
  final String remainingContent;
  final bool isMultilineDescription;
}

/// A right-pointing chevron that rotates to point down when [expanded].
/// The affordance for expanding a collapsed tool row / group.
Widget _toolChevron(BuildContext context, bool expanded) => AnimatedRotation(
      turns: expanded ? 0.25 : 0.0,
      duration: const Duration(milliseconds: 150),
      child: Icon(
        Icons.chevron_right,
        size: 18.0,
        color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.7),
      ),
    );

/// The bordered tool-row container (codeBlockBackground + partial rounded
/// border), shared by tool rows and the collapsed group header so their
/// borders join seamlessly when stacked.
Widget _toolBorderedBox(
  BuildContext context, {
  required Widget child,
  required bool isFirst,
  required bool isLast,
}) {
  const radius = 8.0;
  final borderColor =
      FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3);
  final borderRadius = BorderRadius.only(
    topLeft: isFirst ? const Radius.circular(radius) : Radius.zero,
    topRight: isFirst ? const Radius.circular(radius) : Radius.zero,
    bottomLeft: isLast ? const Radius.circular(radius) : Radius.zero,
    bottomRight: isLast ? const Radius.circular(radius) : Radius.zero,
  );
  return CustomPaint(
    foregroundPainter: _PartialRoundedBorderPainter(
      color: borderColor,
      borderWidth: 0.5,
      borderRadius: borderRadius,
      drawTop: isFirst,
    ),
    child: Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).codeBlockBackground,
        borderRadius: borderRadius,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8.0),
      child: child,
    ),
  );
}

/// Header row for a collapsed run of tool uses — a bordered box (styled like a
/// tool row) showing the run's aggregate [label] and a chevron. Tapping toggles
/// the whole run. Top-rounded; bottom-rounded only when [isLast] (i.e.
/// collapsed, with no rows beneath it).
Widget buildToolGroupHeader(
  BuildContext context,
  String label, {
  required bool isLast,
  required bool expanded,
  required VoidCallback onToggle,
  String? iconToolName,
  String? agentTypeName,
}) {
  return GestureDetector(
    behavior: HitTestBehavior.opaque,
    onTap: () {
      HapticFeedback.selectionClick();
      onToggle();
    },
    child: _toolBorderedBox(
      context,
      isFirst: true,
      isLast: isLast,
      child: Row(
        children: [
          if (iconToolName != null && iconToolName.isNotEmpty) ...[
            ToolIcon(toolName: iconToolName, agentTypeName: agentTypeName),
            const SizedBox(width: 8.0),
          ],
          Expanded(
            child: Text.rich(
              TextSpan(
                text: label,
                style: FlutterFlowTheme.of(context).bodyMedium.override(
                      fontWeight: FontWeight.bold,
                      color: FlutterFlowTheme.of(context).primaryText,
                      fontSize: 15.0,
                    ),
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 6.0),
          _toolChevron(context, expanded),
        ],
      ),
    ),
  );
}

Widget _buildUsingToolMessage(BuildContext context, String content, {String? agentTypeName, bool toolUseIsFirst = true, bool toolUseIsLast = true, bool collapsible = false, bool expanded = false, VoidCallback? onToggle}) {
  final toolFormat = _formatToolPattern(content);
  final toolName = toolFormat.toolName;
  final inlineDesc = toolFormat.isMultilineDescription ? null : toolFormat.toolDescription;
  final multiLineCode = toolFormat.isMultilineDescription
      ? _stripWrappingBackticks(toolFormat.toolDescription)
      : null;

  // Build the header line (bold tool name + inline description).
  final List<InlineSpan> firstLineSpans = [];
  if (toolName.isNotEmpty) {
    // Add bold tool name
    firstLineSpans.add(
      TextSpan(
        text: toolName,
        style: FlutterFlowTheme.of(context).bodyMedium.override(
          fontWeight: FontWeight.bold,
          color: FlutterFlowTheme.of(context).primaryText,
          fontSize: 15.0,
        ),
      ),
    );

    // Add description with a space if present
    if (inlineDesc != null && inlineDesc.isNotEmpty) {
      if (toolName != 'Todos') {
        // Add space after tool name
        firstLineSpans.add(
          TextSpan(
            text: '  ',
            style: FlutterFlowTheme.of(context).bodyMedium.override(
              color: FlutterFlowTheme.of(context).primaryText,
              fontSize: 14.0,
            ),
          ),
        );

        // Parse the description for inline code and other formatting
        final descriptionSpans = <InlineSpan>[];
        final textStyle = FlutterFlowTheme.of(context).bodyMedium.override(
          color: FlutterFlowTheme.of(context).primaryText,
          fontSize: 14.0,
        );
        final codeStyle = GoogleFonts.jetBrainsMono().copyWith(
          color: FlutterFlowTheme.of(context).primaryText,
          fontSize: 13.0,
        );

        final linkStyle = textStyle.copyWith(
          color: FlutterFlowTheme.of(context).primary,
          decoration: TextDecoration.underline,
        );
        _parseLineFormatting(context, inlineDesc, textStyle, codeStyle, linkStyle, descriptionSpans);
        firstLineSpans.addAll(descriptionSpans);
      }
    }
  }
  final headerSpan = TextSpan(children: firstLineSpans);
  // Defensive: WidgetSpans can't be measured by TextPainter without placeholder
  // dimensions, so a header containing one keeps its full, wrapping text rather
  // than risk a bad measure. Inline links/URLs are plain TextSpans now, so this
  // is effectively never hit — kept in case a future span type embeds a widget.
  final headerHasWidgetSpan = firstLineSpans.any((s) => s is WidgetSpan);

  // Detail rendered INSIDE the box, below the header (multi-line command + todos).
  final List<Widget> innerDetail = [];
  if (multiLineCode != null && multiLineCode.isNotEmpty) {
    innerDetail.add(const SizedBox(height: 2));
    innerDetail.add(
      Text(
        multiLineCode,
        style: GoogleFonts.jetBrainsMono().copyWith(
          color: FlutterFlowTheme.of(context).primaryText,
          fontSize: 13,
        ),
      ),
    );
  }

  // Check if remainingContent is a lone code block that should be fused into
  // the same outer border as this tool row.
  final remaining = toolFormat.remainingContent.trim();
  final remainingIsCodeBlock = _isSoleCodeBlock(remaining);

  // If remaining content is purely todo list items, fuse them into the tool box.
  final remainingIsTodoList = !remainingIsCodeBlock && _isAllTodoLines(remaining);
  if (remainingIsTodoList && remaining.isNotEmpty) {
    final textStyle = FlutterFlowTheme.of(context).bodyMedium.override(
      color: FlutterFlowTheme.of(context).primaryText,
      fontSize: 16.0,
    );
    final codeStyle = GoogleFonts.jetBrainsMono().copyWith(
      color: FlutterFlowTheme.of(context).primaryText,
      fontSize: 14.0,
    );
    innerDetail.add(const SizedBox(height: 6.0));
    for (final line in remaining.split('\n')) {
      final todoMatch = RegExp(r'^([●◐○])\s+(.+)$').firstMatch(line.trim());
      if (todoMatch != null) {
        innerDetail.add(_buildTodoItem(context, todoMatch.group(1)!, todoMatch.group(2)!, textStyle, codeStyle));
      }
    }
  }

  // Effective remaining after fusing todo list into tool box.
  final effectiveRemaining = remainingIsTodoList ? '' : remaining;

  // Whether this tool has any detail below its header, and whether we show it.
  final hasDetail = innerDetail.isNotEmpty || effectiveRemaining.isNotEmpty;
  final showDetail = !collapsible || expanded;

  // Builds the header. A header that would wrap (a long command, say) collapses
  // to a single ellipsized line, so a tool with no detail of its own is still
  // expandable — tapping reveals the full text.
  Widget buildHeaderRow({required bool headerOverflows}) {
    final expandable = hasDetail || headerOverflows;
    final showChevron = collapsible && expandable;
    final truncate = collapsible && !expanded && headerOverflows;

    final text = Text.rich(
      headerSpan,
      maxLines: truncate ? 1 : null,
      overflow: truncate ? TextOverflow.ellipsis : TextOverflow.clip,
    );

    final showIcon = toolName.isNotEmpty;
    Widget row = (showIcon || showChevron)
        // Pin the icon/chevron to the first line. Centering (the Row default)
        // drifts them to the middle of the block once an expanded header
        // wraps to several lines; they should stay where they sat collapsed.
        ? Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (showIcon) ...[
                Padding(
                  padding: const EdgeInsets.only(top: 2.0),
                  child: ToolIcon(toolName: toolName, agentTypeName: agentTypeName),
                ),
                const SizedBox(width: 8.0),
              ],
              Expanded(child: text),
              if (showChevron) ...[
                const SizedBox(width: 6.0),
                _toolChevron(context, expanded),
              ],
            ],
          )
        : text;
    if (showChevron && onToggle != null) {
      row = GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          HapticFeedback.selectionClick();
          onToggle();
        },
        child: row,
      );
    }
    return row;
  }

  final Widget headerRow;
  if (!collapsible || headerHasWidgetSpan || firstLineSpans.isEmpty) {
    headerRow = buildHeaderRow(headerOverflows: false);
  } else {
    // Measure against the width the text actually gets, so the chevron only
    // appears when the header genuinely doesn't fit on one line.
    headerRow = LayoutBuilder(
      builder: (context, constraints) {
        const chevronReserve = 24.0; // chevron + gap
        final painter = TextPainter(
          text: headerSpan,
          maxLines: 1,
          textDirection: Directionality.of(context),
          textScaler: MediaQuery.textScalerOf(context),
        )..layout(
            maxWidth:
                (constraints.maxWidth - chevronReserve).clamp(0.0, double.infinity));
        final overflows = painter.didExceedMaxLines;
        painter.dispose();
        return buildHeaderRow(headerOverflows: overflows);
      },
    );
  }

  final boxChildren = <Widget>[headerRow];
  if (showDetail) boxChildren.addAll(innerDetail);

  // A fused code block only renders below the box when the detail is shown.
  final renderCode = showDetail && effectiveRemaining.isNotEmpty && remainingIsCodeBlock;
  final renderMarkdown = showDetail && effectiveRemaining.isNotEmpty && !remainingIsCodeBlock;

  const radius = 8.0;
  final borderColor = FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3);

  // The box rounds its bottom unless a fused code block follows it.
  final boxIsLast = toolUseIsLast && !renderCode;
  final toolRow = _toolBorderedBox(
    context,
    isFirst: toolUseIsFirst,
    isLast: boxIsLast,
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: boxChildren),
  );

  if (renderCode) {
    // Fuse the code block into the same outer group border.
    final codeLines = _extractCodeBlockLines(effectiveRemaining);
    final codeLanguage = _extractCodeBlockLanguage(effectiveRemaining);
    final codeBottomBorderRadius = BorderRadius.only(
      bottomLeft: toolUseIsLast ? const Radius.circular(radius) : Radius.zero,
      bottomRight: toolUseIsLast ? const Radius.circular(radius) : Radius.zero,
    );
    final bareCode = _buildCodeBlock(
      context,
      codeLines,
      false,
      codeLanguage,
      agentTypeName?.toLowerCase() != 'codex',
      bare: true,
    );
    final codeSection = CustomPaint(
      foregroundPainter: _PartialRoundedBorderPainter(
        color: borderColor,
        borderWidth: 0.5,
        borderRadius: codeBottomBorderRadius,
        drawTop: false,
      ),
      child: ClipRRect(
        borderRadius: codeBottomBorderRadius,
        child: Container(
          width: double.infinity,
          color: FlutterFlowTheme.of(context).codeBlockBackground,
          child: bareCode,
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [toolRow, codeSection],
    );
  }

  if (renderMarkdown) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        toolRow,
        buildMarkdownText(
          context,
          effectiveRemaining,
          false,
          onSendMessage: (content) {},
          agentTypeName: agentTypeName,
        ),
      ],
    );
  }

  return toolRow;
}

/// Public parse of a "Using tool:" / "**Exec:**" / patch message into its
/// tool name, description, trailing content, and multi-line flag. Backs the
/// collapsed tool-use group (`tool_use_group.dart`) so parsing stays in one
/// place. Callers should pass already project-root-filtered content.
({
  String toolName,
  String toolDescription,
  String remainingContent,
  bool isMultilineDescription,
}) parseToolMessage(String content) {
  final f = _formatToolPattern(content);
  return (
    toolName: f.toolName,
    toolDescription: f.toolDescription,
    remainingContent: f.remainingContent,
    isMultilineDescription: f.isMultilineDescription,
  );
}

/// Applies the same content cleanup [buildMarkdownText] does before rendering a
/// tool use — project-root filtering, then codex `**Status:**` stripping — so
/// the collapsed tool-use group parses/renders exactly what the chat would.
String sanitizeToolContent(
  String content, {
  String? agentTypeName,
  String Function(String content)? filterProjectRoot,
}) {
  var c = filterProjectRoot?.call(content) ?? content;
  if (agentTypeName?.toLowerCase() == 'codex') {
    final lines = c.split('\n');
    final statusIndex = lines
        .indexWhere((line) => RegExp(r'\*\*Status:\*\*').hasMatch(line.trim()));
    if (statusIndex != -1) c = lines.sublist(0, statusIndex).join('\n');
  }
  return c;
}

/// Renders one tool use in the current bordered format, but with its detail
/// (output/code/todos) collapsed behind a right-chevron in the header row. A
/// header too long for one line is ellipsized and expands the same way, so pass
/// [onToggle] unconditionally — the row decides whether it's expandable.
/// [content] must already be sanitized (see [sanitizeToolContent]).
Widget buildCollapsibleToolRow(
  BuildContext context,
  String content, {
  String? agentTypeName,
  bool toolUseIsFirst = true,
  bool toolUseIsLast = true,
  bool expanded = false,
  VoidCallback? onToggle,
}) =>
    _buildUsingToolMessage(
      context,
      content,
      agentTypeName: agentTypeName,
      toolUseIsFirst: toolUseIsFirst,
      toolUseIsLast: toolUseIsLast,
      collapsible: true,
      expanded: expanded,
      onToggle: onToggle,
    );

/// Returns true when [content] (trimmed) is exactly one fenced code block.
bool _isSoleCodeBlock(String content) {
  if (content.isEmpty) return false;
  final lines = content.split('\n');
  final fenceMatch = _matchMarkdownFence(lines.first);
  if (fenceMatch == null) return false;
  final fence = fenceMatch.group(1)!;
  final fenceChar = fence[0];
  final fenceLength = fence.length;
  for (int i = 1; i < lines.length; i++) {
    final m = _matchMarkdownFence(lines[i]);
    if (m != null) {
      final f = m.group(1)!;
      if (f[0] == fenceChar && f.length >= fenceLength && (m.group(2) ?? '').trim().isEmpty) {
        // Closing fence found — everything after must be whitespace only
        final after = lines.sublist(i + 1).join('\n').trim();
        return after.isEmpty;
      }
    }
  }
  return false;
}

/// Returns true when every non-empty line in [content] is a todo item (●◐○).
bool _isAllTodoLines(String content) {
  if (content.isEmpty) return false;
  final lines = content.split('\n');
  final nonEmpty = lines.where((l) => l.trim().isNotEmpty).toList();
  if (nonEmpty.isEmpty) return false;
  final todoRegex = RegExp(r'^[●◐○]\s+.+$');
  return nonEmpty.every((l) => todoRegex.hasMatch(l.trim()));
}

/// Extracts the code lines from a sole fenced code block (strips opening/closing fences).
List<String> _extractCodeBlockLines(String content) {
  final lines = content.split('\n');
  if (lines.length < 2) return [];
  final fenceMatch = _matchMarkdownFence(lines.first);
  if (fenceMatch == null) return lines;
  final fence = fenceMatch.group(1)!;
  final fenceChar = fence[0];
  final fenceLength = fence.length;
  int closeIndex = lines.length;
  for (int i = 1; i < lines.length; i++) {
    final m = _matchMarkdownFence(lines[i]);
    if (m != null) {
      final f = m.group(1)!;
      if (f[0] == fenceChar && f.length >= fenceLength && (m.group(2) ?? '').trim().isEmpty) {
        closeIndex = i;
        break;
      }
    }
  }
  return lines.sublist(1, closeIndex);
}

/// Extracts the language identifier from the opening fence line.
String? _extractCodeBlockLanguage(String content) {
  final firstLine = content.split('\n').first;
  return _parseCodeBlockLanguage(firstLine);
}

_ToolMessageFormat _formatToolPattern(String content) {
  final lines = content.split('\n');
  final firstLine = lines.first.trim();

  var toolName = '';
  var toolDescription = '';
  var isMultilineDescription = false;
  var remainingContent = lines.length > 1 ? lines.sublist(1).join('\n').trim() : '';

  final codexMatch = RegExp(r'\*\*Exec:\*\*\s*(.*)').firstMatch(firstLine);
  if (codexMatch != null) {
    toolName = 'Exec';
    toolDescription = _stripShellPrefix(codexMatch.group(1) ?? '');

    if (toolDescription.startsWith('`') && !toolDescription.endsWith('`')) {
      toolDescription += '`';
    }

    if (toolDescription.startsWith('`ls')) {
      toolName = 'List';
    } else if (toolDescription.startsWith('`rg') ||
        toolDescription.startsWith('`ripgrep') ||
        toolDescription.startsWith('`grep')) {
      toolName = 'Search';
    } else if (RegExp(r"sed\s+-n\s+'(\d+),(\d+)p'").hasMatch(toolDescription)) {
      toolName = 'Read';
    } else if (RegExp(r"<<\s*'([^']+)'").hasMatch(toolDescription)) {
      if (!isMultilineDescription) {
        toolDescription += '`';
        remainingContent = _formatHeredocInContent(content);
      }
    }

    return _ToolMessageFormat(
      toolName: toolName,
      toolDescription: toolDescription,
      remainingContent: remainingContent,
      isMultilineDescription: isMultilineDescription,
    );
  }

  if (firstLine.contains('✏️ Applying patch to') && firstLine.contains('file (+')) {
    toolName = 'Edited';
    final patchMatch = RegExp(r'✏️ Applying patch to \d+ file \(([^)]+)\)').firstMatch(firstLine);
    if (patchMatch != null) {
      toolDescription = patchMatch.group(1) ?? '';
      if (lines.length > 2) {
        final fileName = lines[1].trim().replaceAll('└ ', '');
        toolDescription = '`$fileName` $toolDescription';
        remainingContent = lines
            .sublist(2)
            .where((line) => !line.startsWith('**$fileName'))
            .join('\n')
            .trim();
      }
    }

    return _ToolMessageFormat(
      toolName: toolName,
      toolDescription: toolDescription,
      remainingContent: remainingContent,
      isMultilineDescription: isMultilineDescription,
    );
  }

  final match = RegExp(r'(?:🔧\s*)?Using tool:\s*(?:\*\*)?([^*-]+?)(?:\*\*)?\s*(?:-\s*(.+))?$')
      .firstMatch(firstLine);
  if (match == null) {
    return const _ToolMessageFormat(
      toolName: '',
      toolDescription: '',
      remainingContent: '',
      isMultilineDescription: false,
    );
  }

  toolName = match.group(1)?.trim() ?? '';
  toolDescription = match.group(2)?.trim() ?? '';

  if (toolDescription.startsWith('`') && !toolDescription.endsWith('`')) {
    // The backtick-wrapped description spans multiple lines — find the closing backtick.
    final descLines = <String>[toolDescription.substring(1)]; // strip opening `
    final restLines = lines.length > 1 ? lines.sublist(1) : <String>[];
    var closingIdx = -1;
    for (int i = 0; i < restLines.length; i++) {
      final l = restLines[i];
      if (l.endsWith('`')) {
        descLines.add(l.substring(0, l.length - 1)); // strip closing `
        closingIdx = i;
        break;
      }
      descLines.add(l);
    }
    if (closingIdx >= 0) {
      // Emit the multi-line command as a fenced code block in remainingContent so
      // _buildUsingToolMessage can fuse it with the tool row.
      final codeBlock = '```\n${descLines.join('\n')}\n```';
      final afterLines = restLines.sublist(closingIdx + 1);
      final afterContent = afterLines.join('\n').trim();
      remainingContent = afterContent.isEmpty ? codeBlock : '$codeBlock\n$afterContent';
      toolDescription = '';
    } else {
      toolDescription += '`';
    }
  }

  if (toolName == 'TodoWrite') {
    toolName = 'Todos';
  }

  return _ToolMessageFormat(
    toolName: toolName,
    toolDescription: toolDescription,
    remainingContent: remainingContent,
    isMultilineDescription: isMultilineDescription,
  );
}

String _stripShellPrefix(String value) {
  return value.replaceAll('bash -lc ', '').replaceAll('zsh -lc ', '');
}

String _stripWrappingBackticks(String value) {
  return value.replaceFirst(RegExp(r'^`'), '').replaceFirst(RegExp(r'`$'), '').trim();
}

/// Paints a rounded-rectangle border, optionally skipping the top edge.
///
/// When [drawTop] is false the left and right strokes extend to y=0 (the top
/// of the widget) so they connect seamlessly with the bottom strokes of the
/// preceding sibling — giving a single shared border between consecutive
/// tool-use rows rather than a doubled line.
class _PartialRoundedBorderPainter extends CustomPainter {
  const _PartialRoundedBorderPainter({
    required this.color,
    required this.borderWidth,
    required this.borderRadius,
    required this.drawTop,
  });

  final Color color;
  final double borderWidth;
  final BorderRadius borderRadius;
  final bool drawTop;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = borderWidth
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.butt;

    final half = borderWidth / 2;
    final w = size.width;
    final h = size.height;
    final blr = borderRadius.bottomLeft.x;
    final brr = borderRadius.bottomRight.x;

    if (drawTop) {
      canvas.drawRRect(
        RRect.fromLTRBAndCorners(
          half, half, w - half, h - half,
          topLeft: borderRadius.topLeft,
          topRight: borderRadius.topRight,
          bottomLeft: borderRadius.bottomLeft,
          bottomRight: borderRadius.bottomRight,
        ),
        paint,
      );
      return;
    }

    // No top border: draw left side, bottom (with corners), and right side,
    // starting and ending at y=0 so they butt against the row above.
    final path = Path()
      ..moveTo(half, 0)
      ..lineTo(half, h - half - blr);
    if (blr > 0) {
      path.arcToPoint(Offset(half + blr, h - half), radius: Radius.circular(blr), clockwise: false);
    }
    path.lineTo(w - half - brr, h - half);
    if (brr > 0) {
      path.arcToPoint(Offset(w - half, h - half - brr), radius: Radius.circular(brr), clockwise: false);
    }
    path.lineTo(w - half, 0);

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_PartialRoundedBorderPainter old) =>
      old.color != color ||
      old.borderWidth != borderWidth ||
      old.borderRadius != borderRadius ||
      old.drawTop != drawTop;
}

String _formatHeredocInContent(String content) {
  if (!content.contains('<<') || !RegExp(r"<<\s*'([^']+)'").hasMatch(content)) {
    return content;
  }

  final heredocMatch = RegExp(r"<<\s*'([^']+)'").firstMatch(content);
  if (heredocMatch == null) {
    return content;
  }

  final delimiter = heredocMatch.group(1) ?? '';
  final lines = content.split('\n');
  var startIndex = -1;
  var endIndex = -1;

  for (var i = 0; i < lines.length; i++) {
    if (lines[i].contains("<<'$delimiter'")) {
      startIndex = i + 1;
    } else if (lines[i].trim().startsWith(delimiter) && startIndex != -1) {
      endIndex = i;
      break;
    }
  }

  if (startIndex != -1 && endIndex != -1) {
    final newLines = [...lines];
    newLines.insert(startIndex, '```');
    newLines.insert(endIndex + 1, '```');
    return newLines.join('\n');
  }

  return content;
}
