// Pure extension → (IconData, brand color) lookup for the Files tab tree.
// Brand glyphs come from font_awesome_flutter where available so that
// Python / JS / Rust / Vue etc. read with their own logo. Languages without
// a FontAwesome brand glyph (Dart, TypeScript, Kotlin, C, …) fall back to
// `Icons.code` tinted with their brand color so they still differ from a
// neutral text file.
// Colors are sampled from material-icon-theme via paseo's port (see
// ~/playground/paseo/packages/app/src/components/material-file-icons.ts).
// See `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers.

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class FileIcon {
  const FileIcon(this.icon, [this.color]);
  final IconData icon;
  // Null = caller should fall back to the theme's secondaryText so neutral
  // entries (folders, generic files) stay theme-tied.
  final Color? color;
}

// Brand palette — copied verbatim from the material-icon-theme SVGs in
// paseo so the colors line up with what users see in VS Code / GitHub.
const _cBlue = Color(0xFF0288D1);
const _cAccentBlue = Color(0xFF42A5F5);
const _cTealCyan = Color(0xFF00ACC1);
const _cTeal = Color(0xFF26A69A);
const _cYellow = Color(0xFFFFCA28);
const _cAmber = Color(0xFFF9A825);
const _cRed = Color(0xFFF44336);
const _cRedAlt = Color(0xFFFF5252);
const _cOrange = Color(0xFFFF7043);
const _cOrangeHtml = Color(0xFFE65100);
const _cPurpleCss = Color(0xFF7E57C2);
const _cPurpleKotlin = Color(0xFF7C4DFF);
const _cPurpleElixir = Color(0xFF9575CD);
const _cPink = Color(0xFFEC407A);
const _cGreen = Color(0xFF8BC34A);
const _cGreenVue = Color(0xFF41B883);
const _cSwiftOrange = Color(0xFFFF6E40);
const _cSvelte = Color(0xFFFF5722);
const _cDartLight = Color(0xFF4FC3F7);
const _cLuaBlue = Color(0xFF42A5F5);
const _cRBlue = Color(0xFF1976D2);
const _cPhpBlue = Color(0xFF1E88E5);
const _cLockYellow = Color(0xFFFFD54F);

// ext → (IconData, Color) maps. Icons stay in the Material family so the row
// height + alignment doesn't shift between language brands; the color is what
// actually carries the type signal.
const _imageExts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'};
const _markdownExts = {'.md', '.markdown', '.mdx'};
const _archiveExts = {'.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar'};
const _docExts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'};
const _lockExts = {'.lock'};

