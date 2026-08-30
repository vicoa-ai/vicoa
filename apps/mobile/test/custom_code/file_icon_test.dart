// Spec for `fileIconFor` — extension → (IconData, brand color) lookup for
// the Files tree. Covers `plans/todos/vicoa-app-files-tab.md` §Phase C Helpers.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/file_icon.dart';

void main() {
  test('unknown extension falls back to a generic file icon, no brand color', () {
    final r = fileIconFor('mystery.xyz');
    expect(r.icon, Icons.insert_drive_file_outlined);
    expect(r.color, isNull);
  });

  test('directory uses folder icon, open variant when expanded; no brand color', () {
    expect(fileIconFor('src', isDir: true).icon, Icons.folder_outlined);
    expect(fileIconFor('src', isDir: true).color, isNull);
    expect(fileIconFor('src', isDir: true, isExpanded: true).icon, Icons.folder_open_outlined);
  });

  test('common image extensions get an image icon, teal brand', () {
    for (final n in ['pic.png', 'PHOTO.JPG', 'a.jpeg', 'b.gif', 'c.webp']) {
      final r = fileIconFor(n);
      expect(r.icon, Icons.image_outlined, reason: n);
      expect(r.color, isNotNull, reason: n);
    }
  });

  test('markdown maps to the article icon, blue brand', () {
    final r = fileIconFor('README.md');
    expect(r.icon, Icons.article_outlined);
    expect(r.color, isNotNull);
  });

  test('structured-config files map to a data icon with per-config brand color', () {
    expect(fileIconFor('config.json').icon, Icons.data_object_outlined);
    expect(fileIconFor('pubspec.yaml').icon, Icons.data_object_outlined);
    expect(fileIconFor('pyproject.toml').icon, Icons.data_object_outlined);
    expect(fileIconFor('config.json').color, isNotNull);
  });

  test('code files surface per-language brand glyphs and colors', () {
    // Brand glyphs differ where FontAwesome provides one (Python, Go, Rust),
    // fall back to Icons.code where it doesn't (Dart). Either way, colors
    // differ across languages — the per-type signal must land.
    final py = fileIconFor('a.py');
    final go = fileIconFor('a.go');
    final rs = fileIconFor('a.rs');
    final dart = fileIconFor('a.dart');
    expect(py.icon, isNot(equals(Icons.code)));
    expect(go.icon, isNot(equals(Icons.code)));
    expect(rs.icon, isNot(equals(Icons.code)));
    expect(dart.icon, Icons.code);
    for (final r in [py, go, rs, dart]) {
      expect(r.color, isNotNull);
    }
    expect(py.color, isNot(equals(dart.color)));
    expect(go.color, isNot(equals(dart.color)));
  });

  test('case-insensitive extension lookup', () {
    expect(fileIconFor('Foo.PNG').icon, Icons.image_outlined);
    expect(fileIconFor('FOO.MD').icon, Icons.article_outlined);
  });
}
