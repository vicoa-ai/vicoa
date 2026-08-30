// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';

import 'index.dart';
import '/flutter_flow/flutter_flow_util.dart';

class SettingStruct extends BaseStruct {
  SettingStruct({
    bool? onboarded,
    bool? isGuest,
    int? freePerMonth,
    bool? surveyUploaded,
    bool? rateForCredit,
    bool? hasPromptedForReview,
    bool? hasPromptedReviewForUsingMessages,
    int? lastReviewPromptedSessionCount,
    int? lastReviewPromptedReferralCount,
    DateTime? lastUpdatedAt,
    String? versionNotified,
    DateTime? lastSyncUpAt,
    DateTime? lastSyncDownAt,
    bool? showHomeFilterIcon,
    bool? showHomeWebPreviewIcon,
    bool? collapseLongCode,
    int? codeCollapseLineThreshold,
    bool? collapseToolUse,
    bool? welcomeGetStartedEmailSent,
  })  : _onboarded = onboarded,
        _isGuest = isGuest,
        _freePerMonth = freePerMonth,
        _surveyUploaded = surveyUploaded,
        _rateForCredit = rateForCredit,
        _hasPromptedForReview = hasPromptedForReview,
        _hasPromptedReviewForUsingMessages = hasPromptedReviewForUsingMessages,
        _lastReviewPromptedSessionCount = lastReviewPromptedSessionCount,
        _lastReviewPromptedReferralCount = lastReviewPromptedReferralCount,
        _lastUpdatedAt = lastUpdatedAt,
        _versionNotified = versionNotified,
        _lastSyncUpAt = lastSyncUpAt,
        _lastSyncDownAt = lastSyncDownAt,
        _showHomeFilterIcon = showHomeFilterIcon,
        _showHomeWebPreviewIcon = showHomeWebPreviewIcon,
        _collapseLongCode = collapseLongCode,
        _codeCollapseLineThreshold = codeCollapseLineThreshold,
        _collapseToolUse = collapseToolUse,
        _welcomeGetStartedEmailSent = welcomeGetStartedEmailSent;

  // "onboarded" field.
  bool? _onboarded;
  bool get onboarded => _onboarded ?? false;
  set onboarded(bool? val) {
    _onboarded = val;
    debugLog();
  }

  bool hasOnboarded() => _onboarded != null;

  // "isGuest" field.
  bool? _isGuest;
  bool get isGuest => _isGuest ?? false;
  set isGuest(bool? val) {
    _isGuest = val;
    debugLog();
  }

  bool hasIsGuest() => _isGuest != null;

  // "freePerMonth" field.
  int? _freePerMonth;
  int get freePerMonth => _freePerMonth ?? 0;
  set freePerMonth(int? val) {
    _freePerMonth = val;
    debugLog();
  }

  void incrementFreePerMonth(int amount) =>
      freePerMonth = freePerMonth + amount;

  bool hasFreePerMonth() => _freePerMonth != null;

  // "surveyUploaded" field.
  bool? _surveyUploaded;
  bool get surveyUploaded => _surveyUploaded ?? false;
  set surveyUploaded(bool? val) {
    _surveyUploaded = val;
    debugLog();
  }

  bool hasSurveyUploaded() => _surveyUploaded != null;

  // "rateForCredit" field.
  bool? _rateForCredit;
  bool get rateForCredit => _rateForCredit ?? false;
  set rateForCredit(bool? val) {
    _rateForCredit = val;
    debugLog();
  }

  bool hasRateForCredit() => _rateForCredit != null;

  // "hasPromptedForReview" field.
  bool? _hasPromptedForReview;
  bool get hasPromptedForReview => _hasPromptedForReview ?? false;
  set hasPromptedForReview(bool? val) {
    _hasPromptedForReview = val;
    debugLog();
  }

  bool hasHasPromptedForReview() => _hasPromptedForReview != null;

  // "hasPromptedReviewForUsingMessages" field.
  bool? _hasPromptedReviewForUsingMessages;
  bool get hasPromptedReviewForUsingMessages =>
      _hasPromptedReviewForUsingMessages ?? false;
  set hasPromptedReviewForUsingMessages(bool? val) {
    _hasPromptedReviewForUsingMessages = val;
    debugLog();
  }

  bool hasHasPromptedReviewForUsingMessages() =>
      _hasPromptedReviewForUsingMessages != null;

  // "lastReviewPromptedSessionCount" field.
  int? _lastReviewPromptedSessionCount;
  int get lastReviewPromptedSessionCount =>
      _lastReviewPromptedSessionCount ?? 0;
  set lastReviewPromptedSessionCount(int? val) {
    _lastReviewPromptedSessionCount = val;
    debugLog();
  }

