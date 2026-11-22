// Swiping between the images of a folder in the file viewer
// (`file_viewer_widget.dart`): only images take part, the header follows the
// page, and a zoomed-in image pans instead of paging.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:hive/hive.dart';
import 'package:vicoa/custom_code/actions/files_cache.dart';
import 'package:vicoa/l10n/app_localizations.dart';
import 'package:vicoa/pages/files_screen/file_viewer/file_viewer_widget.dart';

// A 1x1 transparent PNG.
const _png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

const _folder = [
  {'name': 'sub', 'type': 'dir'},
  {'name': 'a.png', 'type': 'file'},
  {'name': 'b.ts', 'type': 'file'},
  {'name': 'c.png', 'type': 'file'},
  {'name': 'notes.md', 'type': 'file'},
  {'name': 'd.jpg', 'type': 'file'},
];

void main() {
  late Directory dir;
  late FilesCache cache;
  late List<String> calls;

  Future<Map<String, dynamic>> send(String machineId, String method, Map<String, dynamic> params) async {
    final path = params['path'] as String;
    calls.add('$method $path');
    if (method == 'list-files') return {'entries': _folder};
    if (path.endsWith('.png') || path.endsWith('.jpg')) {
      return {'content': _png, 'encoding': 'base64', 'is_binary': true, 'size': base64Decode(_png).length, 'truncated': false};
    }
    return {'content': 'const x = 1;', 'encoding': 'utf-8', 'is_binary': false, 'size': 12, 'truncated': false};
  }

  Future<void> pumpViewer(WidgetTester tester, String path) async {
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: FileViewerWidget(machineId: 'm', cwd: '/p', path: path, name: path.split('/').last, rpc: (send: send, connected: () => true)),
    ));
    for (var i = 0; i < 5; i++) {
      await tester.pump();
    }
  }

  Future<void> swipe(WidgetTester tester, double dx) async {
    await tester.drag(find.byType(PageView), Offset(dx, 0));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
  }

  void zoom(WidgetTester tester, double scale) {
    tester.widget<InteractiveViewer>(find.byType(InteractiveViewer)).transformationController!.value = Matrix4.diagonal3Values(scale, scale, 1);
  }

  setUpAll(() {
    GoogleFonts.config.allowRuntimeFetching = false;
  });

  setUp(() async {
    calls = [];
    dir = await Directory.systemTemp.createTemp('file_viewer_gallery_test_');
    Hive.init(dir.path);
    // In memory: a widget test's fake clock never lets a disk write finish,
    // and the cache writes what the viewer shows.
    await Hive.openBox<String>('files_cache_v1', bytes: Uint8List(0));
    cache = await FilesCache.open();
    await cache.putListing(machineId: 'm', cwd: '/p', path: 'shots', entries: _folder);
  });

  tearDown(() async {
    await cache.close();
    await dir.delete(recursive: true);
  });

  testWidgets('swipes through the images of the folder only, header following', (tester) async {
    await pumpViewer(tester, 'shots/a.png');
    expect(find.byType(PageView), findsOneWidget);
    expect(find.text('a.png'), findsOneWidget);
    expect(find.text('shots · 1 / 3'), findsOneWidget);
    // The folder came from the cache; only the image itself was fetched.
    expect(calls.where((c) => c.startsWith('list-files')), isEmpty);

    await swipe(tester, -500);
    expect(find.text('c.png'), findsOneWidget);
    expect(find.text('shots · 2 / 3'), findsOneWidget);

    await swipe(tester, -500);
    expect(find.text('d.jpg'), findsOneWidget);
    expect(find.text('shots · 3 / 3'), findsOneWidget);

    // Past the last image there is nothing more.
    await swipe(tester, -500);
    expect(find.text('d.jpg'), findsOneWidget);

    await swipe(tester, 500);
    expect(find.text('c.png'), findsOneWidget);
    // Never anything but images.
    expect(calls.where((c) => c.contains('b.ts') || c.contains('notes.md')), isEmpty);
  });

  testWidgets('a zoomed-in image does not page until zoomed back out', (tester) async {
    await pumpViewer(tester, 'shots/a.png');
    zoom(tester, 2);
    await tester.pump();
    await swipe(tester, -500);
    expect(find.text('a.png'), findsOneWidget);

    zoom(tester, 1);
    await tester.pump();
    await swipe(tester, -500);
    expect(find.text('c.png'), findsOneWidget);
  });

  for (final (style, leftStep) in [('both fingers moving', -10.0), ('one finger held still', 0.0)]) {
    testWidgets('a pinch zooms the image rather than turning the page ($style)', (tester) async {
      await pumpViewer(tester, 'shots/a.png');
      final center = tester.getCenter(find.byType(PageView));
      final left = await tester.startGesture(center - const Offset(20, 0), pointer: 1);
      final right = await tester.startGesture(center + const Offset(20, 0), pointer: 2);
      await tester.pump();
      for (var i = 0; i < 10; i++) {
        await left.moveBy(Offset(leftStep, 0));
        await right.moveBy(Offset(20 + leftStep, 0));
        await tester.pump();
      }
      await left.up();
      await right.up();
      await tester.pump(const Duration(milliseconds: 600));
      final transform = tester.widget<InteractiveViewer>(find.byType(InteractiveViewer)).transformationController!.value;
      expect(transform.getMaxScaleOnAxis(), greaterThan(1.5));
      expect(find.text('a.png'), findsOneWidget);
    });
  }

  testWidgets('a text file opens on its own, with no folder lookup', (tester) async {
    await pumpViewer(tester, 'shots/b.ts');
    expect(find.byType(PageView), findsNothing);
    expect(find.text('b.ts'), findsOneWidget);
    expect(find.text('shots'), findsOneWidget);
    expect(calls, ['read-file shots/b.ts']);
  });
}
