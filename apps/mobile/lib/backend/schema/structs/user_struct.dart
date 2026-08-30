// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';

import 'index.dart';
import '/flutter_flow/flutter_flow_util.dart';

class UserStruct extends BaseStruct {
  UserStruct({
    String? subscriptionStatus,
    String? id,
    String? email,
    String? name,
    String? superWallUserId,
    String? revenueCatId,
    String? referralCode,
    String? referredBy,
    DateTime? createdAt,
    DateTime? updatedAt,
  })  : _subscriptionStatus = subscriptionStatus,
        _id = id,
        _email = email,
        _name = name,
        _superWallUserId = superWallUserId,
        _revenueCatId = revenueCatId,
        _referralCode = referralCode,
        _referredBy = referredBy,
        _createdAt = createdAt,
        _updatedAt = updatedAt;

  // "subscriptionStatus" field.
  String? _subscriptionStatus;
  String get subscriptionStatus => _subscriptionStatus ?? '';
  set subscriptionStatus(String? val) {
    _subscriptionStatus = val;
    debugLog();
  }

  bool hasSubscriptionStatus() => _subscriptionStatus != null;

  // "id" field.
  String? _id;
  String get id => _id ?? '';
  set id(String? val) {
    _id = val;
    debugLog();
  }

  bool hasId() => _id != null;

  // "email" field.
  String? _email;
  String get email => _email ?? '';
  set email(String? val) {
    _email = val;
    debugLog();
  }

  bool hasEmail() => _email != null;

  // "name" field.
  String? _name;
  String get name => _name ?? '';
  set name(String? val) {
    _name = val;
    debugLog();
  }

  bool hasName() => _name != null;

  // "superWallUserId" field.
  String? _superWallUserId;
  String get superWallUserId => _superWallUserId ?? '';
  set superWallUserId(String? val) {
    _superWallUserId = val;
    debugLog();
  }

  bool hasSuperWallUserId() => _superWallUserId != null;

  // "revenueCatId" field.
  String? _revenueCatId;
  String get revenueCatId => _revenueCatId ?? '';
  set revenueCatId(String? val) {
    _revenueCatId = val;
    debugLog();
  }

  bool hasRevenueCatId() => _revenueCatId != null;

  // "referralCode" field.
  String? _referralCode;
  String get referralCode => _referralCode ?? '';
  set referralCode(String? val) {
    _referralCode = val;
    debugLog();
  }

  bool hasReferralCode() => _referralCode != null;

  // "referredBy" field.
  String? _referredBy;
  String get referredBy => _referredBy ?? '';
  set referredBy(String? val) {
    _referredBy = val;
    debugLog();
  }

  bool hasReferredBy() => _referredBy != null;

  // "createdAt" field.
  DateTime? _createdAt;
  DateTime? get createdAt => _createdAt;
  set createdAt(DateTime? val) {
    _createdAt = val;
    debugLog();
  }

  bool hasCreatedAt() => _createdAt != null;

  // "updatedAt" field.
  DateTime? _updatedAt;
  DateTime? get updatedAt => _updatedAt;
  set updatedAt(DateTime? val) {
    _updatedAt = val;
    debugLog();
  }

  bool hasUpdatedAt() => _updatedAt != null;


  static UserStruct fromMap(Map<String, dynamic> data) => UserStruct(
        subscriptionStatus: data['subscriptionStatus'] as String?,
        id: data['id'] as String?,
        email: data['email'] as String?,
        name: data['name'] as String?,
        superWallUserId: data['superWallUserId'] as String?,
        revenueCatId: data['revenueCatId'] as String?,
        referralCode: data['referralCode'] as String?,
        referredBy: data['referredBy'] as String?,
        createdAt: data['createdAt'] as DateTime?,
        updatedAt: data['updatedAt'] as DateTime?,
      );

