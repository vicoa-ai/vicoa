import 'dart:io';
import 'dart:developer' as devtools;
import 'dart:math' as math;
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '/main.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import 'flutter_flow_util.dart';
import 'package:collection/collection.dart';
import 'package:easy_debounce/easy_debounce.dart';
import 'package:debug_panel_proto/debug_panel_proto.dart';

import '/auth/supabase_auth/auth_util.dart';

bool kEnableDebugLogging = true;

/// A inherited widget that provides the root model of the current page, as well
/// as a callback to link the current model to its parent model for debug logging
/// purpose.
class DebugFlutterFlowModelContext extends InheritedWidget {
  const DebugFlutterFlowModelContext({
    super.key,
    required this.rootModel,
    this.parentModelCallback,
    required super.child,
  });

  final FlutterFlowModel rootModel;
  final Function(FlutterFlowModel)? parentModelCallback;

  static DebugFlutterFlowModelContext? maybeOf(BuildContext context) {
    return context
        .dependOnInheritedWidgetOfExactType<DebugFlutterFlowModelContext>();
  }

  static DebugFlutterFlowModelContext of(BuildContext context) {
    final DebugFlutterFlowModelContext? result = maybeOf(context);
    assert(result != null, 'No DebugFlutterFlowModelContext found in context');
    return result!;
  }

  @override
  bool updateShouldNotify(DebugFlutterFlowModelContext oldWidget) =>
      rootModel != oldWidget.rootModel ||
      parentModelCallback != oldWidget.parentModelCallback;
}

/// replace ModalRoute.of(context), needed because of the issue in Flutter 3.19.x
/// see discussion https://github.com/flutter/flutter/issues/146132 and
/// https://github.com/flutter/flutter/pull/145389
class DebugModalRoute {
  static ModalRoute<dynamic>? of(BuildContext context) {
    ModalRoute<dynamic>? route;
    context.visitAncestorElements((element) {
      if (element.widget.runtimeType.toString() == '_ModalScopeStatus') {
        dynamic widget = element.widget;
        route = widget.route as ModalRoute;
        return false;
      }
      return true;
    });
    return route;
  }
}

extension SerializationExtensions on GeneratedMessage {
  String get serializedBufferString => base64.encode(writeToBuffer());
}

void debugLogging(String info) {
  devtools.postEvent(
    'ext.flutterflow_debug_panel.updateDebugData',
    {'data': info},
  );
}

/// Debounce the logging call for different channel (tag) every 500ms
void debouncedDebugLogging(
  String tag,
  Map<String, dynamic> Function() debugInfo,
) {
  if (!kEnableDebugLogging) {
    return;
  }

  try {
    EasyDebounce.debounce(
      tag,
      const Duration(milliseconds: 1000),
      () => debugLogging(json.encode(debugInfo())),
    );
  } catch (_) {}
}

void debugLogGlobalProperty(
  BuildContext context, {
  String? locale,
  String? routePath,
  List<String>? routeStack,
}) async {
  debouncedDebugLogging(
      '405ebf2ff50c295c675b5802889ea941f081fd51',
      () => {
            'event_type': 'variable',
            'data_source': 'globalProperty',
            'data': GlobalPropertyDebugData(
                    values: context.mounted
                        ? {
                            'screenWidth': debugSerializeParam(
                              MediaQuery.sizeOf(context).width,
                              ParamType.double,
                              nullable: false,
                            ),
                            'screenHeight': debugSerializeParam(
                              MediaQuery.sizeOf(context).height,
                              ParamType.double,
                              nullable: false,
                            ),
                            'platform': debugSerializeParam(
                              kIsWeb ? 'web' : Platform.operatingSystem,
                              ParamType.String,
                              nullable: false,
                            ),
                            'themeMode': debugSerializeParam(
                              FlutterFlowTheme.themeMode.name,
                              ParamType.String,
                              nullable: false,
                            ),
                            'currentTime': debugSerializeParam(
                              getCurrentTimestamp,
                              ParamType.DateTime,
                              nullable: false,
                            ),
                            'locale': debugSerializeParam(
                              locale ?? MyApp.of(context).locale?.toString(),
                              ParamType.String,
                              nullable: true,
                            ),
                            'route': debugSerializeParam(
                              (routePath ?? MyApp.of(context).getRoute())
                                  .toString(),
                              ParamType.String,
                              nullable: false,
                              link: debugRouteLinkMap[
                                  (routePath ?? MyApp.of(context).getRoute())
                                      .toString()],
                            ),
                            'routeStack': DebugDataField(
                              type: DebugDataField_ParamType.STRING,
                              listValue: ListDebugDataField(
                                values: (routeStack ??
                                        MyApp.of(context).getRouteStack())
                                    .map((e) => DebugDataField(
                                          type: DebugDataField_ParamType.STRING,
                                          serializedValue: e,
                                          link: debugRouteLinkMap[e],
                                          nullable: false,
                                        ))
                                    .toList(),
                              ),
                              nullable: false,
                            ),
                          }
                        : {})
                .serializedBufferString
          });
}

void debugLogAppState(FFAppState appState) {
  debouncedDebugLogging(
      'fbcc19a787981a30d86b10103c2f3951604b2ae6',
      () => {
            'event_type': 'variable',
            'data_source': 'appState',
            'data': AppStateDebugData(values: appState.toDebugSerializableMap())
                .serializedBufferString,
          });
}