// Per-extension code icon + brand color. Each entry overrides `Icons.code`
// with a more specific glyph where one exists. Anything missing falls back
// to `Icons.code` so unknown code files still read as "a code file".
final Map<String, FileIcon> _codeIcon = {
  '.dart': const FileIcon(Icons.code, _cDartLight),
  '.py': FileIcon(FontAwesomeIcons.python, _cBlue),
  '.js': FileIcon(FontAwesomeIcons.js, _cYellow),
  '.jsx': FileIcon(FontAwesomeIcons.react, _cTealCyan),
  '.ts': const FileIcon(Icons.code, _cBlue),
  '.tsx': FileIcon(FontAwesomeIcons.react, _cBlue),
  '.go': FileIcon(FontAwesomeIcons.golang, _cTealCyan),
  '.rs': FileIcon(FontAwesomeIcons.rust, _cOrange),
  '.rb': FileIcon(FontAwesomeIcons.gem, _cRed),
  '.java': FileIcon(FontAwesomeIcons.java, _cRed),
  '.kt': const FileIcon(Icons.code, _cPurpleKotlin),
  '.swift': FileIcon(FontAwesomeIcons.swift, _cSwiftOrange),
  '.c': const FileIcon(Icons.code, _cBlue),
  '.cc': const FileIcon(Icons.code, _cBlue),
  '.cpp': const FileIcon(Icons.code, _cBlue),
  '.h': const FileIcon(Icons.code, _cBlue),
  '.hpp': const FileIcon(Icons.code, _cBlue),
  '.cs': const FileIcon(Icons.code, _cBlue),
  '.php': FileIcon(FontAwesomeIcons.php, _cPhpBlue),
  '.sh': FileIcon(FontAwesomeIcons.terminal, _cOrange),
  '.zsh': FileIcon(FontAwesomeIcons.terminal, _cOrange),
  '.bash': FileIcon(FontAwesomeIcons.terminal, _cOrange),
  '.lua': const FileIcon(Icons.code, _cLuaBlue),
  '.r': const FileIcon(Icons.code, _cRBlue),
  '.scala': const FileIcon(Icons.code, _cRed),
  '.clj': const FileIcon(Icons.code, _cGreen),
  '.ex': const FileIcon(Icons.code, _cPurpleElixir),
  '.exs': const FileIcon(Icons.code, _cPurpleElixir),
  '.erl': const FileIcon(Icons.code, _cRed),
  '.html': FileIcon(FontAwesomeIcons.html5, _cOrangeHtml),
  '.css': FileIcon(FontAwesomeIcons.css3, _cPurpleCss),
  '.scss': FileIcon(FontAwesomeIcons.sass, _cPink),
  '.sass': FileIcon(FontAwesomeIcons.sass, _cPink),
  '.less': const FileIcon(Icons.code, _cBlue),
  '.vue': FileIcon(FontAwesomeIcons.vuejs, _cGreenVue),
  '.svelte': const FileIcon(Icons.code, _cSvelte),
  '.sql': FileIcon(FontAwesomeIcons.database, _cYellow),
  '.zig': const FileIcon(Icons.code, _cAmber),
  '.hs': const FileIcon(Icons.code, _cRed),
  '.ml': const FileIcon(Icons.code, _cOrange),
  '.nix': const FileIcon(Icons.code, _cRBlue),
  '.gradle': const FileIcon(Icons.code, _cTealCyan),
  '.wasm': const FileIcon(Icons.code, _cPurpleKotlin),
};

const Map<String, Color> _configColor = {
  '.json': _cAmber,
  '.yaml': _cRedAlt,
  '.yml': _cRedAlt,
  '.toml': _cAccentBlue,
  '.ini': _cAccentBlue,
  '.env': _cAccentBlue,
  '.cfg': _cAccentBlue,
  '.conf': _cAccentBlue,
  '.tf': _cPurpleKotlin,
  '.hcl': _cAccentBlue,
};

FileIcon fileIconFor(
  String name, {
  bool isDir = false,
  bool isExpanded = false,
}) {
  if (isDir) {
    return FileIcon(isExpanded ? Icons.folder_open_outlined : Icons.folder_outlined);
  }
  final lower = name.toLowerCase();
  final dot = lower.lastIndexOf('.');
  final ext = dot >= 0 ? lower.substring(dot) : '';
  if (_imageExts.contains(ext)) return const FileIcon(Icons.image_outlined, _cTeal);
  if (ext == '.svg') return const FileIcon(Icons.image_outlined, _cAmber);
  if (_markdownExts.contains(ext)) return const FileIcon(Icons.article_outlined, _cAccentBlue);
  if (_configColor.containsKey(ext)) {
    return FileIcon(Icons.data_object_outlined, _configColor[ext]);
  }
  final codeIcon = _codeIcon[ext];
  if (codeIcon != null) return codeIcon;
  if (ext == '.xml') return const FileIcon(Icons.code, _cGreen);
  if (_lockExts.contains(ext)) return const FileIcon(Icons.lock_outline, _cLockYellow);
  if (_archiveExts.contains(ext)) return const FileIcon(Icons.archive_outlined);
  if (_docExts.contains(ext)) return const FileIcon(Icons.description_outlined, _cAccentBlue);
  return const FileIcon(Icons.insert_drive_file_outlined);
}
