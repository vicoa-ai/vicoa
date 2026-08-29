import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'dart:async';

class FileMentionParams {
  final List<String> files;
  final String searchTerm;
  const FileMentionParams(this.files, this.searchTerm);
}

List<String> filterFileMentionsInBackground(FileMentionParams params) {
  final files = params.files;
  final searchTerm = params.searchTerm;

  final matches = files
      .map((file) => {'file': file, 'score': fuzzyMatchScore(searchTerm, file)})
      .where((item) => (item['score'] as int) > 0)
      .toList()
    ..sort((a, b) => (b['score'] as int).compareTo(a['score'] as int));

  return matches.take(6).map((item) => item['file'] as String).toList();
}

int fuzzyMatchScore(String search, String target) {
  final searchLower = search.toLowerCase();
  final targetLower = target.toLowerCase();

  int searchIndex = 0;
  int score = 0;
  int consecutiveMatches = 0;

  for (int i = 0; i < targetLower.length && searchIndex < searchLower.length; i++) {
    if (targetLower[i] == searchLower[searchIndex]) {
      searchIndex++;
      consecutiveMatches++;
      score += 1 + consecutiveMatches;
      if (i > 0 && targetLower[i - 1] == '/') score += 5;
      if (i == 0) score += 10;
    } else {
      consecutiveMatches = 0;
    }
  }

  if (searchIndex < searchLower.length) return 0;
  score -= (target.length * 0.1).round();
  return score;
}

mixin FileMentionMixin {
  List<String> fileMentions = [];
  List<String> filteredFileMentions = [];
  bool showFileMentionSuggestions = false;
  bool isLoadingFileMentions = false;
  int fileMentionSuggestionsRevision = 0;

  Timer? _fileMentionDebounceTimer;
  int _fileMentionQuerySequence = 0;

  TextEditingController get fileMentionTextController;
  VoidCallback? get fileMentionOnStateChanged;

  /// Lazy hook: called the first time the user types `@` so subclasses can
  /// load the file list on demand (disk cache or network) without paying the
  /// cost on chat open. Default is a no-op.
  Future<void> ensureFileMentionsLoaded() async {}

  void setFileMentionSuggestions({
    required bool show,
    required List<String> suggestions,
  }) {
    final didChange = show != showFileMentionSuggestions ||
        !listEquals(filteredFileMentions, suggestions);
    showFileMentionSuggestions = show;
    filteredFileMentions = suggestions;
    if (didChange) {
      fileMentionSuggestionsRevision++;
      fileMentionOnStateChanged?.call();
    }
  }

  static final RegExp _separatorPattern = RegExp(r'[_\-\s.]');

  List<String> quickFilterFileMentions(String searchTerm) {
    final searchLower = searchTerm.trim().toLowerCase();
    if (searchLower.isEmpty) return const [];

    final searchNorm = searchLower.replaceAll(_separatorPattern, '');

    final startsWithMatches = <String>[];
    final containsMatches = <String>[];

    for (final file in fileMentions) {
      final fileLower = file.toLowerCase();
      final fileNorm = fileLower.replaceAll(_separatorPattern, '');
      if (fileLower.startsWith(searchLower) ||
          fileLower.contains('/$searchLower') ||
          fileNorm.startsWith(searchNorm)) {
        startsWithMatches.add(file);
      } else if (fileLower.contains(searchLower) || fileNorm.contains(searchNorm)) {
        containsMatches.add(file);
      } else {
        continue;
      }
      if (startsWithMatches.length + containsMatches.length >= 6) break;
    }

    final combined = <String>[...startsWithMatches, ...containsMatches];
    return combined.length <= 6 ? combined : combined.take(6).toList();
  }

  void filterFileMentions(String text) {
    _fileMentionQuerySequence++;
    final querySequence = _fileMentionQuerySequence;
    _fileMentionDebounceTimer?.cancel();

    final selection = fileMentionTextController.selection;
    final cursorPos = selection.isValid && selection.baseOffset >= 0
        ? selection.baseOffset.clamp(0, text.length)
        : text.length;

    final lastAtIndex =
        cursorPos > 0 ? text.lastIndexOf('@', cursorPos - 1) : -1;
    if (lastAtIndex == -1) {
      setFileMentionSuggestions(show: false, suggestions: const []);
      return;
    }

    if (lastAtIndex > 0) {
      final charBefore = text[lastAtIndex - 1];
      if (charBefore != ' ' && charBefore != '\n' && charBefore != '\t') {
        setFileMentionSuggestions(show: false, suggestions: const []);
        return;
      }
    }

    final searchTerm = text.substring(lastAtIndex + 1, cursorPos);

    // A space/newline after @ means the phrase is complete — stop searching.
    if (searchTerm.contains(' ') || searchTerm.contains('\n') || searchTerm.contains('\t')) {
      setFileMentionSuggestions(show: false, suggestions: const []);
      return;
    }

    // Lazy-load the file list on first `@`. The hook is async; once the load
    // completes the subclass fires onStateChanged, which re-runs filtering.
    if (fileMentions.isEmpty && !isLoadingFileMentions) {
      unawaited(ensureFileMentionsLoaded());
    }

    if (searchTerm.isEmpty) {
      final suggestions = fileMentions.take(6).toList();
      setFileMentionSuggestions(show: suggestions.isNotEmpty, suggestions: suggestions);
      return;
    }

    final quickResults = quickFilterFileMentions(searchTerm);
    setFileMentionSuggestions(show: quickResults.isNotEmpty, suggestions: quickResults);

    _fileMentionDebounceTimer = Timer(const Duration(milliseconds: 30), () async {
      try {
        final results = await compute(
          filterFileMentionsInBackground,
          FileMentionParams(fileMentions, searchTerm),
        );
        if (querySequence != _fileMentionQuerySequence) return;
        setFileMentionSuggestions(show: results.isNotEmpty, suggestions: results);
      } catch (e) {
        debugPrint('Error filtering file mentions: $e');
        setFileMentionSuggestions(show: false, suggestions: const []);
      }
    });
  }

  void insertFileMention(String filePath) {
    final text = fileMentionTextController.text;
    final selection = fileMentionTextController.selection;
    final cursorPos = selection.isValid && selection.baseOffset >= 0
        ? selection.baseOffset.clamp(0, text.length)
        : text.length;

    final atIndex =
        cursorPos > 0 ? text.lastIndexOf('@', cursorPos - 1) : -1;
    if (atIndex == -1) return;

    // Replace the whole mention word (from @ until next whitespace or end),
    // not just up to cursor — otherwise editing mid-word leaves trailing chars.
    int wordEnd = cursorPos;
    while (wordEnd < text.length) {
      final ch = text[wordEnd];
      if (ch == ' ' || ch == '\n' || ch == '\t') break;
      wordEnd++;
    }

    final beforeAt = text.substring(0, atIndex);
    final afterWord = text.substring(wordEnd);
    final needsSpace = afterWord.isEmpty ||
        (afterWord[0] != ' ' && afterWord[0] != '\n' && afterWord[0] != '\t');
    final mention = '@$filePath';
    final separator = needsSpace ? ' ' : '';
    final newText = '$beforeAt$mention$separator$afterWord';
    final newCursorPos = beforeAt.length + mention.length + separator.length;

    fileMentionTextController.text = newText;
    fileMentionTextController.selection = TextSelection.fromPosition(
      TextPosition(offset: newCursorPos),
    );
    setFileMentionSuggestions(show: false, suggestions: const []);
  }

  void disposeFileMentionMixin() {
    _fileMentionDebounceTimer?.cancel();
    _fileMentionDebounceTimer = null;
  }
}