void debugLogAuthenticatedUser() {
  debouncedDebugLogging(
      'c0186d2c21d5d9300ee148206df9fbd1850b8d41',
      () => {
            'event_type': 'variable',
            'data_source': 'authenticatedUser',
            'data': AuthenticatedUserDebugData(values: {
              'isUserLoggedIn': debugSerializeParam(
                loggedIn,
                ParamType.bool,
                nullable: false,
              ),
              'currentUserEmail': debugSerializeParam(
                currentUserEmail,
                ParamType.String,
                nullable: false,
              ),
              'currentUserUid': debugSerializeParam(
                currentUserUid,
                ParamType.String,
                nullable: false,
              ),
              'currentUserDisplayName': debugSerializeParam(
                currentUserDisplayName,
                ParamType.String,
                nullable: false,
              ),
              'currentUserPhoto': debugSerializeParam(
                currentUserPhoto,
                ParamType.String,
                nullable: false,
              ),
              'currentPhoneNumber': debugSerializeParam(
                currentPhoneNumber,
                ParamType.String,
                nullable: false,
              ),
              'currentJwtToken': debugSerializeParam(
                currentJwtToken,
                ParamType.String,
                nullable: false,
              ),
              'currentUserEmailVerified': debugSerializeParam(
                currentUserEmailVerified,
                ParamType.bool,
                nullable: false,
              ),
            }).serializedBufferString,
          });
}

void debugLogWidgetClass(FlutterFlowModel widgetClassModel) {
  WidgetsBinding.instance.addPostFrameCallback(
    (_) {
      if (widgetClassModel.isRouteVisible) {
        debouncedDebugLogging(
            '508f3c74205c87928b71f49040062e732f9c20b0',
            () => {
                  'event_type': 'variable',
                  'data_source': 'widgetClass',
                  'data': widgetClassModel.rootModel
                      .toWidgetClassDebugData()
                      .serializedBufferString,
                });
      }
    },
  );
}

mixin DebugLoggable {
  Function()? logger;
  void debugLog() {
    logger?.call();
  }
}

class LoggableList<E> extends DelegatingList<E> with DebugLoggable {
  LoggableList(super.base);

  @override
  void operator []=(int index, E value) {
    super[index] = value;
    debugLog();
  }

  @override
  void add(E value) {
    super.add(value);
    debugLog();
  }

  @override
  void addAll(Iterable<E> iterable) {
    super.addAll(iterable);
    debugLog();
  }

  @override
  void clear() {
    super.clear();
    debugLog();
  }

  @override
  void fillRange(int start, int end, [E? fillValue]) {
    super.fillRange(start, end, fillValue);
    debugLog();
  }

  @override
  set first(E value) {
    if (isEmpty) throw RangeError.index(0, this);
    this[0] = value;
    debugLog();
  }

  @override
  void insert(int index, E element) {
    super.insert(index, element);
    debugLog();
  }

  @override
  void insertAll(int index, Iterable<E> iterable) {
    super.insertAll(index, iterable);
    debugLog();
  }

  @override
  set last(E value) {
    if (isEmpty) throw RangeError.index(0, this);
    this[length - 1] = value;
    debugLog();
  }

  @override
  bool remove(Object? value) {
    var rst = super.remove(value);
    debugLog();
    return rst;
  }

  @override
  E removeAt(int index) {
    var rst = super.removeAt(index);
    debugLog();
    return rst;
  }

  @override
  E removeLast() {
    var rst = super.removeLast();
    debugLog();
    return rst;
  }

  @override
  void removeRange(int start, int end) {
    super.removeRange(start, end);
    debugLog();
  }

  @override
  void removeWhere(bool Function(E) test) {
    super.removeWhere(test);
    debugLog();
  }

  @override
  void replaceRange(int start, int end, Iterable<E> iterable) {
    super.replaceRange(start, end, iterable);
    debugLog();
  }

  @override
  void retainWhere(bool Function(E) test) {
    super.retainWhere(test);
    debugLog();
  }

  @override
  void setAll(int index, Iterable<E> iterable) {
    super.setAll(index, iterable);
    debugLog();
  }

  @override
  void setRange(int start, int end, Iterable<E> iterable, [int skipCount = 0]) {
    super.setRange(start, end, iterable, skipCount);
    debugLog();
  }

  @override
  void shuffle([math.Random? random]) {
    super.shuffle(random);
    debugLog();
  }

  @override
  void sort([int Function(E, E)? compare]) {
    super.sort(compare);
    debugLog();
  }
}

class LoggableMap<K, V> extends DelegatingMap<K, V> with DebugLoggable {
  LoggableMap(super.base);

  @override
  void operator []=(K key, V value) {
    super[key] = value;
    debugLog();
  }

  @override
  void addAll(Map<K, V> other) {
    super.addAll(other);
    debugLog();
  }

  @override
  void addEntries(Iterable<MapEntry<K, V>> entries) {
    super.addEntries(entries);
    debugLog();
  }

  @override
  void clear() {
    super.clear();
    debugLog();
  }

  @override
  void forEach(void Function(K, V) f) {
    super.forEach(f);
    debugLog();
  }

  @override
  V putIfAbsent(K key, V Function() ifAbsent) {
    var rst = super.putIfAbsent(key, ifAbsent);
    debugLog();
    return rst;
  }

  @override
  V? remove(Object? key) {
    var rst = super.remove(key);
    debugLog();
    return rst;
  }

  @override
  void removeWhere(bool Function(K, V) test) {
    super.removeWhere(test);
    debugLog();
  }

  @override
  V update(K key, V Function(V) update, {V Function()? ifAbsent}) {
    var rst = super.update(key, update, ifAbsent: ifAbsent);
    debugLog();
    return rst;
  }

  @override
  void updateAll(V Function(K, V) update) {
    var rst = super.updateAll(update);
    debugLog();
    return rst;
  }
}
