import 'dart:async';
import 'package:flutter/material.dart';
import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import 'package:shared_preferences/shared_preferences.dart';
import 'flutter_flow/flutter_flow_util.dart';

class FFAppState extends ChangeNotifier {
  static FFAppState _instance = FFAppState._internal();

  factory FFAppState() {
    return _instance;
  }

  FFAppState._internal();

  static void reset() {
    _instance = FFAppState._internal();
  }

  Future initializePersistedState() async {
    prefs = await SharedPreferences.getInstance();
    _safeInit(() {
      if (prefs.containsKey('ff_setting')) {
        try {
          final serializedData = prefs.getString('ff_setting') ?? '{}';
          _setting =
              SettingStruct.fromSerializableMap(jsonDecode(serializedData));
        } catch (e) {
          print("Can't decode persisted data type. Error: $e.");
        }
      }
    });
    _safeInit(() {
      if (prefs.containsKey('ff_user')) {
        try {
          final serializedData = prefs.getString('ff_user') ?? '{}';
          _user = UserStruct.fromSerializableMap(jsonDecode(serializedData));
        } catch (e) {
          print("Can't decode persisted data type. Error: $e.");
        }
      }
    });
    _safeInit(() {
      _surveys = LoggableList(
        prefs
                .getStringList('ff_surveys')
                ?.map((x) {
                  try {
                    return SurveyStruct.fromSerializableMap(jsonDecode(x));
                  } catch (e) {
                    print("Can't decode persisted data type. Error: $e.");
                    return null;
                  }
                })
                .withoutNulls
                .toList() ??
            _surveys,
      );
    });
    _safeInit(() {
      _appVersion = prefs.getString('ff_appVersion') ?? _appVersion;
    });
    _safeInit(() {
      if (prefs.containsKey('ff_credit')) {
        try {
          final serializedData = prefs.getString('ff_credit') ?? '{}';
          _credit =
              CreditStruct.fromSerializableMap(jsonDecode(serializedData));
        } catch (e) {
          print("Can't decode persisted data type. Error: $e.");
        }
      }
    });
    _safeInit(() {
      _creditTransactions = LoggableList(
        prefs
                .getStringList('ff_creditTransactions')
                ?.map((x) {
                  try {
                    return CreditTransactionStruct.fromSerializableMap(
                        jsonDecode(x));
                  } catch (e) {
                    print("Can't decode persisted data type. Error: $e.");
                    return null;
                  }
                })
                .withoutNulls
                .toList() ??
            _creditTransactions,
      );
    });
    _safeInit(() {
      final draftMessagesJson = prefs.getString('ff_chatDraftMessages') ?? '{}';
      try {
        final decoded = jsonDecode(draftMessagesJson) as Map<String, dynamic>;
        _chatDraftMessages = decoded.map((key, value) => MapEntry(key, value.toString()));
      } catch (e) {
        print("Can't decode chat draft messages. Error: $e.");
        _chatDraftMessages = {};
      }
    });
    _safeInit(() {
      final lastSeenIdsJson = prefs.getString('ff_lastSeenMessageIds') ?? '{}';
      try {
        final decoded = jsonDecode(lastSeenIdsJson) as Map<String, dynamic>;
        _lastSeenMessageIds = decoded.map((key, value) => MapEntry(key, value.toString()));
      } catch (e) {
        print("Can't decode last seen message IDs. Error: $e.");
        _lastSeenMessageIds = {};
      }
    });
    _safeInit(() {
      // One-time migration off the old monolithic `ff_cachedChatMessages`
      // blob: re-encoding it on every WS message arrival was blocking the UI
      // for 30–50 ms per message (3.8 MB+ for users with many chats). The
      // new ChatMessagesCache stores one file per instance and debounces
      // writes. Hand the old data over, then schedule cleanup of the prefs
      // key so it doesn't sit there forever consuming storage.
      final cachedMessagesJson =
          prefs.getString('ff_cachedChatMessages') ?? '{}';
      try {
        final decoded =
            jsonDecode(cachedMessagesJson) as Map<String, dynamic>;
        final seed = decoded.map<String, List<dynamic>>((key, value) {
          if (value is List) {
            return MapEntry(key, List<dynamic>.from(value));
          }
          return MapEntry(key, <dynamic>[]);
        });
        if (seed.isNotEmpty) {
          actions.ChatMessagesCache.instance.seedMemoryFromMap(seed);
        }
      } catch (e) {
        print("Can't decode cached chat messages. Error: $e.");
      }
      // Give the staggered per-instance flushes time to land, then drop the
      // old blob so it doesn't keep eating storage.
      Timer(const Duration(seconds: 60), () {
        prefs.remove('ff_cachedChatMessages');
      });
    });
    _safeInit(() {
      _lastWebPreviewUrl = prefs.getString('ff_lastWebPreviewUrl') ?? '';
    });
    _safeInit(() {
      _lastWebPreviewDesktopMode = prefs.getBool('ff_lastWebPreviewDesktopMode') ?? false;
    });
    _safeInit(() {
      _voiceTranscriptionLanguageTag = prefs.getString('ff_voiceTranscriptionLanguageTag') ?? _voiceTranscriptionLanguageTag;
    });
    _safeInit(() {
      _appLanguage = prefs.getString('ff_appLanguage') ?? _appLanguage;
    });
    _safeInit(() {
      _pendingDeletions = LoggableList(
        prefs
                .getStringList('ff_pendingDeletions')
                ?.map((x) {
                  try {
                    return LocalDeletionStruct.fromSerializableMap(
                        jsonDecode(x));
                  } catch (e) {
                    print("Can't decode persisted data type. Error: $e.");
                    return null;
                  }
                })
                .withoutNulls
                .toList() ??
            _pendingDeletions,
      );
    });
    _safeInit(() {
      final cachedMachinesJson = prefs.getString('ff_cachedMachines') ?? '[]';
      try {
        final decoded = jsonDecode(cachedMachinesJson);
        if (decoded is List) {
          _cachedMachines = decoded;
        }
      } catch (e) {
        print("Can't decode cached machines. Error: $e.");
        _cachedMachines = [];
      }
    });
    _safeInit(() {
      _cachedDirectories = LoggableList(
        prefs.getStringList('ff_cachedDirectories') ?? _cachedDirectories,
      );
    });
    _safeInit(() {
      final cachedInstancesJson =
          prefs.getString('ff_cachedAgentInstances') ?? '[]';
      try {
        final decoded = jsonDecode(cachedInstancesJson);
        if (decoded is List) {
          _cachedAgentInstances = decoded;
        }
      } catch (e) {
        print("Can't decode cached agent instances. Error: $e.");
        _cachedAgentInstances = [];
      }
    });
    _safeInit(() {
      final timestampStr = prefs.getString('ff_cachedAgentInstancesTimestamp');
      if (timestampStr != null) {
        try {
          _cachedAgentInstancesTimestamp = DateTime.parse(timestampStr);
        } catch (e) {
          print("Can't parse cached agent instances timestamp. Error: $e.");
          _cachedAgentInstancesTimestamp = null;
        }
      }
    });
    _safeInit(() {
      final cachedAgentsJson = prefs.getString('ff_cachedAgents') ?? '[]';
      try {
        final decoded = jsonDecode(cachedAgentsJson);
        if (decoded is List) {
          _cachedAgents = decoded;
        }
      } catch (e) {
        print("Can't decode cached agents. Error: $e.");
        _cachedAgents = [];
      }
    });
    _safeInit(() {
      final timestampStr = prefs.getString('ff_cachedAgentsTimestamp');
      if (timestampStr != null) {
        try {
          _cachedAgentsTimestamp = DateTime.parse(timestampStr);
        } catch (e) {
          print("Can't parse cached agents timestamp. Error: $e.");
          _cachedAgentsTimestamp = null;
        }
      }
    });
    _safeInit(() {
      final timestampStr = prefs.getString('ff_cachedMachinesTimestamp');
      if (timestampStr != null) {
        try {
          _cachedMachinesTimestamp = DateTime.parse(timestampStr);
        } catch (e) {
          print("Can't parse cached machines timestamp. Error: $e.");
          _cachedMachinesTimestamp = null;
        }
      }
    });
    _safeInit(() {
      final json = prefs.getString('ff_userPreferences');
      if (json != null) {
        try {
          _userPreferences = UserPreferences.fromJson(jsonDecode(json) as Map<String, dynamic>);
        } catch (e) {
          print("Can't decode userPreferences. Error: $e.");
        }
      } else {
        // Migrate from legacy flat keys
        _userPreferences = UserPreferences(
          newSessionMachineId: prefs.getString('ff_lastSelectedMachineId'),
          newSessionAgentType: prefs.getString('ff_lastSelectedAgentType'),
        );
      }
    });
    _safeInit(() {
      final json = prefs.getString('ff_analyticsFlags');
      if (json != null) {
        try {
          _analyticsFlags = AnalyticsFlags.fromJson(jsonDecode(json) as Map<String, dynamic>);
        } catch (e) {
          print("Can't decode analyticsFlags. Error: $e.");
        }
      }
    });
    _safeInit(() {
      _gettingStartedDismissed = prefs.getBool('ff_gettingStartedDismissed') ?? false;
    });
    _safeInit(() {
      _gettingStartedCollapsed = prefs.getBool('ff_gettingStartedCollapsed') ?? false;
    });
    _safeInit(() {
      _gettingStartedActivated = prefs.getBool('ff_gettingStartedActivated') ?? false;
    });
  }