  bool hasLastReviewPromptedSessionCount() =>
      _lastReviewPromptedSessionCount != null;

  // "lastReviewPromptedReferralCount" field.
  int? _lastReviewPromptedReferralCount;
  int get lastReviewPromptedReferralCount =>
      _lastReviewPromptedReferralCount ?? 0;
  set lastReviewPromptedReferralCount(int? val) {
    _lastReviewPromptedReferralCount = val;
    debugLog();
  }

  bool hasLastReviewPromptedReferralCount() =>
      _lastReviewPromptedReferralCount != null;

  // "lastUpdatedAt" field.
  DateTime? _lastUpdatedAt;
  DateTime? get lastUpdatedAt => _lastUpdatedAt;
  set lastUpdatedAt(DateTime? val) {
    _lastUpdatedAt = val;
    debugLog();
  }

  bool hasLastUpdatedAt() => _lastUpdatedAt != null;

  // "versionNotified" field.
  String? _versionNotified;
  String get versionNotified => _versionNotified ?? '';
  set versionNotified(String? val) {
    _versionNotified = val;
    debugLog();
  }

  bool hasVersionNotified() => _versionNotified != null;

  // "lastSyncUpAt" field.
  DateTime? _lastSyncUpAt;
  DateTime? get lastSyncUpAt => _lastSyncUpAt;
  set lastSyncUpAt(DateTime? val) {
    _lastSyncUpAt = val;
    debugLog();
  }

  bool hasLastSyncUpAt() => _lastSyncUpAt != null;

  // "lastSyncDownAt" field.
  DateTime? _lastSyncDownAt;
  DateTime? get lastSyncDownAt => _lastSyncDownAt;
  set lastSyncDownAt(DateTime? val) {
    _lastSyncDownAt = val;
    debugLog();
  }

  bool hasLastSyncDownAt() => _lastSyncDownAt != null;

  // "showHomeFilterIcon" field.
  bool? _showHomeFilterIcon;
  bool get showHomeFilterIcon => _showHomeFilterIcon ?? true;
  set showHomeFilterIcon(bool? val) {
    _showHomeFilterIcon = val;
    debugLog();
  }

  bool hasShowHomeFilterIcon() => _showHomeFilterIcon != null;

  // "showHomeWebPreviewIcon" field.
  bool? _showHomeWebPreviewIcon;
  bool get showHomeWebPreviewIcon => _showHomeWebPreviewIcon ?? false;
  set showHomeWebPreviewIcon(bool? val) {
    _showHomeWebPreviewIcon = val;
    debugLog();
  }

  bool hasShowHomeWebPreviewIcon() => _showHomeWebPreviewIcon != null;

  // "collapseLongCode" field.
  bool? _collapseLongCode;
  bool get collapseLongCode => _collapseLongCode ?? true;
  set collapseLongCode(bool? val) {
    _collapseLongCode = val;
    debugLog();
  }

  bool hasCollapseLongCode() => _collapseLongCode != null;

  // "codeCollapseLineThreshold" field.
  int? _codeCollapseLineThreshold;
  int get codeCollapseLineThreshold => _codeCollapseLineThreshold ?? 8;
  set codeCollapseLineThreshold(int? val) {
    _codeCollapseLineThreshold = val;
    debugLog();
  }

  bool hasCodeCollapseLineThreshold() => _codeCollapseLineThreshold != null;

  // "collapseToolUse" field. When true, consecutive tool-use messages in the
  // agent chat fold into a compact, tap-to-expand group (mirrors vicoa-web).
  // Defaults to true — tool calls are collapsed by default.
  bool? _collapseToolUse;
  bool get collapseToolUse => _collapseToolUse ?? true;
  set collapseToolUse(bool? val) {
    _collapseToolUse = val;
    debugLog();
  }

  bool hasCollapseToolUse() => _collapseToolUse != null;

  // "welcomeGetStartedEmailSent" field. One-shot device flag: true once the
  // welcome-demo CLI setup email has been triggered for this user on this
  // device. The backend also enforces this per-account, so a fresh install
  // re-syncs the flag the next time the user taps the CTA.
  bool? _welcomeGetStartedEmailSent;
  bool get welcomeGetStartedEmailSent => _welcomeGetStartedEmailSent ?? false;
  set welcomeGetStartedEmailSent(bool? val) {
    _welcomeGetStartedEmailSent = val;
    debugLog();
  }

  bool hasWelcomeGetStartedEmailSent() => _welcomeGetStartedEmailSent != null;

