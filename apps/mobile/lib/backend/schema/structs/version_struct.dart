// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';

import 'index.dart';
import '/flutter_flow/flutter_flow_util.dart';

class VersionStruct extends BaseStruct {
  VersionStruct({
    String? value,
    bool? shouldUpdate,
    bool? forceUpdate,
  })  : _value = value,
        _shouldUpdate = shouldUpdate,
        _forceUpdate = forceUpdate;

  // "value" field.
  String? _value;
  String get value => _value ?? '';
  set value(String? val) {
    _value = val;
    debugLog();
  }

  bool hasValue() => _value != null;

  // "shouldUpdate" field.
  bool? _shouldUpdate;
  bool get shouldUpdate => _shouldUpdate ?? false;
  set shouldUpdate(bool? val) {
    _shouldUpdate = val;
    debugLog();
  }

  bool hasShouldUpdate() => _shouldUpdate != null;

  // "forceUpdate" field.
  bool? _forceUpdate;
  bool get forceUpdate => _forceUpdate ?? false;
  set forceUpdate(bool? val) {
    _forceUpdate = val;
    debugLog();
  }

  bool hasForceUpdate() => _forceUpdate != null;

  static VersionStruct fromMap(Map<String, dynamic> data) => VersionStruct(
        value: data['value'] as String?,
        shouldUpdate: data['shouldUpdate'] as bool?,
        forceUpdate: data['forceUpdate'] as bool?,
      );

  static VersionStruct? maybeFromMap(dynamic data) =>
      data is Map ? VersionStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'value': _value,
        'shouldUpdate': _shouldUpdate,
        'forceUpdate': _forceUpdate,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'value': serializeParam(
          _value,
          ParamType.String,
        ),
        'shouldUpdate': serializeParam(
          _shouldUpdate,
          ParamType.bool,
        ),
        'forceUpdate': serializeParam(
          _forceUpdate,
          ParamType.bool,
        ),
      }.withoutNulls;

  static VersionStruct fromSerializableMap(Map<String, dynamic> data) =>
      VersionStruct(
        value: deserializeParam(
          data['value'],
          ParamType.String,
          false,
        ),
        shouldUpdate: deserializeParam(
          data['shouldUpdate'],
          ParamType.bool,
          false,
        ),
        forceUpdate: deserializeParam(
          data['forceUpdate'],
          ParamType.bool,
          false,
        ),
      );
  @override
  Map<String, DebugDataField> toDebugSerializableMap() => {
        'value': debugSerializeParam(
          value,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'shouldUpdate': debugSerializeParam(
          shouldUpdate,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'forceUpdate': debugSerializeParam(
          forceUpdate,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
      };

  @override
  String toString() => 'VersionStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is VersionStruct &&
        value == other.value &&
        shouldUpdate == other.shouldUpdate &&
        forceUpdate == other.forceUpdate;
  }

  @override
  int get hashCode =>
      const ListEquality().hash([value, shouldUpdate, forceUpdate]);
}

VersionStruct createVersionStruct({
  String? value,
  bool? shouldUpdate,
  bool? forceUpdate,
}) =>
    VersionStruct(
      value: value,
      shouldUpdate: shouldUpdate,
      forceUpdate: forceUpdate,
    );