  void update(VoidCallback callback) {
    callback();
    notifyListeners();
  }

  late SharedPreferences prefs;

  SettingStruct _setting =
      SettingStruct.fromSerializableMap(jsonDecode('{\"freePerMonth\":\"2\"}'));
  SettingStruct get setting => _setting?..logger = () => debugLogAppState(this);
  set setting(SettingStruct value) {
    _setting = value;
    prefs.setString('ff_setting', value.serialize());
    debugLogAppState(this);
  }

  void updateSettingStruct(Function(SettingStruct) updateFn) {
    updateFn(_setting);
    prefs.setString('ff_setting', _setting.serialize());
    debugLogAppState(this);
  }

  UserStruct _user = UserStruct();
  UserStruct get user => _user?..logger = () => debugLogAppState(this);
  set user(UserStruct value) {
    _user = value;
    prefs.setString('ff_user', value.serialize());
    debugLogAppState(this);
  }

  void updateUserStruct(Function(UserStruct) updateFn) {
    updateFn(_user);
    prefs.setString('ff_user', _user.serialize());
    debugLogAppState(this);
  }

  late LoggableList<SurveyStruct> _surveys = LoggableList([]);
  List<SurveyStruct> get surveys =>
      _surveys?..logger = () => debugLogAppState(this);
  set surveys(List<SurveyStruct> value) {
    if (value != null) {
      _surveys = LoggableList(value);
    }

    prefs.setStringList('ff_surveys', value.map((x) => x.serialize()).toList());
    debugLogAppState(this);
  }