  static SettingStruct fromMap(Map<String, dynamic> data) => SettingStruct(
        onboarded: data['onboarded'] as bool?,
        isGuest: data['isGuest'] as bool?,
        freePerMonth: castToType<int>(data['freePerMonth']),
        surveyUploaded: data['surveyUploaded'] as bool?,
        rateForCredit: data['rateForCredit'] as bool?,
        hasPromptedForReview: data['hasPromptedForReview'] as bool?,
        hasPromptedReviewForUsingMessages:
            data['hasPromptedReviewForUsingMessages'] as bool?,
        lastReviewPromptedSessionCount: castToType<int>(
          data['lastReviewPromptedSessionCount'] ??
              data['lastReviewPromptedCompletionCount'],
        ),
        lastReviewPromptedReferralCount:
            castToType<int>(data['lastReviewPromptedReferralCount']),
        lastUpdatedAt: data['lastUpdatedAt'] as DateTime?,
        versionNotified: data['versionNotified'] as String?,
        lastSyncUpAt: data['lastSyncUpAt'] as DateTime?,
        lastSyncDownAt: data['lastSyncDownAt'] as DateTime?,
        showHomeFilterIcon: data['showHomeFilterIcon'] as bool?,
        showHomeWebPreviewIcon: data['showHomeWebPreviewIcon'] as bool?,
        collapseLongCode: data['collapseLongCode'] as bool?,
        codeCollapseLineThreshold:
            castToType<int>(data['codeCollapseLineThreshold']),
        collapseToolUse: data['collapseToolUse'] as bool?,
        welcomeGetStartedEmailSent:
            data['welcomeGetStartedEmailSent'] as bool?,
      );

