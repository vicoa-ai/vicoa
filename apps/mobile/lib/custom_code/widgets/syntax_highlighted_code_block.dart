import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';
import 'package:highlight/highlight.dart' show highlight, Node;

import '/l10n/app_localizations.dart';

// Create a custom theme without background colors
Map<String, TextStyle> createNoBackgroundTheme(Map<String, TextStyle> baseTheme) {
  return baseTheme.map((key, style) {
    return MapEntry(key, style.copyWith(backgroundColor: Colors.transparent));
  });
}

String resolveCodeLanguage(String? language) {
  if (language == null) {
    return 'plaintext';
  }
  final normalized = language.trim().toLowerCase();
  if (normalized.isEmpty) {
    return 'plaintext';
  }

  switch (normalized) {
    case 'bash':
    case 'shell':
    case 'sh':
      return 'bash';
    case 'csharp':
    case 'cs':
      return 'cs';
    case 'css':
      return 'css';
    case 'dart':
      return 'dart';
    case 'diff':
      return 'diff';
    case 'go':
    case 'golang':
      return 'go';
    case 'java':
      return 'java';
    case 'javascript':
    case 'js':
      return 'javascript';
    case 'json':
      return 'json';
    case 'kotlin':
    case 'kt':
      return 'kotlin';
    case 'markdown':
    case 'md':
      return 'markdown';
    case 'php':
      return 'php';
    case 'python':
    case 'py':
      return 'python';
    case 'rust':
    case 'rs':
      return 'rust';
    case 'sql':
      return 'sql';
    case 'swift':
      return 'swift';
    case 'typescript':
    case 'ts':
      return 'typescript';
    case 'xml':
    case 'html':
      return 'xml';
    case 'yaml':
    case 'yml':
      return 'yaml';
    default:
      return 'plaintext';
  }
}

class SyntaxHighlightedCodeBlock extends StatefulWidget {
  const SyntaxHighlightedCodeBlock({
    super.key,
    required this.code,
    required this.language,
    required this.textStyle,
    required this.backgroundColor,
    required this.borderColor,
    this.bare = false,
  });

  final String code;
  final String language;
  final TextStyle textStyle;
  final Color backgroundColor;
  final Color borderColor;
  // When true, renders only the scrollable content with no outer container/border/margin.
  final bool bare;

  @override
  State<SyntaxHighlightedCodeBlock> createState() => _SyntaxHighlightedCodeBlockState();
}

class _SyntaxHighlightedCodeBlockState extends State<SyntaxHighlightedCodeBlock> {
  Widget _buildScrollContent() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(vertical: 12.0, horizontal: 12.0),
      child: SelectableHighlightView(
        widget.code,
        language: widget.language,
        theme: createNoBackgroundTheme(monokaiSublimeTheme),
        textStyle: widget.textStyle,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (widget.bare) {
      return _buildScrollContent();
    }
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 8.0, bottom: 8.0),
      decoration: BoxDecoration(
        color: widget.backgroundColor,
        border: Border.all(
          color: widget.borderColor,
          width: 0.5,
        ),
        borderRadius: BorderRadius.circular(8.0),
      ),
      child: _buildScrollContent(),
    );
  }
}

class SelectableHighlightView extends StatelessWidget {
  SelectableHighlightView(
    String input, {
    super.key,
    this.language,
    this.theme = const {},
    this.padding,
    this.textStyle,
    int tabSize = 8,
  }) : source = input.replaceAll('\t', ' ' * tabSize);

  final String source;
  final String? language;
  final Map<String, TextStyle> theme;
  final EdgeInsetsGeometry? padding;
  final TextStyle? textStyle;

  static const _rootKey = 'root';
  static const _defaultFontFamily = 'monospace';

  List<TextSpan> _convert(List<Node> nodes) {
    List<TextSpan> spans = [];
    var currentSpans = spans;
    List<List<TextSpan>> stack = [];

    void traverse(Node node) {
      if (node.value != null) {
        currentSpans.add(
          node.className == null
              ? TextSpan(text: node.value)
              : TextSpan(text: node.value, style: theme[node.className!]),
        );
      } else if (node.children != null) {
        List<TextSpan> tmp = [];
        currentSpans.add(TextSpan(children: tmp, style: theme[node.className!]));
        stack.add(currentSpans);
        currentSpans = tmp;

        for (final child in node.children!) {
          traverse(child);
          if (child == node.children!.last) {
            currentSpans = stack.isEmpty ? spans : stack.removeLast();
          }
        }
      }
    }

    for (final node in nodes) {
      traverse(node);
    }

    return spans;
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    var resolvedStyle = TextStyle(
      fontFamily: _defaultFontFamily,
      color: theme[_rootKey]?.color ?? colorScheme.onSurface,
    );
    if (textStyle != null) {
      resolvedStyle = resolvedStyle.merge(textStyle);
    }

    final nodes = highlight.parse(source, language: language).nodes ?? [];
    return Container(
      color: theme[_rootKey]?.backgroundColor ?? colorScheme.surface,
      padding: padding,
      child: ScrollConfiguration(
        behavior: _NoScrollToSelectionBehavior(),
        child: SelectableText.rich(
          TextSpan(
            style: resolvedStyle,
            children: _convert(nodes),
          ),
          contextMenuBuilder: (context, state) {
            final filteredItems = state.contextMenuButtonItems
                .where(
                  (item) =>
                      item.type != ContextMenuButtonType.lookUp &&
                      item.type != ContextMenuButtonType.searchWeb,
                )
                .map((item) {
                  // Customize Share button to remove ellipsis
                  if (item.type == ContextMenuButtonType.share) {
                    return ContextMenuButtonItem(
                      type: ContextMenuButtonType.share,
                      onPressed: item.onPressed,
                      label: AppLocalizations.of(context).commonShare, // Remove the "..." from "Share..."
                    );
                  }
                  return item;
                })
                .toList();

            final hasSelectAll = filteredItems
                .any((item) => item.type == ContextMenuButtonType.selectAll);
            if (!hasSelectAll) {
              final selectAllItem = ContextMenuButtonItem(
                type: ContextMenuButtonType.selectAll,
                onPressed: () {
                  state.selectAll(SelectionChangedCause.toolbar);
                },
              );

              final shareIndex = filteredItems
                  .indexWhere((item) => item.type == ContextMenuButtonType.share);
              if (shareIndex != -1) {
                filteredItems.insert(shareIndex, selectAllItem);
              } else {
                filteredItems.add(selectAllItem);
              }
            }

            return AdaptiveTextSelectionToolbar.buttonItems(
              anchors: state.contextMenuAnchors,
              buttonItems: filteredItems,
            );
          },
          maxLines: null,
        ),
      ),
    );
  }
}

/// Custom scroll behavior that prevents automatic scrolling when text is selected
/// This prevents the page from auto-scrolling when long-pressing code blocks
class _NoScrollToSelectionBehavior extends ScrollBehavior {
  @override
  Widget buildOverscrollIndicator(
      BuildContext context, Widget child, ScrollableDetails details) {
    return child;
  }

  @override
  ScrollPhysics getScrollPhysics(BuildContext context) {
    return const NeverScrollableScrollPhysics();
  }
}