  void addToSurveys(SurveyStruct value) {
    surveys.add(value);
    prefs.setStringList(
        'ff_surveys', _surveys.map((x) => x.serialize()).toList());
  }

  void removeFromSurveys(SurveyStruct value) {
    surveys.remove(value);
    prefs.setStringList(
        'ff_surveys', _surveys.map((x) => x.serialize()).toList());
  }

  void removeAtIndexFromSurveys(int index) {
    surveys.removeAt(index);
    prefs.setStringList(
        'ff_surveys', _surveys.map((x) => x.serialize()).toList());
  }

  void updateSurveysAtIndex(
    int index,
    SurveyStruct Function(SurveyStruct) updateFn,
  ) {
    surveys[index] = updateFn(_surveys[index]);
    prefs.setStringList(
        'ff_surveys', _surveys.map((x) => x.serialize()).toList());
  }

  void insertAtIndexInSurveys(int index, SurveyStruct value) {
    surveys.insert(index, value);
    prefs.setStringList(
        'ff_surveys', _surveys.map((x) => x.serialize()).toList());
  }

  String _appVersion = "1.7.8";
  String get appVersion => _appVersion;
  set appVersion(String value) {
    _appVersion = value;
    prefs.setString('ff_appVersion', value);
    debugLogAppState(this);
  }

