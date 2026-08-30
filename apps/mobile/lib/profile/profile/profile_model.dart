import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/profile/refer_friends/refer_friends_widget.dart';
import 'dart:math';
import 'dart:ui';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/custom_functions.dart' as functions;
import '/index.dart';
import 'profile_widget.dart' show ProfileWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

class ProfileModel extends FlutterFlowModel<ProfileWidget> {
  ///  State fields for stateful widgets in this page.

  // Stores action output result for [Custom Action - getSuperWallUserId] action in Profile widget.
  String? _superWallUserId;
  set superWallUserId(String? value) {
    _superWallUserId = value;
    debugLogWidgetClass(this);
  }

  String? get superWallUserId => _superWallUserId;

  // Stores action output result for [Custom Action - getRevenueCatUserId] action in Profile widget.
  String? _revenueCatUserId;
  set revenueCatUserId(String? value) {
    _revenueCatUserId = value;
    debugLogWidgetClass(this);
  }

  String? get revenueCatUserId => _revenueCatUserId;

  final Map<String, DebugDataField> debugGeneratorVariables = {};
  final Map<String, DebugDataField> debugBackendQueries = {};
  final Map<String, FlutterFlowModel> widgetBuilderComponents = {};
  @override
  void initState(BuildContext context) {
    debugLogWidgetClass(this);
  }

  @override
  void dispose() {}

  @override
  WidgetClassDebugData toWidgetClassDebugData() => WidgetClassDebugData(
        actionOutputs: {
          'superWallUserId': debugSerializeParam(
            superWallUserId,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Profile',
            name: 'String',
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=Profile',
        searchReference: 'reference=OgdQcm9maWxlUAFaB1Byb2ZpbGU=',
        widgetClassName: 'Profile',
      );
}
