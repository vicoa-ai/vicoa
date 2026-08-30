// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';

import 'index.dart';
import '/flutter_flow/flutter_flow_util.dart';

class LocalDeletionStruct extends BaseStruct {
  LocalDeletionStruct({
    String? id,
    String? type,
    DateTime? deletedAt,
  })  : _id = id,
        _type = type,
        _deletedAt = deletedAt;

  // "id" field.
  String? _id;
  String get id => _id ?? '';
  set id(String? val) {
    _id = val;
    debugLog();
  }

  bool hasId() => _id != null;

  // "type" field.
  String? _type;
  String get type => _type ?? '';
  set type(String? val) {
    _type = val;
    debugLog();
  }

  bool hasType() => _type != null;

  // "deletedAt" field.
  DateTime? _deletedAt;
  DateTime? get deletedAt => _deletedAt;
  set deletedAt(DateTime? val) {
    _deletedAt = val;
    debugLog();
  }

  bool hasDeletedAt() => _deletedAt != null;

  static LocalDeletionStruct fromMap(Map<String, dynamic> data) =>
      LocalDeletionStruct(
        id: data['id'] as String?,
        type: data['type'] as String?,
        deletedAt: data['deletedAt'] as DateTime?,
      );

  static LocalDeletionStruct? maybeFromMap(dynamic data) => data is Map
      ? LocalDeletionStruct.fromMap(data.cast<String, dynamic>())
      : null;

  Map<String, dynamic> toMap() => {
        'id': _id,
        'type': _type,
        'deletedAt': _deletedAt,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'id': serializeParam(
          _id,
          ParamType.String,
        ),
        'type': serializeParam(
          _type,
          ParamType.String,
        ),
        'deletedAt': serializeParam(
          _deletedAt,
          ParamType.DateTime,
        ),
      }.withoutNulls;

  static LocalDeletionStruct fromSerializableMap(Map<String, dynamic> data) =>
      LocalDeletionStruct(
        id: deserializeParam(
          data['id'],
          ParamType.String,
          false,
        ),
        type: deserializeParam(
          data['type'],
          ParamType.String,
          false,
        ),
        deletedAt: deserializeParam(
          data['deletedAt'],
          ParamType.DateTime,
          false,
        ),
      );
  @override
  Map<String, DebugDataField> toDebugSerializableMap() => {
        'id': debugSerializeParam(
          id,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'type': debugSerializeParam(
          type,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'deletedAt': debugSerializeParam(
          _deletedAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
      };

  @override
  String toString() => 'LocalDeletionStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is LocalDeletionStruct &&
        id == other.id &&
        type == other.type &&
        deletedAt == other.deletedAt;
  }

  @override
  int get hashCode => const ListEquality().hash([id, type, deletedAt]);
}

LocalDeletionStruct createLocalDeletionStruct({
  String? id,
  String? type,
  DateTime? deletedAt,
}) =>
    LocalDeletionStruct(
      id: id,
      type: type,
      deletedAt: deletedAt,
    );