  static SettingStruct? maybeFromMap(dynamic data) =>
      data is Map ? SettingStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'onboarded': _onboarded,
        'isGuest': _isGuest,
        'freePerMonth': _freePerMonth,
        'surveyUploaded': _surveyUploaded,
        'rateForCredit': _rateForCredit,
        'hasPromptedForReview': _hasPromptedForReview,
        'hasPromptedReviewForUsingMessages': _hasPromptedReviewForUsingMessages,
        'lastReviewPromptedSessionCount': _lastReviewPromptedSessionCount,
        'lastReviewPromptedReferralCount': _lastReviewPromptedReferralCount,
        'lastUpdatedAt': _lastUpdatedAt,
        'versionNotified': _versionNotified,
        'lastSyncUpAt': _lastSyncUpAt,
        'lastSyncDownAt': _lastSyncDownAt,
        'showHomeFilterIcon': _showHomeFilterIcon,
        'showHomeWebPreviewIcon': _showHomeWebPreviewIcon,
        'collapseLongCode': _collapseLongCode,
        'codeCollapseLineThreshold': _codeCollapseLineThreshold,
        'collapseToolUse': _collapseToolUse,
        'welcomeGetStartedEmailSent': _welcomeGetStartedEmailSent,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'onboarded': serializeParam(
          _onboarded,
          ParamType.bool,
        ),
        'isGuest': serializeParam(
          _isGuest,
          ParamType.bool,
        ),
        'freePerMonth': serializeParam(
          _freePerMonth,
          ParamType.int,
        ),
        'surveyUploaded': serializeParam(
          _surveyUploaded,
          ParamType.bool,
        ),
        'rateForCredit': serializeParam(
          _rateForCredit,
          ParamType.bool,
        ),
        'hasPromptedForReview': serializeParam(
          _hasPromptedForReview,
          ParamType.bool,
        ),
        'hasPromptedReviewForUsingMessages': serializeParam(
          _hasPromptedReviewForUsingMessages,
          ParamType.bool,
        ),
        'lastReviewPromptedSessionCount': serializeParam(
          _lastReviewPromptedSessionCount,
          ParamType.int,
        ),
        'lastReviewPromptedReferralCount': serializeParam(
          _lastReviewPromptedReferralCount,
          ParamType.int,
        ),
        'lastUpdatedAt': serializeParam(
          _lastUpdatedAt,
          ParamType.DateTime,
        ),
        'versionNotified': serializeParam(
          _versionNotified,
          ParamType.String,
        ),
        'lastSyncUpAt': serializeParam(
          _lastSyncUpAt,
          ParamType.DateTime,
        ),
        'lastSyncDownAt': serializeParam(
          _lastSyncDownAt,
          ParamType.DateTime,
        ),
        'showHomeFilterIcon': serializeParam(
          _showHomeFilterIcon,
          ParamType.bool,
        ),
        'showHomeWebPreviewIcon': serializeParam(
          _showHomeWebPreviewIcon,
          ParamType.bool,
        ),
        'collapseLongCode': serializeParam(
          _collapseLongCode,
          ParamType.bool,
        ),
        'codeCollapseLineThreshold': serializeParam(
          _codeCollapseLineThreshold,
          ParamType.int,
        ),
        'collapseToolUse': serializeParam(
          _collapseToolUse,
          ParamType.bool,
        ),
        'welcomeGetStartedEmailSent': serializeParam(
          _welcomeGetStartedEmailSent,
          ParamType.bool,
        ),
      }.withoutNulls;

  static SettingStruct fromSerializableMap(Map<String, dynamic> data) =>
      SettingStruct(
        onboarded: deserializeParam(
          data['onboarded'],
          ParamType.bool,
          false,
        ),
        isGuest: deserializeParam(
          data['isGuest'],
          ParamType.bool,
          false,
        ),
        freePerMonth: deserializeParam(
          data['freePerMonth'],
          ParamType.int,
          false,
        ),
        surveyUploaded: deserializeParam(
          data['surveyUploaded'],
          ParamType.bool,
          false,
        ),
        rateForCredit: deserializeParam(
          data['rateForCredit'],
          ParamType.bool,
          false,
        ),
        hasPromptedForReview: deserializeParam(
          data['hasPromptedForReview'],
          ParamType.bool,
          false,
        ),
        hasPromptedReviewForUsingMessages: deserializeParam(
          data['hasPromptedReviewForUsingMessages'],
          ParamType.bool,
          false,
        ),
        lastReviewPromptedSessionCount: deserializeParam(
          data['lastReviewPromptedSessionCount'] ??
              data['lastReviewPromptedCompletionCount'],
          ParamType.int,
          false,
        ),
        lastReviewPromptedReferralCount: deserializeParam(
          data['lastReviewPromptedReferralCount'],
          ParamType.int,
          false,
        ),
        lastUpdatedAt: deserializeParam(
          data['lastUpdatedAt'],
          ParamType.DateTime,
          false,
        ),
        versionNotified: deserializeParam(
          data['versionNotified'],
          ParamType.String,
          false,
        ),
        lastSyncUpAt: deserializeParam(
          data['lastSyncUpAt'],
          ParamType.DateTime,
          false,
        ),
        lastSyncDownAt: deserializeParam(
          data['lastSyncDownAt'],
          ParamType.DateTime,
          false,
        ),
        showHomeFilterIcon: deserializeParam(
          data['showHomeFilterIcon'],
          ParamType.bool,
          false,
        ),
        showHomeWebPreviewIcon: deserializeParam(
          data['showHomeWebPreviewIcon'],
          ParamType.bool,
          false,
        ),
        collapseLongCode: deserializeParam(
          data['collapseLongCode'],
          ParamType.bool,
          false,
        ),
        codeCollapseLineThreshold: deserializeParam(
          data['codeCollapseLineThreshold'],
          ParamType.int,
          false,
        ),
        collapseToolUse: deserializeParam(
          data['collapseToolUse'],
          ParamType.bool,
          false,
        ),
        welcomeGetStartedEmailSent: deserializeParam(
          data['welcomeGetStartedEmailSent'],
          ParamType.bool,
          false,
        ),
      );
  @override
  Map<String, DebugDataField> toDebugSerializableMap() => {
        'onboarded': debugSerializeParam(
          onboarded,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'isGuest': debugSerializeParam(
          isGuest,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'freePerMonth': debugSerializeParam(
          freePerMonth,
          ParamType.int,
          name: 'int',
          nullable: false,
        ),
        'surveyUploaded': debugSerializeParam(
          surveyUploaded,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'rateForCredit': debugSerializeParam(
          rateForCredit,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'hasPromptedForReview': debugSerializeParam(
          hasPromptedForReview,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'hasPromptedReviewForUsingMessages': debugSerializeParam(
          hasPromptedReviewForUsingMessages,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'lastReviewPromptedSessionCount': debugSerializeParam(
          lastReviewPromptedSessionCount,
          ParamType.int,
          name: 'int',
          nullable: false,
        ),
        'lastReviewPromptedReferralCount': debugSerializeParam(
          lastReviewPromptedReferralCount,
          ParamType.int,
          name: 'int',
          nullable: false,
        ),
        'lastUpdatedAt': debugSerializeParam(
          _lastUpdatedAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
        'versionNotified': debugSerializeParam(
          versionNotified,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'lastSyncUpAt': debugSerializeParam(
          _lastSyncUpAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
        'lastSyncDownAt': debugSerializeParam(
          _lastSyncDownAt,
          ParamType.DateTime,
          name: 'DateTime',
          nullable: true,
        ),
        'showHomeFilterIcon': debugSerializeParam(
          showHomeFilterIcon,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'showHomeWebPreviewIcon': debugSerializeParam(
          showHomeWebPreviewIcon,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'collapseLongCode': debugSerializeParam(
          collapseLongCode,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'codeCollapseLineThreshold': debugSerializeParam(
          codeCollapseLineThreshold,
          ParamType.int,
          name: 'int',
          nullable: false,
        ),
        'collapseToolUse': debugSerializeParam(
          collapseToolUse,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
        'welcomeGetStartedEmailSent': debugSerializeParam(
          welcomeGetStartedEmailSent,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
      };

  @override
  String toString() => 'SettingStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    return other is SettingStruct &&
        onboarded == other.onboarded &&
        isGuest == other.isGuest &&
        freePerMonth == other.freePerMonth &&
        surveyUploaded == other.surveyUploaded &&
        rateForCredit == other.rateForCredit &&
        hasPromptedForReview == other.hasPromptedForReview &&
        hasPromptedReviewForUsingMessages ==
            other.hasPromptedReviewForUsingMessages &&
        lastReviewPromptedSessionCount ==
            other.lastReviewPromptedSessionCount &&
        lastReviewPromptedReferralCount ==
            other.lastReviewPromptedReferralCount &&
        lastUpdatedAt == other.lastUpdatedAt &&
        versionNotified == other.versionNotified &&
        lastSyncUpAt == other.lastSyncUpAt &&
        lastSyncDownAt == other.lastSyncDownAt &&
        showHomeFilterIcon == other.showHomeFilterIcon &&
        showHomeWebPreviewIcon == other.showHomeWebPreviewIcon &&
        collapseLongCode == other.collapseLongCode &&
        codeCollapseLineThreshold == other.codeCollapseLineThreshold &&
        collapseToolUse == other.collapseToolUse &&
        welcomeGetStartedEmailSent == other.welcomeGetStartedEmailSent;
  }

  @override
  int get hashCode => const ListEquality().hash([
        onboarded,
        isGuest,
        freePerMonth,
        surveyUploaded,
        rateForCredit,
        hasPromptedForReview,
        hasPromptedReviewForUsingMessages,
        lastReviewPromptedSessionCount,
        lastReviewPromptedReferralCount,
        lastUpdatedAt,
        versionNotified,
        lastSyncUpAt,
        lastSyncDownAt,
        showHomeFilterIcon,
        showHomeWebPreviewIcon,
        collapseLongCode,
        codeCollapseLineThreshold,
        collapseToolUse,
        welcomeGetStartedEmailSent
      ]);
}

SettingStruct createSettingStruct({
  bool? onboarded,
  bool? isGuest,
  int? freePerMonth,
  bool? surveyUploaded,
  bool? rateForCredit,
  bool? hasPromptedForReview,
  bool? hasPromptedReviewForUsingMessages,
  int? lastReviewPromptedSessionCount,
  int? lastReviewPromptedReferralCount,
  DateTime? lastUpdatedAt,
  String? versionNotified,
  DateTime? lastSyncUpAt,
  DateTime? lastSyncDownAt,
  bool? showHomeFilterIcon,
  bool? showHomeWebPreviewIcon,
  bool? collapseLongCode,
  int? codeCollapseLineThreshold,
  bool? collapseToolUse,
  bool? welcomeGetStartedEmailSent,
}) =>
    SettingStruct(
      onboarded: onboarded,
      isGuest: isGuest,
      freePerMonth: freePerMonth,
      surveyUploaded: surveyUploaded,
      rateForCredit: rateForCredit,
      hasPromptedForReview: hasPromptedForReview,
      hasPromptedReviewForUsingMessages: hasPromptedReviewForUsingMessages,
      lastReviewPromptedSessionCount: lastReviewPromptedSessionCount,
      lastReviewPromptedReferralCount: lastReviewPromptedReferralCount,
      lastUpdatedAt: lastUpdatedAt,
      versionNotified: versionNotified,
      lastSyncUpAt: lastSyncUpAt,
      lastSyncDownAt: lastSyncDownAt,
      showHomeFilterIcon: showHomeFilterIcon,
      showHomeWebPreviewIcon: showHomeWebPreviewIcon,
      collapseLongCode: collapseLongCode,
      codeCollapseLineThreshold: codeCollapseLineThreshold,
      collapseToolUse: collapseToolUse,
      welcomeGetStartedEmailSent: welcomeGetStartedEmailSent,
    );
