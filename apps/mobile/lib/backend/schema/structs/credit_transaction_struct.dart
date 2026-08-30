// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';

import 'index.dart';
import '/flutter_flow/flutter_flow_util.dart';

class CreditTransactionStruct extends BaseStruct {
  CreditTransactionStruct({
    String? name,
    String? type,
    int? amount,
    DateTime? createdAt,
  })  : _name = name,
        _type = type,
        _amount = amount,
        _createdAt = createdAt;

  // "name" field.
  String? _name;
  String get name => _name ?? '';
  set name(String? val) {
    _name = val;
    debugLog();
  }

  bool hasName() => _name != null;

  // "type" field.
  String? _type;
  String get type => _type ?? '';
  set type(String? val) {
    _type = val;
    debugLog();
  }

  bool hasType() => _type != null;

  // "amount" field.
  int? _amount;
  int get amount => _amount ?? 0;
  set amount(int? val) {
    _amount = val;
    debugLog();
  }

  void incrementAmount(int amount) => amount = amount + amount;

  bool hasAmount() => _amount != null;

  // "createdAt" field.
  DateTime? _createdAt;
  DateTime? get createdAt => _createdAt;
  set createdAt(DateTime? val) {
    _createdAt = val;
    debugLog();
  }

  bool hasCreatedAt() => _createdAt != null;

  static CreditTransactionStruct fromMap(Map<String, dynamic> data) =>
      CreditTransactionStruct(
        name: data['name'] as String?,
        type: data['type'] as String?,
        amount: castToType<int>(data['amount']),
        createdAt: data['createdAt'] as DateTime?,
      );

  static CreditTransactionStruct? maybeFromMap(dynamic data) => data is Map
      ? CreditTransactionStruct.fromMap(data.cast<String, dynamic>())
      : null;

  Map<String, dynamic> toMap() => {
        'name': _name,
        'type': _type,
        'amount': _amount,
        'createdAt': _createdAt,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'name': serializeParam(
          _name,
          ParamType.String,
        ),
        'type': serializeParam(
          _type,
          ParamType.String,
        ),
        'amount': serializeParam(
          _amount,
          ParamType.int,
        ),
        'createdAt': serializeParam(
          _createdAt,
          ParamType.DateTime,
        ),
      }.withoutNulls;

  static CreditTransactionStruct fromSerializableMap(
          Map<String, dynamic> data) =>
      CreditTransactionStruct(
        name: deserializeParam(
          data['name'],
          ParamType.String,
          false,
        ),
        type: deserializeParam(
          data['type'],
          ParamType.String,
          false,
        ),
        amount: deserializeParam(
          data['amount'],
          ParamType.int,
          false,
        ),
        createdAt: deserializeParam(
          data['createdAt'],
          ParamType.DateTime,
          false,
        ),
      );
  @override
  Map<String, DebugDataField> toDebugSerializableMap() => {
        'name': debugSerializeParam(
          name,
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
        'amount': debugSerializeParam(
          amount,
          ParamType.int,
          name: 'int',
          nullable: false,
        ),
        'createdAt': debugSerializeParam(
          _createdAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
      };

  @override
  String toString() => 'CreditTransactionStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is CreditTransactionStruct &&
        name == other.name &&
        type == other.type &&
        amount == other.amount &&
        createdAt == other.createdAt;
  }

  @override
  int get hashCode =>
      const ListEquality().hash([name, type, amount, createdAt]);
}

CreditTransactionStruct createCreditTransactionStruct({
  String? name,
  String? type,
  int? amount,
  DateTime? createdAt,
}) =>
    CreditTransactionStruct(
      name: name,
      type: type,
      amount: amount,
      createdAt: createdAt,
    );
