import '/auth/base_auth_user_provider.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/gift_dialog/gift_dialog_widget.dart';
import '/pages/info_dialog/info_dialog_widget.dart';
import 'dart:ui';
import '/custom_code/actions/index.dart' as actions;
import '/index.dart';
import 'refer_friends_widget.dart' show ReferFriendsWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class ReferFriendsModel extends FlutterFlowModel<ReferFriendsWidget> {
  ///  Local state fields for this component.

  bool _showCopied = false;
  set showCopied(bool value) {
    _showCopied = value;
    debugLogWidgetClass(this);
  }

  bool get showCopied => _showCopied;

  ///  State fields for stateful widgets in this component.

  // Stores action output result for [Custom Action - supabaseClaimReferrerReward] action in referFriends widget.
  int? _credits;
  set credits(int? value) {
    _credits = value;
    debugLogWidgetClass(this);
  }

  int? get credits => _credits;

  // Stores action output result for [Custom Action - supabaseGenerateReferralCode] action in Button widget.
  String? _referralCode;
  set referralCode(String? value) {
    _referralCode = value;
    debugLogWidgetClass(this);
  }

  String? get referralCode => _referralCode;

  // Stores action output result for [Custom Action - supabaseGetReferralCount] action in referFriends widget.
  int? _invitedFriendsCount;
  set invitedFriendsCount(int? value) {
    _invitedFriendsCount = value;
    debugLogWidgetClass(this);
  }

  int? get invitedFriendsCount => _invitedFriendsCount;

  final Map<String, DebugDataField> debugGeneratorVariables = {};
  final Map<String, DebugDataField> debugBackendQueries = {};
  final Map<String, FlutterFlowModel> widgetBuilderComponents = {};
  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {}

  @override
  WidgetClassDebugData toWidgetClassDebugData() => WidgetClassDebugData(
        localStates: {
          'showCopied': debugSerializeParam(
            showCopied,
            ParamType.bool,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=referFriends',
            searchReference:
                'reference=QiQKEwoKc2hvd0NvcGllZBIFZmE1ZjMqBxIFZmFsc2VyBAgFIAFQAFoKc2hvd0NvcGllZGIMcmVmZXJGcmllbmRz',
            name: 'bool',
            nullable: false,
          )
        },
        actionOutputs: {
          'credits': debugSerializeParam(
            credits,
            ParamType.int,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=referFriends',
            name: 'int',
            nullable: true,
          ),
          'referralCode': debugSerializeParam(
            referralCode,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=referFriends',
            name: 'String',
            nullable: true,
          ),
          'invitedFriendsCount': debugSerializeParam(
            invitedFriendsCount,
            ParamType.int,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=referFriends',
            name: 'int',
            nullable: true,
          )
        },
        generatorVariables: debugGeneratorVariables,
        backendQueries: debugBackendQueries,
        componentStates: {
          ...widgetBuilderComponents.map(
            (key, value) => MapEntry(
              key,
              value.toWidgetClassDebugData(),
            ),
          ),
        }.withoutNulls,
        link:
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=referFriends',
        searchReference: 'reference=OgxyZWZlckZyaWVuZHNQAFoMcmVmZXJGcmllbmRz',
        widgetClassName: 'referFriends',
      );
}