  CreditStruct _credit = CreditStruct();
  CreditStruct get credit => _credit?..logger = () => debugLogAppState(this);
  set credit(CreditStruct value) {
    _credit = value;
    prefs.setString('ff_credit', value.serialize());
    debugLogAppState(this);
  }

  void updateCreditStruct(Function(CreditStruct) updateFn) {
    updateFn(_credit);
    prefs.setString('ff_credit', _credit.serialize());
    debugLogAppState(this);
  }

  late LoggableList<CreditTransactionStruct> _creditTransactions =
      LoggableList([]);
  List<CreditTransactionStruct> get creditTransactions =>
      _creditTransactions?..logger = () => debugLogAppState(this);
  set creditTransactions(List<CreditTransactionStruct> value) {
    if (value != null) {
      _creditTransactions = LoggableList(value);
    }

    prefs.setStringList(
        'ff_creditTransactions', value.map((x) => x.serialize()).toList());
    debugLogAppState(this);
  }

  void addToCreditTransactions(CreditTransactionStruct value) {
    creditTransactions.add(value);
    prefs.setStringList('ff_creditTransactions',
        _creditTransactions.map((x) => x.serialize()).toList());
  }

  void removeFromCreditTransactions(CreditTransactionStruct value) {
    creditTransactions.remove(value);
    prefs.setStringList('ff_creditTransactions',
        _creditTransactions.map((x) => x.serialize()).toList());
  }

  void removeAtIndexFromCreditTransactions(int index) {
    creditTransactions.removeAt(index);
    prefs.setStringList('ff_creditTransactions',
        _creditTransactions.map((x) => x.serialize()).toList());
  }

  void updateCreditTransactionsAtIndex(
    int index,
    CreditTransactionStruct Function(CreditTransactionStruct) updateFn,
  ) {
    creditTransactions[index] = updateFn(_creditTransactions[index]);
    prefs.setStringList('ff_creditTransactions',
        _creditTransactions.map((x) => x.serialize()).toList());
  }

  void insertAtIndexInCreditTransactions(
      int index, CreditTransactionStruct value) {
    creditTransactions.insert(index, value);
    prefs.setStringList('ff_creditTransactions',
        _creditTransactions.map((x) => x.serialize()).toList());
  }

  Map<String, String> _chatDraftMessages = {};
  Map<String, String> get chatDraftMessages => _chatDraftMessages;

  void setChatDraft(String instanceId, String draftText) {
    if (draftText.trim().isEmpty) {
      _chatDraftMessages.remove(instanceId);
    } else {
      _chatDraftMessages[instanceId] = draftText;
    }
    prefs.setString('ff_chatDraftMessages', jsonEncode(_chatDraftMessages));
    debugLogAppState(this);
  }

  String getChatDraft(String instanceId) {
    return _chatDraftMessages[instanceId] ?? '';
  }

  void clearChatDraft(String instanceId) {
    _chatDraftMessages.remove(instanceId);
    prefs.setString('ff_chatDraftMessages', jsonEncode(_chatDraftMessages));
    debugLogAppState(this);
  }

  Map<String, String> _lastSeenMessageIds = {};
  Map<String, String> get lastSeenMessageIds => _lastSeenMessageIds;

  void setLastSeenMessageId(String instanceId, String messageId) {
    _lastSeenMessageIds[instanceId] = messageId;
    prefs.setString('ff_lastSeenMessageIds', jsonEncode(_lastSeenMessageIds));
    debugLogAppState(this);
  }

  String getLastSeenMessageId(String instanceId) {
    return _lastSeenMessageIds[instanceId] ?? '';
  }

  // Backing storage lives in ChatMessagesCache (one file per instance,
  // debounced disk writes, isolate-encoded). These wrappers preserve the
  // legacy sync API so all existing call sites keep working unchanged.

  void setCachedMessages(String instanceId, List<dynamic> messages) {
    actions.ChatMessagesCache.instance.set(instanceId, messages);
  }

