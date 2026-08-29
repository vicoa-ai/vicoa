// State machine for the Files tab. See `plans/todos/vicoa-app-files-tab.md`
// §Phase C Files tab body.
//
// Tests inject a fake list-files callable and an in-memory cache so they
// stay pure Dart — no Flutter widgets, no live Hive.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/actions/files_tab_model.dart';
import 'package:vicoa/custom_code/actions/rpc_files.dart';

class _AsyncGate<T> {
  final _c = Completer<T>();
  Future<T> get future => _c.future;
  void complete(T value) => _c.complete(value);
}

class _FakeCache implements FilesTabCache {
  final Map<String, List<dynamic>> _listings = {};
  final Map<String, Set<String>> _expanded = {};

  @override
  List<dynamic>? getListing({
    required String machineId,
    required String cwd,
    required String path,
  }) =>
      _listings['$machineId|$cwd|$path'];

  @override
  Future<void> putListing({
    required String machineId,
    required String cwd,
    required String path,
    required List<dynamic> entries,
  }) async {
    _listings['$machineId|$cwd|$path'] = entries;
  }

  @override
  Set<String> getExpanded({required String machineId, required String cwd}) =>
      _expanded['$machineId|$cwd'] ?? <String>{};

  @override
  Future<void> putExpanded({
    required String machineId,
    required String cwd,
    required Set<String> expanded,
  }) async {
    _expanded['$machineId|$cwd'] = Set.of(expanded);
  }
}

void main() {
  test('cached listing is exposed immediately and refreshed in background',
      () async {
    final cache = _FakeCache();
    await cache.putListing(
      machineId: 'm',
      cwd: '/proj',
      path: '',
      entries: [{'name': 'stale.md', 'type': 'file', 'size': 1}],
    );

    final completer = _AsyncGate<List<FilesEntry>>();
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: cache,
      listFiles: ({required machineId, required cwd, required path}) =>
          completer.future,
    );

    final init = model.initialize();

    // Stale-while-revalidate: cached entries visible before the network call returns.
    final cached = model.listingFor('');
    expect(cached, isA<ListingLoaded>());
    expect((cached as ListingLoaded).entries[0].name, 'stale.md');

    completer.complete([FilesEntry(name: 'fresh.md', isDir: false, size: 2)]);
    await init;
    final refreshed = model.listingFor('') as ListingLoaded;
    expect(refreshed.entries[0].name, 'fresh.md');
  });

  test('toggleExpanded adds the dir, fires list-files, toggling removes it', () async {
    final calls = <String>[];
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: _FakeCache(),
      listFiles: ({required machineId, required cwd, required path}) async {
        calls.add(path);
        return [];
      },
    );
    await model.initialize();
    calls.clear();

    await model.toggleExpanded('src');
    expect(model.expanded, contains('src'));
    expect(calls, ['src']);

    await model.toggleExpanded('src');
    expect(model.expanded, isNot(contains('src')));
  });

  test('expanded set is persisted across model re-creation', () async {
    final cache = _FakeCache();
    final first = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: cache,
      listFiles: ({required machineId, required cwd, required path}) async => [],
    );
    await first.initialize();
    await first.toggleExpanded('src');

    final reopened = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: cache,
      listFiles: ({required machineId, required cwd, required path}) async => [],
    );
    await reopened.initialize();
    expect(reopened.expanded, contains('src'));
  });

  test('FileOpsException surfaces as ListingError', () async {
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: _FakeCache(),
      listFiles: ({required machineId, required cwd, required path}) async {
        throw FileOpsException('path_not_found');
      },
    );
    await model.initialize();
    final state = model.listingFor('');
    expect(state, isA<ListingError>());
    expect((state as ListingError).code, 'path_not_found');
    // Per-path failures aren't an offline signal.
    expect(model.isMachineOffline, isFalse);
  });

  test('connectivity error with cached listing flips offline flag, keeps entries', () async {
    final cache = _FakeCache();
    await cache.putListing(
      machineId: 'm',
      cwd: '/proj',
      path: '',
      entries: [{'name': 'cached.md', 'type': 'file', 'size': 1}],
    );
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: cache,
      listFiles: ({required machineId, required cwd, required path}) async {
        throw FileOpsException('target_disconnected');
      },
    );
    await model.initialize();
    expect(model.isMachineOffline, isTrue);
    final state = model.listingFor('');
    expect(state, isA<ListingLoaded>());
    expect((state as ListingLoaded).entries[0].name, 'cached.md');
  });

  test('cold-start connectivity error sets offline + ListingError', () async {
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: _FakeCache(),
      listFiles: ({required machineId, required cwd, required path}) async {
        throw FileOpsException('not_connected');
      },
    );
    await model.initialize();
    expect(model.isMachineOffline, isTrue);
    expect(model.listingFor(''), isA<ListingError>());
  });

  test('successful fetch clears the offline flag', () async {
    var shouldFail = true;
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: _FakeCache(),
      listFiles: ({required machineId, required cwd, required path}) async {
        if (shouldFail) throw FileOpsException('timeout');
        return [FilesEntry(name: 'back.md', isDir: false, size: 1)];
      },
    );
    await model.initialize();
    expect(model.isMachineOffline, isTrue);
    shouldFail = false;
    await model.refresh();
    expect(model.isMachineOffline, isFalse);
    expect(model.listingFor(''), isA<ListingLoaded>());
  });

  test('refresh re-fires list-files for the root and every expanded dir', () async {
    var version = 0;
    final calls = <String>[];
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: _FakeCache(),
      listFiles: ({required machineId, required cwd, required path}) async {
        calls.add(path);
        return [FilesEntry(name: 'v$version-in-$path', isDir: false, size: 1)];
      },
    );
    await model.initialize();
    await model.toggleExpanded('src');
    await model.toggleExpanded('docs');
    calls.clear();
    version = 1;

    await model.refresh();
    expect(calls.toSet(), {'', 'src', 'docs'});
    expect(
      (model.listingFor('') as ListingLoaded).entries[0].name,
      'v1-in-',
    );
    expect(
      (model.listingFor('src') as ListingLoaded).entries[0].name,
      'v1-in-src',
    );
  });

  test('initialize loads the root listing and exposes it as loaded', () async {
    final calls = <List<String>>[];
    final model = FilesTabModel(
      machineId: 'm',
      cwd: '/proj',
      cache: _FakeCache(),
      listFiles: ({required machineId, required cwd, required path}) async {
        calls.add([machineId, cwd, path]);
        return [
          FilesEntry(name: 'src', isDir: true),
          FilesEntry(name: 'readme.md', isDir: false, size: 10),
        ];
      },
    );

    await model.initialize();

    expect(calls, [['m', '/proj', '']]);
    final root = model.listingFor('');
    expect(root, isA<ListingLoaded>());
    expect((root as ListingLoaded).entries.map((e) => e.name), ['src', 'readme.md']);
  });
}
