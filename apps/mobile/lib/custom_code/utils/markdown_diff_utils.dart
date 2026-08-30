import 'dart:math' as math;

enum DiffLineType { add, remove, context, ellipsis }

class DiffLine {
  final String content;
  final DiffLineType type;

  const DiffLine({
    required this.content,
    required this.type,
  });
}

const int diffContextLines = 3;

String stripDiffPrefix(String line) => line.substring(1);

bool isDiffHeaderLine(String line) =>
    line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@');

String formatMergedLine(String prefix, String content) {
  final spacer = content.startsWith(' ') ? '' : ' ';
  return '$prefix$spacer$content';
}

List<DiffLine> buildMergedDiffLines(
  List<String> removedLines,
  List<String> addedLines,
  bool compactContext,
) {
  final removedLength = removedLines.length;
  final addedLength = addedLines.length;
  final lcs = List.generate(
    removedLength + 1,
    (_) => List.filled(addedLength + 1, 0),
  );

  for (int i = 1; i <= removedLength; i++) {
    for (int j = 1; j <= addedLength; j++) {
      if (removedLines[i - 1] == addedLines[j - 1]) {
        lcs[i][j] = lcs[i - 1][j - 1] + 1;
      } else {
        lcs[i][j] = math.max(lcs[i - 1][j], lcs[i][j - 1]);
      }
    }
  }

  final result = <DiffLine>[];
  int i = removedLength;
  int j = addedLength;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && removedLines[i - 1] == addedLines[j - 1]) {
      result.insert(
        0,
        DiffLine(
          content: formatMergedLine(' ', removedLines[i - 1]),
          type: DiffLineType.context,
        ),
      );
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i == 0 || lcs[i][j - 1] >= lcs[i - 1][j])) {
      result.insert(
        0,
        DiffLine(
          content: formatMergedLine('+', addedLines[j - 1]),
          type: DiffLineType.add,
        ),
      );
      j -= 1;
    } else if (i > 0) {
      result.insert(
        0,
        DiffLine(
          content: formatMergedLine('-', removedLines[i - 1]),
          type: DiffLineType.remove,
        ),
      );
      i -= 1;
    }
  }

  if (!compactContext) {
    return result;
  }

  final compacted = <DiffLine>[];
  var contextBuffer = <DiffLine>[];

  for (final item in result) {
    if (item.type == DiffLineType.context) {
      contextBuffer.add(item);
      continue;
    }

    if (contextBuffer.length > diffContextLines * 2 + 1) {
      compacted.addAll(contextBuffer.take(diffContextLines));
      compacted.add(const DiffLine(content: '...', type: DiffLineType.ellipsis));
      compacted.addAll(contextBuffer.skip(contextBuffer.length - diffContextLines));
    } else {
      compacted.addAll(contextBuffer);
    }

    contextBuffer = [];
    compacted.add(item);
  }

  if (contextBuffer.length > diffContextLines) {
    compacted.addAll(contextBuffer.take(diffContextLines));
    compacted.add(const DiffLine(content: '...', type: DiffLineType.ellipsis));
  } else {
    compacted.addAll(contextBuffer);
  }

  return compacted;
}

List<DiffLine> formatDiffLines(
  String text,
  bool shouldMergeDiff, {
  bool compactContext = true,
}) {
  final lines = text.split('\n');
  final result = <DiffLine>[];
  var removedLines = <String>[];
  var addedLines = <String>[];
  var rawLines = <String>[];
  var isMergeable = true;
  var hasAddedLines = false;

  void flush() {
    if (rawLines.isEmpty) {
      return;
    }

    if (shouldMergeDiff && isMergeable && removedLines.isNotEmpty && addedLines.isNotEmpty) {
      result.addAll(buildMergedDiffLines(removedLines, addedLines, compactContext));
    } else {
      for (final line in rawLines) {
        if (line.startsWith('+')) {
          result.add(DiffLine(content: line, type: DiffLineType.add));
        } else if (line.startsWith('-')) {
          result.add(DiffLine(content: line, type: DiffLineType.remove));
        } else {
          result.add(DiffLine(content: line, type: DiffLineType.context));
        }
      }
    }

    removedLines = [];
    addedLines = [];
    rawLines = [];
    isMergeable = true;
    hasAddedLines = false;
  }

  for (final line in lines) {
    if (isDiffHeaderLine(line)) {
      flush();
      result.add(DiffLine(content: line, type: DiffLineType.context));
      continue;
    }

    if (line.startsWith('+') || line.startsWith('-')) {
      rawLines.add(line);
      if (line.startsWith('+')) {
        addedLines.add(stripDiffPrefix(line));
        hasAddedLines = true;
      } else {
        if (hasAddedLines) {
          isMergeable = false;
        }
        removedLines.add(stripDiffPrefix(line));
      }
      continue;
    }

    flush();
    result.add(DiffLine(content: line, type: DiffLineType.context));
  }

  flush();
  return result;
}
