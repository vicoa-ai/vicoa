import 'dart:async';

import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/custom_code/actions/vicoa_api_request.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'search_widget.dart';

enum SearchStatus { idle, loading, loaded, error }

enum SearchErrorKind { none, failed, timeout }

/// Owns the search page's data + async lifecycle so the widget stays a thin
/// view: a debounced query, a request token that drops stale responses (Dart
/// has no AbortController), grouped results, and a client-side fallback for
/// backends that predate `/api/v1/search`.
class SearchModel extends FlutterFlowModel<SearchWidget> {
  /// Recently-loaded sessions handed in from Home. Backs the empty-query
  /// "Recent" list and the 404 fallback filter, so search feels instant and
  /// still works session-only when the endpoint is missing.
  List<dynamic> recentSessions = const [];

  final TextEditingController queryController = TextEditingController();
  final FocusNode queryFocus = FocusNode();

  String query = '';
  SearchStatus status = SearchStatus.idle;
  SearchErrorKind errorKind = SearchErrorKind.none;

  List<dynamic> sessions = const [];
  List<dynamic> tasks = const [];
  List<dynamic> automations = const [];

  /// Flipped on the first 404: the endpoint doesn't exist here, so we degrade
  /// to filtering the loaded session list instead of hitting the server again.
  bool serverUnavailable = false;

  Timer? _debounce;
  int _requestToken = 0;

  VoidCallback? _notify;
  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  static const int _debounceMs = 250;
  static const int _localFallbackLimit = 20;

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    _debounce?.cancel();
    queryController.dispose();
    queryFocus.dispose();
  }

  bool get hasQuery => query.trim().isNotEmpty;

  bool get hasNoResults =>
      sessions.isEmpty && tasks.isEmpty && automations.isEmpty;

  void onQueryChanged(String value) {
    query = value;
    _debounce?.cancel();
    final term = value.trim();

    if (term.isEmpty) {
      _requestToken++; // cancel any in-flight response
      sessions = const [];
      tasks = const [];
      automations = const [];
      status = SearchStatus.idle;
      errorKind = SearchErrorKind.none;
      _bump();
      return;
    }

    if (serverUnavailable) {
      _runLocalFallback(term);
      _bump();
      return;
    }

    status = SearchStatus.loading;
    errorKind = SearchErrorKind.none;
    _bump();
    _debounce =
        Timer(const Duration(milliseconds: _debounceMs), () => _runSearch(term));
  }

  void clear() => onQueryChanged('');

  Future<void> _runSearch(String term) async {
    final token = ++_requestToken;
    try {
      final result = await actions.apiSearchWorkspace(term);
      if (token != _requestToken) return; // superseded by a newer keystroke
      sessions = (result['sessions'] as List?) ?? const [];
      tasks = (result['tasks'] as List?) ?? const [];
      automations = (result['automations'] as List?) ?? const [];
      status = SearchStatus.loaded;
      errorKind = SearchErrorKind.none;
    } on ApiException catch (e) {
      if (token != _requestToken) return;
      if (e.statusCode == 404) {
        serverUnavailable = true;
        _runLocalFallback(term);
      } else if (e.statusCode == 503) {
        status = SearchStatus.error;
        errorKind = SearchErrorKind.timeout;
      } else {
        status = SearchStatus.error;
        errorKind = SearchErrorKind.failed;
      }
    } catch (e) {
      if (token != _requestToken) return;
      debugPrint('Workspace search failed: $e');
      status = SearchStatus.error;
      errorKind = SearchErrorKind.failed;
    } finally {
      if (token == _requestToken) _bump();
    }
  }

  void _runLocalFallback(String term) {
    final q = term.toLowerCase();
    sessions = recentSessions.where((s) {
      if (s is! Map) return false;
      final name = s['name']?.toString().toLowerCase() ?? '';
      final message = s['latest_message']?.toString().toLowerCase() ?? '';
      final project = s['project']?.toString().toLowerCase() ?? '';
      return name.contains(q) || message.contains(q) || project.contains(q);
    }).take(_localFallbackLimit).toList();
    tasks = const [];
    automations = const [];
    status = SearchStatus.loaded;
    errorKind = SearchErrorKind.none;
  }
}