  /// Returns the cached message list synchronously. On a memory-cache miss
  /// returns an empty list immediately and kicks off a background disk read;
  /// FFAppState fires `notifyListeners` once that read completes so
  /// AnimatedBuilder/Consumer-wired widgets can pick up the data.
  List<dynamic> getCachedMessages(String instanceId) {
    return actions.ChatMessagesCache.instance.getSync(
      instanceId,
      onLoaded: notifyListeners,
    );
  }

  void clearCachedMessages(String instanceId) {
    actions.ChatMessagesCache.instance.delete(instanceId);
  }

  String _lastWebPreviewUrl = '';
  String get lastWebPreviewUrl => _lastWebPreviewUrl;

  void setLastWebPreviewUrl(String url) {
    _lastWebPreviewUrl = url.trim();
    prefs.setString('ff_lastWebPreviewUrl', _lastWebPreviewUrl);
    debugLogAppState(this);
  }

  void clearLastWebPreviewUrl() {
    _lastWebPreviewUrl = '';
    prefs.remove('ff_lastWebPreviewUrl');
    debugLogAppState(this);
  }

  bool _lastWebPreviewDesktopMode = false;
  bool get lastWebPreviewDesktopMode => _lastWebPreviewDesktopMode;

  void setLastWebPreviewDesktopMode(bool value) {
    _lastWebPreviewDesktopMode = value;
    prefs.setBool('ff_lastWebPreviewDesktopMode', value);
    debugLogAppState(this);
  }

  String _voiceTranscriptionLanguageTag = 'en';
  String get voiceTranscriptionLanguageTag => _voiceTranscriptionLanguageTag;

  void setVoiceTranscriptionLanguageTag(String value) {
    _voiceTranscriptionLanguageTag = value.trim().isEmpty ? 'en' : value.trim();
    prefs.setString(
      'ff_voiceTranscriptionLanguageTag',
      _voiceTranscriptionLanguageTag,
    );
    debugLogAppState(this);
  }

  /// App UI language preference: 'system' (follow device locale), 'en', or 'zh'.
  String _appLanguage = 'system';
  String get appLanguage => _appLanguage;

  void setAppLanguagePref(String value) {
    _appLanguage = value.trim().isEmpty ? 'system' : value.trim();
    prefs.setString('ff_appLanguage', _appLanguage);
    debugLogAppState(this);
  }

  late LoggableList<LocalDeletionStruct> _pendingDeletions = LoggableList([]);
  List<LocalDeletionStruct> get pendingDeletions =>
      _pendingDeletions?..logger = () => debugLogAppState(this);
  set pendingDeletions(List<LocalDeletionStruct> value) {
    if (value != null) {
      _pendingDeletions = LoggableList(value);
    }

    prefs.setStringList(
        'ff_pendingDeletions', value.map((x) => x.serialize()).toList());
    debugLogAppState(this);
  }

  void addToPendingDeletions(LocalDeletionStruct value) {
    pendingDeletions.add(value);
    prefs.setStringList('ff_pendingDeletions',
        _pendingDeletions.map((x) => x.serialize()).toList());
  }

  void removeFromPendingDeletions(LocalDeletionStruct value) {
    pendingDeletions.remove(value);
    prefs.setStringList('ff_pendingDeletions',
        _pendingDeletions.map((x) => x.serialize()).toList());
  }

  void removeAtIndexFromPendingDeletions(int index) {
    pendingDeletions.removeAt(index);
    prefs.setStringList('ff_pendingDeletions',
        _pendingDeletions.map((x) => x.serialize()).toList());
  }

  void updatePendingDeletionsAtIndex(
    int index,
    LocalDeletionStruct Function(LocalDeletionStruct) updateFn,
  ) {
    pendingDeletions[index] = updateFn(_pendingDeletions[index]);
    prefs.setStringList('ff_pendingDeletions',
        _pendingDeletions.map((x) => x.serialize()).toList());
  }

  void insertAtIndexInPendingDeletions(int index, LocalDeletionStruct value) {
    pendingDeletions.insert(index, value);
    prefs.setStringList('ff_pendingDeletions',
        _pendingDeletions.map((x) => x.serialize()).toList());
  }

