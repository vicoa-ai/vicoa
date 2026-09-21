// Pure helpers behind the edited-file chips on a collapsed tool run
// (`widgets/tool_use_group.dart`) and the tappable path on an expanded edit
// row: which tools count as a file edit, an edit's `+N -M` stat, and whether a
// path shown in a tool row is one the file viewer can open. Mirrors the web's
// `tool-use-parsing.ts` / `classifyWorkspacePath` for the Flutter chat.

/// Whether [name] is a file-editing tool — Edit / Write / MultiEdit, or the
/// Codex patch card's "Edited". Case- and separator-insensitive.
bool isFileEditToolName(String name) {
  final n = name.toLowerCase().replaceAll(RegExp(r'[^a-z]'), '');
  return n == 'edit' || n == 'edited' || n == 'write' || n == 'multiedit';
}

/// A `+N -M` line count.
class DiffStat {
  const DiffStat(this.additions, this.deletions);

  final int additions;
  final int deletions;

  DiffStat operator +(DiffStat other) =>
      DiffStat(additions + other.additions, deletions + other.deletions);

  @override
  String toString() => '+$additions -$deletions';

  @override
  bool operator ==(Object other) =>
      other is DiffStat &&
      other.additions == additions &&
      other.deletions == deletions;

  @override
  int get hashCode => Object.hash(additions, deletions);
}

final RegExp _reportedStat = RegExp(r'^\+(\d+)\s+-(\d+)$');

/// Parses a stat an agent reported on the tool line (`+3 -1`), or null.
DiffStat? parseDiffStat(String? stat) {
  if (stat == null) return null;
  final m = _reportedStat.firstMatch(stat.trim());
  if (m == null) return null;
  return DiffStat(int.parse(m.group(1)!), int.parse(m.group(2)!));
}

/// Derives a stat from the fenced diff in a tool message's body — `+`/`-`
/// lines inside a fence, excluding the `+++`/`---` file headers. Null when
/// there is no fence or nothing inside it changed. Claude's Edit/Write cards
/// carry their diff this way and report no stat on the tool line.
DiffStat? diffStatFromContent(String content) {
  if (!content.contains('```')) return null;
  var additions = 0;
  var deletions = 0;
  var inFence = false;
  for (final line in content.split('\n')) {
    if (line.trimLeft().startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (!inFence) continue;
    if (line.startsWith('+') && !line.startsWith('+++')) {
      additions++;
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      deletions++;
    }
  }
  if (additions == 0 && deletions == 0) return null;
  return DiffStat(additions, deletions);
}

final RegExp _driveRooted = RegExp(r'^[A-Za-z]:[\\/]');

/// The path the file viewer can open for a path as shown in a tool row, or
/// null when there is none.
///
/// Tool content reaches the chat with the project root already stripped
/// (`filterProjectRootFromContent`), so a path that is still rooted — `/…`,
/// `~/…`, `C:\…` — lies outside the project, or the root is unknown; the
/// daemon's `read-file` would refuse it either way. A leading `./` is dropped,
/// `.` / `..` segments fold, and a path that climbs out of the project is
/// outside too. The tool path is literal: no percent-decoding, no `:line`.
String? workspaceRelativePath(String path) {
  var p = path.trim();
  if (p.isEmpty) return null;
  if (p.startsWith('/') ||
      p.startsWith('~') ||
      p.startsWith('\\') ||
      _driveRooted.hasMatch(p)) {
    return null;
  }
  p = p.replaceAll('\\', '/');
  final out = <String>[];
  for (final seg in p.split('/')) {
    if (seg.isEmpty || seg == '.') continue;
    if (seg == '..') {
      if (out.isEmpty) return null;
      out.removeLast();
      continue;
    }
    out.add(seg);
  }
  if (out.isEmpty) return null;
  return out.join('/');
}
