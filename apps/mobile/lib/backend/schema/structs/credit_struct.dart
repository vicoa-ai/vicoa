// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';

import 'index.dart';
import '/flutter_flow/flutter_flow_util.dart';

class CreditStruct extends BaseStruct {
  CreditStruct({
    int? balance,
    DateTime? updatedAt,
  })  : _balance = balance,
        _updatedAt = updatedAt;

  // "balance" field.
  int? _balance;
  int get balance => _balance ?? 0;
  set balance(int? val) {
    _balance = val;
    debugLog();
  }

  void incrementBalance(int amount) => balance = balance + amount;

  bool hasBalance() => _balance != null;

  // "updatedAt" field.
  DateTime? _updatedAt;
  DateTime? get updatedAt => _updatedAt;
  set updatedAt(DateTime? val) {
    _updatedAt = val;
    debugLog();
  }

  bool hasUpdatedAt() => _updatedAt != null;

  static CreditStruct fromMap(Map<String, dynamic> data) => CreditStruct(
        balance: castToType<int>(data['balance']),
        updatedAt: data['updatedAt'] as DateTime?,
      );

  static CreditStruct? maybeFromMap(dynamic data) =>
      data is Map ? CreditStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'balance': _balance,
        'updatedAt': _updatedAt,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'balance': serializeParam(
          _balance,
          ParamType.int,
        ),
        'updatedAt': serializeParam(
          _updatedAt,
          ParamType.DateTime,
        ),
      }.withoutNulls;

  static CreditStruct fromSerializableMap(Map<String, dynamic> data) =>
      CreditStruct(
        balance: deserializeParam(
          data['balance'],
          ParamType.int,
          false,
        ),
        updatedAt: deserializeParam(
          data['updatedAt'],
          ParamType.DateTime,
          false,
        ),
      );
  @override
  Map<String, DebugDataField> toDebugSerializableMap() => {
        'balance': debugSerializeParam(
          balance,
          ParamType.int,
          name: 'int',
          nullable: false,
        ),
        'updatedAt': debugSerializeParam(
          _updatedAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
      };

  @override
  String toString() => 'CreditStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is CreditStruct &&
        balance == other.balance &&
        updatedAt == other.updatedAt;
  }

  @override
  int get hashCode => const ListEquality().hash([balance, updatedAt]);
}

CreditStruct createCreditStruct({
  int? balance,
  DateTime? updatedAt,
}) =>
    CreditStruct(
      balance: balance,
      updatedAt: updatedAt,
    );