  List<dynamic> _cachedMachines = [];
  List<dynamic> get cachedMachines => _cachedMachines;
  set cachedMachines(List<dynamic> value) {
    _cachedMachines = value;
    prefs.setString('ff_cachedMachines', jsonEncode(value));
    debugLogAppState(this);
  }

  late LoggableList<String> _cachedDirectories = LoggableList([]);
  List<String> get cachedDirectories =>
      _cachedDirectories?..logger = () => debugLogAppState(this);
  set cachedDirectories(List<String> value) {
    if (value != null) {
      _cachedDirectories = LoggableList(value);
    }
    prefs.setStringList('ff_cachedDirectories', value);
    debugLogAppState(this);
  }

  void addToCachedDirectories(String value) {
    if (value.trim().isEmpty) return;
    // Remove if already exists (to move to top)
    cachedDirectories.remove(value);
    // Add to beginning
    cachedDirectories.insert(0, value);
    // Keep only last 10 directories
    if (cachedDirectories.length > 10) {
      _cachedDirectories = LoggableList(cachedDirectories.sublist(0, 10));
    }
    prefs.setStringList('ff_cachedDirectories', _cachedDirectories);
  }

  UserPreferences _userPreferences = UserPreferences();
  UserPreferences get userPreferences => _userPreferences;
  void updateUserPreferences(UserPreferences Function(UserPreferences) updateFn) {
    _userPreferences = updateFn(_userPreferences);
    prefs.setString('ff_userPreferences', jsonEncode(_userPreferences.toJson()));
    debugLogAppState(this);
  }

  AnalyticsFlags _analyticsFlags = AnalyticsFlags();
  AnalyticsFlags get analyticsFlags => _analyticsFlags;
  void updateAnalyticsFlags(void Function(AnalyticsFlags) updateFn) {
    updateFn(_analyticsFlags);
    prefs.setString('ff_analyticsFlags', jsonEncode(_analyticsFlags.toJson()));
    debugLogAppState(this);
  }

  // Getting-started checklist UI state (the derived step completion is read
  // live from account data; only these dismiss/collapse bits are persisted).
  bool _gettingStartedDismissed = false;
  bool get gettingStartedDismissed => _gettingStartedDismissed;
  set gettingStartedDismissed(bool value) {
    _gettingStartedDismissed = value;
    prefs.setBool('ff_gettingStartedDismissed', value);
  }

  bool _gettingStartedCollapsed = false;
  bool get gettingStartedCollapsed => _gettingStartedCollapsed;
  set gettingStartedCollapsed(bool value) {
    _gettingStartedCollapsed = value;
    prefs.setBool('ff_gettingStartedCollapsed', value);
  }

  // Monotonic per-account cache of "the user has sent a real message" (the
  // truth comes from the server's total_user_messages). Seeds the checklist's
  // step 3 to avoid a flash for returning activated users. Reset on logout via
  // clearAllUserData so a new account on the same device starts unactivated.
  bool _gettingStartedActivated = false;
  bool get gettingStartedActivated => _gettingStartedActivated;
  set gettingStartedActivated(bool value) {
    _gettingStartedActivated = value;
    prefs.setBool('ff_gettingStartedActivated', value);
  }

  // Cached agent instances (sessions)
  List<dynamic> _cachedAgentInstances = [];
  List<dynamic> get cachedAgentInstances => _cachedAgentInstances;
  set cachedAgentInstances(List<dynamic> value) {
    _cachedAgentInstances = value;
    prefs.setString('ff_cachedAgentInstances', jsonEncode(value));
    debugLogAppState(this);
  }

  DateTime? _cachedAgentInstancesTimestamp;
  DateTime? get cachedAgentInstancesTimestamp => _cachedAgentInstancesTimestamp;
  set cachedAgentInstancesTimestamp(DateTime? value) {
    _cachedAgentInstancesTimestamp = value;
    if (value != null) {
      prefs.setString('ff_cachedAgentInstancesTimestamp', value.toIso8601String());
    } else {
      prefs.remove('ff_cachedAgentInstancesTimestamp');
    }
    debugLogAppState(this);
  }

