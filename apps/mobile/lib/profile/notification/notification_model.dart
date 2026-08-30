import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'dart:math';
import 'dart:ui';
import '/custom_code/actions/index.dart' as actions;
import '/index.dart';
import 'notification_widget.dart' show NotificationWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class NotificationModel extends FlutterFlowModel<NotificationWidget> {
  ///  Local state fields for this page.

  bool _stockCheck = false;
  set stockCheck(bool value) {
    _stockCheck = value;
    debugLogWidgetClass(this);
  }

  bool get stockCheck => _stockCheck;

  ///  State fields for stateful widgets in this page.

  // Stores action output result for [Custom Action - notificationRequestPermission] action in Notification widget.
  bool? _enabled;
  set enabled(bool? value) {
    _enabled = value;
    debugLogWidgetClass(this);
  }

  bool? get enabled => _enabled;

  // Stores action output result for [Custom Action - notificationRequestPermission] action in Notification widget.
  bool? _notificationEnabled;
  set notificationEnabled(bool? value) {
    _notificationEnabled = value;
    debugLogWidgetClass(this);
  }

  bool? get notificationEnabled => _notificationEnabled;

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
        localStates: {
          'stockCheck': debugSerializeParam(
            stockCheck,
            ParamType.bool,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Notification',
            searchReference:
                'reference=QiQKEwoKc3RvY2tDaGVjaxIFcHcwenYqBxIFZmFsc2VyBAgFIAFQAVoKc3RvY2tDaGVja2IMTm90aWZpY2F0aW9u',
            name: 'bool',
            nullable: false,
          )
        },
        actionOutputs: {
          'enabled': debugSerializeParam(
            enabled,
            ParamType.bool,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Notification',
            name: 'bool',
            nullable: true,
          ),
          'notificationEnabled': debugSerializeParam(
            notificationEnabled,
            ParamType.bool,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Notification',
            name: 'bool',
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=Notification',
        searchReference: 'reference=OgxOb3RpZmljYXRpb25QAVoMTm90aWZpY2F0aW9u',
        widgetClassName: 'Notification',
      );
}