  static UserStruct? maybeFromMap(dynamic data) =>
      data is Map ? UserStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'subscriptionStatus': _subscriptionStatus,
        'id': _id,
        'email': _email,
        'name': _name,
        'superWallUserId': _superWallUserId,
        'revenueCatId': _revenueCatId,
        'referralCode': _referralCode,
        'referredBy': _referredBy,
        'createdAt': _createdAt,
        'updatedAt': _updatedAt,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'subscriptionStatus': serializeParam(
          _subscriptionStatus,
          ParamType.String,
        ),
        'id': serializeParam(
          _id,
          ParamType.String,
        ),
        'email': serializeParam(
          _email,
          ParamType.String,
        ),
        'name': serializeParam(
          _name,
          ParamType.String,
        ),
        'superWallUserId': serializeParam(
          _superWallUserId,
          ParamType.String,
        ),
        'revenueCatId': serializeParam(
          _revenueCatId,
          ParamType.String,
        ),
        'referralCode': serializeParam(
          _referralCode,
          ParamType.String,
        ),
        'referredBy': serializeParam(
          _referredBy,
          ParamType.String,
        ),
        'createdAt': serializeParam(
          _createdAt,
          ParamType.DateTime,
        ),
        'updatedAt': serializeParam(
          _updatedAt,
          ParamType.DateTime,
        ),
      }.withoutNulls;

  static UserStruct fromSerializableMap(Map<String, dynamic> data) =>
      UserStruct(
        subscriptionStatus: deserializeParam(
          data['subscriptionStatus'],
          ParamType.String,
          false,
        ),
        id: deserializeParam(
          data['id'],
          ParamType.String,
          false,
        ),
        email: deserializeParam(
          data['email'],
          ParamType.String,
          false,
        ),
        name: deserializeParam(
          data['name'],
          ParamType.String,
          false,
        ),
        superWallUserId: deserializeParam(
          data['superWallUserId'],
          ParamType.String,
          false,
        ),
        revenueCatId: deserializeParam(
          data['revenueCatId'],
          ParamType.String,
          false,
        ),
        referralCode: deserializeParam(
          data['referralCode'],
          ParamType.String,
          false,
        ),
        referredBy: deserializeParam(
          data['referredBy'],
          ParamType.String,
          false,
        ),
        createdAt: deserializeParam(
          data['createdAt'],
          ParamType.DateTime,
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
        'subscriptionStatus': debugSerializeParam(
          subscriptionStatus,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'id': debugSerializeParam(
          id,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'email': debugSerializeParam(
          email,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'name': debugSerializeParam(
          name,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'superWallUserId': debugSerializeParam(
          superWallUserId,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'revenueCatId': debugSerializeParam(
          revenueCatId,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'referralCode': debugSerializeParam(
          referralCode,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'referredBy': debugSerializeParam(
          referredBy,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'createdAt': debugSerializeParam(
          _createdAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
        'updatedAt': debugSerializeParam(
          _updatedAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
      };

  @override
  String toString() => 'UserStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is UserStruct &&
        subscriptionStatus == other.subscriptionStatus &&
        id == other.id &&
        email == other.email &&
        name == other.name &&
        superWallUserId == other.superWallUserId &&
        revenueCatId == other.revenueCatId &&
        referralCode == other.referralCode &&
        referredBy == other.referredBy &&
        createdAt == other.createdAt &&
        updatedAt == other.updatedAt;
  }

  @override
  int get hashCode => const ListEquality().hash([
        subscriptionStatus,
        id,
        email,
        name,
        superWallUserId,
        revenueCatId,
        referralCode,
        referredBy,
        createdAt,
        updatedAt,
      ]);
}

UserStruct createUserStruct({
  String? subscriptionStatus,
  String? id,
  String? email,
  String? name,
  String? superWallUserId,
  String? revenueCatId,
  String? referralCode,
  String? referredBy,
  DateTime? createdAt,
  DateTime? updatedAt,
}) =>
    UserStruct(
      subscriptionStatus: subscriptionStatus,
      id: id,
      email: email,
      name: name,
      superWallUserId: superWallUserId,
      revenueCatId: revenueCatId,
      referralCode: referralCode,
      referredBy: referredBy,
      createdAt: createdAt,
      updatedAt: updatedAt,
    );