  // Cached agents
  List<dynamic> _cachedAgents = [];
  List<dynamic> get cachedAgents => _cachedAgents;
  set cachedAgents(List<dynamic> value) {
    _cachedAgents = value;
    prefs.setString('ff_cachedAgents', jsonEncode(value));
    debugLogAppState(this);
  }

  DateTime? _cachedAgentsTimestamp;
  DateTime? get cachedAgentsTimestamp => _cachedAgentsTimestamp;
  set cachedAgentsTimestamp(DateTime? value) {
    _cachedAgentsTimestamp = value;
    if (value != null) {
      prefs.setString('ff_cachedAgentsTimestamp', value.toIso8601String());
    } else {
      prefs.remove('ff_cachedAgentsTimestamp');
    }
    debugLogAppState(this);
  }

  DateTime? _cachedMachinesTimestamp;
  DateTime? get cachedMachinesTimestamp => _cachedMachinesTimestamp;
  set cachedMachinesTimestamp(DateTime? value) {
    _cachedMachinesTimestamp = value;
    if (value != null) {
      prefs.setString('ff_cachedMachinesTimestamp', value.toIso8601String());
    } else {
      prefs.remove('ff_cachedMachinesTimestamp');
    }
    debugLogAppState(this);
  }

  /// Clear all user data and cached sessions
  /// Use this when user logs out or deletes account
  void clearAllUserData() {
    // Clear user data
    user = UserStruct();
    credit = CreditStruct();
    creditTransactions = [];
    surveys = [];
    setting = SettingStruct();

    // Clear cached sessions
    cachedAgentInstances = [];
    cachedAgentInstancesTimestamp = null;
    cachedAgents = [];
    cachedAgentsTimestamp = null;
    cachedMachines = [];
    cachedMachinesTimestamp = null;
    clearLastWebPreviewUrl();
    setLastWebPreviewDesktopMode(false);

    // Reset the getting-started checklist so a different account on this device
    // starts fresh (progress is per-account, not per-device).
    gettingStartedActivated = false;
    gettingStartedDismissed = false;
    gettingStartedCollapsed = false;
  }

  Map<String, DebugDataField> toDebugSerializableMap() => {
        'setting': debugSerializeParam(
          setting,
          ParamType.DataStruct,
          link:
              'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=appValues&appValuesTab=state',
          searchReference:
              'reference=Ci0KEwoHc2V0dGluZxIIaHRlbXJydWdyFggUKhISEAoHU2V0dGluZxIFcGkzNXdaB3NldHRpbmc=',
          name: 'Setting',
          nullable: false,
        ),
        'user': debugSerializeParam(
          user,
          ParamType.DataStruct,
          link:
              'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=appValues&appValuesTab=state',
          searchReference:
              'reference=CicKEAoEdXNlchIINGt5bjdkdXByEwgUKg8SDQoEVXNlchIFeXl1c2ZaBHVzZXI=',
          name: 'User',
          nullable: false,
        ),
        'surveys': debugSerializeParam(
          surveys,
          ParamType.DataStruct,
          isList: true,
          link:
              'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=appValues&appValuesTab=state',
          searchReference:
              'reference=Ci4KEwoHc3VydmV5cxIIMDlkc2p6cGhyFxICCBQqERIPCgZTdXJ2ZXkSBW9sMHluWgdzdXJ2ZXlz',
          name: 'Survey',
          nullable: false,
        ),
        'appVersion': debugSerializeParam(
          appVersion,
          ParamType.String,
          link:
              'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=appValues&appValuesTab=state',
          searchReference:
              'reference=ChwKFgoKYXBwVmVyc2lvbhIIN2dteW9zYmZyAggDWgphcHBWZXJzaW9u',
          name: 'String',
          nullable: false,
        ),
        'credit': debugSerializeParam(
          credit,
          ParamType.DataStruct,
          link:
              'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=appValues&appValuesTab=state',
          searchReference:
              'reference=CisKEgoGY3JlZGl0Egh5Mno3MmY3d3IVCBQqERIPCgZDcmVkaXQSBWFrbHYyWgZjcmVkaXQ=',
          name: 'Credit',
          nullable: false,
        ),
        'creditTransactions': debugSerializeParam(
          creditTransactions,
          ParamType.DataStruct,
          isList: true,
          link:
              'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=appValues&appValuesTab=state',
          searchReference:
              'reference=CkQKHgoSY3JlZGl0VHJhbnNhY3Rpb25zEghva3I0amtsZ3IiEgIIFCocEhoKEUNyZWRpdFRyYW5zYWN0aW9uEgU4OHIxZVoSY3JlZGl0VHJhbnNhY3Rpb25z',
          name: 'CreditTransaction',
          nullable: false,
        ),
        'pendingDeletions': debugSerializeParam(
          pendingDeletions,
          ParamType.DataStruct,
          isList: true,
          link:
              'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=appValues&appValuesTab=state',
          searchReference:
              'reference=CkAKHAoQcGVuZGluZ0RlbGV0aW9ucxIINGE5ZGl2ajlyHhICCBQqGBIWCg1Mb2NhbERlbGV0aW9uEgVrZ252dHoAWhBwZW5kaW5nRGVsZXRpb25z',
          name: 'LocalDeletion',
          nullable: false,
        )
      };
}

