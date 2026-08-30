import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'dart:ui';
import 'confirm_dialog_widget.dart' show ConfirmDialogWidget;
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class ConfirmDialogModel extends FlutterFlowModel<ConfirmDialogWidget> {
  final Map<String, DebugDataField> debugGeneratorVariables = {};
  final Map<String, DebugDataField> debugBackendQueries = {};
  final Map<String, FlutterFlowModel> widgetBuilderComponents = {};
  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {}

  @override
  WidgetClassDebugData toWidgetClassDebugData() => WidgetClassDebugData(
        widgetParameters: {
          'title': debugSerializeParam(
            widget?.title,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=confirmDialog',
            searchReference:
                'reference=ShcKDwoFdGl0bGUSBjVtY2I0YXIECAMgAVAAWgV0aXRsZQ==',
            name: 'String',
            nullable: true,
          ),
          'content': debugSerializeParam(
            widget?.content,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=confirmDialog',
            searchReference:
                'reference=ShkKEQoHY29udGVudBIGNmEwNHB4cgQIAyABUABaB2NvbnRlbnQ=',
            name: 'String',
            nullable: true,
          )
        }.withoutNulls,
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=confirmDialog',
        searchReference:
            'reference=Og1jb25maXJtRGlhbG9nUABaDWNvbmZpcm1EaWFsb2c=',
        widgetClassName: 'confirmDialog',
      );
}
