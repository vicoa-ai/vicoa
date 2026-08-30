/// Utilities for sanitizing and cleaning text content
library;

/// Removes content matching the provided regex pattern, but only when it appears
/// outside of markdown code blocks (delimited by triple backticks).
///
/// This is useful for filtering out control messages or other metadata that should
/// be removed from display, while preserving the same content when it appears in
/// code examples or documentation.
///
/// Example:
/// ```dart
/// final regex = RegExp(r'\{\s*"type"\s*:\s*"control"[^}]*\}');
/// final cleaned = removePatternOutsideCodeBlocks(content, regex);
/// ```
String removePatternOutsideCodeBlocks(String content, RegExp pattern) {
  return replacePatternOutsideCodeBlocks(content, pattern, '');
}

/// Replaces content matching the provided regex pattern with a replacement string,
/// but only when it appears outside of markdown code blocks (delimited by triple backticks).
///
/// This is useful for normalizing whitespace or transforming content outside code blocks
/// while preserving the exact formatting inside code blocks.
///
/// Example:
/// ```dart
/// // Collapse multiple spaces to single space outside code blocks
/// final cleaned = replacePatternOutsideCodeBlocks(content, RegExp(r'[ \t]{2,}'), ' ');
/// ```
String replacePatternOutsideCodeBlocks(String content, RegExp pattern, String replacement) {
  if (content.isEmpty) {
    return '';
  }

  final lines = content.split('\n');
  final result = StringBuffer();
  bool inCodeBlock = false;

  for (int i = 0; i < lines.length; i++) {
    final line = lines[i];
    final trimmedLine = line.trim();

    // Check if we're entering or exiting a code block
    if (trimmedLine.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      result.writeln(line);
      continue;
    }

    // If we're in a code block, keep the line as-is
    if (inCodeBlock) {
      result.writeln(line);
      continue;
    }

    // Outside code blocks: replace pattern matches
    final cleanedLine = line.replaceAll(pattern, replacement);
    result.writeln(cleanedLine);
  }

  // Remove the trailing newline added by the last writeln
  final resultStr = result.toString();
  return resultStr.endsWith('\n')
      ? resultStr.substring(0, resultStr.length - 1)
      : resultStr;
}