class AnalyticsFlags {
  AnalyticsFlags({
    this.hasSentFirstMobileMessage = false,
    this.hasCreatedFirstRemoteSession = false,
  });

  bool hasSentFirstMobileMessage;
  bool hasCreatedFirstRemoteSession;

  factory AnalyticsFlags.fromJson(Map<String, dynamic> json) => AnalyticsFlags(
        hasSentFirstMobileMessage: json['hasSentFirstMobileMessage'] as bool? ?? false,
        hasCreatedFirstRemoteSession: json['hasCreatedFirstRemoteSession'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'hasSentFirstMobileMessage': hasSentFirstMobileMessage,
        'hasCreatedFirstRemoteSession': hasCreatedFirstRemoteSession,
      };
}

class UserPreferences {
  UserPreferences({
    this.newSessionMachineId,
    this.newSessionAgentType,
    this.newSessionDirectory,
    this.newSessionWorktree,
    this.homeFilterGroupBy = 'Time',
    this.homeFilterStatus = 'All',
  });

  String? newSessionMachineId;
  String? newSessionAgentType;
  // Working directory last used with [newSessionMachineId]; restored only when
  // that machine is re-selected, else the machine's own default stands.
  String? newSessionDirectory;
  // Worktree last used with [newSessionMachineId] + [newSessionDirectory], as
  // {mode, path, branch}; restored only when both still match ('none' clears it
  // rather than being stored). Loosely typed to keep this struct dependency-free.
  Map<String, dynamic>? newSessionWorktree;
  String homeFilterGroupBy;
  String homeFilterStatus;

  factory UserPreferences.fromJson(Map<String, dynamic> json) => UserPreferences(
        newSessionMachineId: json['newSessionMachineId'] as String?,
        newSessionAgentType: json['newSessionAgentType'] as String?,
        newSessionDirectory: json['newSessionDirectory'] as String?,
        newSessionWorktree: (json['newSessionWorktree'] as Map?)?.cast<String, dynamic>(),
        homeFilterGroupBy: json['homeFilterGroupBy'] as String? ?? 'Time',
        homeFilterStatus: json['homeFilterStatus'] as String? ?? 'All',
      );

  Map<String, dynamic> toJson() => {
        if (newSessionMachineId != null) 'newSessionMachineId': newSessionMachineId,
        if (newSessionAgentType != null) 'newSessionAgentType': newSessionAgentType,
        if (newSessionDirectory != null) 'newSessionDirectory': newSessionDirectory,
        if (newSessionWorktree != null) 'newSessionWorktree': newSessionWorktree,
        'homeFilterGroupBy': homeFilterGroupBy,
        'homeFilterStatus': homeFilterStatus,
      };
}

void _safeInit(Function() initializeField) {
  try {
    initializeField();
  } catch (_) {}
}

Future _safeInitAsync(Function() initializeField) async {
  try {
    await initializeField();
  } catch (_) {}
}
