import '/flutter_flow/flutter_flow_theme.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

// Box-drawing characters or markdown table rows: a grid whose columns must
// stay aligned, so it scrolls sideways instead of wrapping. Prose and code
// wrap. Mirrors isGridPreview in apps/web ask-user-question-panel.tsx.
final _gridPreview = RegExp(r'[─-╿]|^\s*\|.*\|\s*$', multiLine: true);

bool isGridPreview(String preview) => _gridPreview.hasMatch(preview);

TextStyle _previewTextStyle(BuildContext context) => GoogleFonts.jetBrainsMono().copyWith(color: FlutterFlowTheme.of(context).primaryText, fontSize: 12, height: 1.4);

/// The focused option's preview (a draft, mockup or snippet), shown once
/// under the option list in the selected option's colour.
class AskUserQuestionPreviewPane extends StatefulWidget {
  const AskUserQuestionPreviewPane({super.key, required this.preview});

  final String preview;

  @override
  State<AskUserQuestionPreviewPane> createState() => _AskUserQuestionPreviewPaneState();
}

class _AskUserQuestionPreviewPaneState extends State<AskUserQuestionPreviewPane> {
  final ScrollController _scroll = ScrollController();
  bool _moreBefore = false;
  bool _moreAfter = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_updateEdges);
    WidgetsBinding.instance.addPostFrameCallback((_) => _updateEdges());
  }

  @override
  void didUpdateWidget(covariant AskUserQuestionPreviewPane oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.preview == widget.preview) return;
    // A different option's preview starts at its left edge.
    if (_scroll.hasClients) _scroll.jumpTo(0);
    WidgetsBinding.instance.addPostFrameCallback((_) => _updateEdges());
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _updateEdges() {
    if (!mounted || !_scroll.hasClients) return;
    final position = _scroll.position;
    final before = position.pixels > 1;
    final after = position.pixels < position.maxScrollExtent - 1;
    if (before != _moreBefore || after != _moreAfter) setState(() { _moreBefore = before; _moreAfter = after; });
  }

  void _openFullScreen() {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final theme = FlutterFlowTheme.of(dialogContext);
        return Dialog.fullscreen(
          backgroundColor: theme.secondaryBackground,
          child: SafeArea(
            child: Stack(
              children: [
                // Pan both ways and pinch to zoom: a wide grid rarely fits a phone.
                InteractiveViewer(
                  constrained: false,
                  minScale: 0.5,
                  maxScale: 3,
                  boundaryMargin: const EdgeInsets.all(32),
                  child: Padding(padding: const EdgeInsetsDirectional.fromSTEB(16, 56, 16, 16), child: Text(widget.preview, softWrap: false, style: _previewTextStyle(dialogContext))),
                ),
                PositionedDirectional(top: 4, end: 4, child: IconButton(icon: Icon(Icons.close_rounded, color: theme.secondaryText), onPressed: () => Navigator.of(dialogContext).pop())),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = FlutterFlowTheme.of(context);
    final decoration = BoxDecoration(color: theme.primaryText.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(10));
    const padding = EdgeInsetsDirectional.fromSTEB(12, 10, 12, 10);

    if (!isGridPreview(widget.preview)) {
      return Container(width: double.infinity, padding: padding, decoration: decoration, child: Text(widget.preview, style: _previewTextStyle(context)));
    }

    return Container(
      width: double.infinity,
      decoration: decoration,
      child: Stack(
        children: [
          NotificationListener<ScrollMetricsNotification>(
            onNotification: (_) {
              WidgetsBinding.instance.addPostFrameCallback((_) => _updateEdges());
              return false;
            },
            // Fade whichever edge still has content past it.
            child: ShaderMask(
              blendMode: BlendMode.dstIn,
              shaderCallback: (rect) {
                final fade = rect.width > 0 ? (32 / rect.width).clamp(0.0, 0.5) : 0.0;
                return LinearGradient(
                  colors: [_moreBefore ? Colors.transparent : Colors.black, Colors.black, Colors.black, _moreAfter ? Colors.transparent : Colors.black],
                  stops: [0, fade, 1 - fade, 1],
                ).createShader(rect);
              },
              child: SingleChildScrollView(controller: _scroll, scrollDirection: Axis.horizontal, padding: padding, child: Text(widget.preview, softWrap: false, style: _previewTextStyle(context))),
            ),
          ),
          if (_moreBefore || _moreAfter)
            PositionedDirectional(
              top: 4,
              end: 4,
              child: Material(
                color: theme.secondaryBackground.withValues(alpha: 0.85),
                shape: const CircleBorder(),
                clipBehavior: Clip.antiAlias,
                child: InkWell(onTap: _openFullScreen, child: Padding(padding: const EdgeInsets.all(6), child: Icon(Icons.open_in_full_rounded, size: 16, color: theme.secondaryText))),
              ),
            ),
        ],
      ),
    );
  }
}
