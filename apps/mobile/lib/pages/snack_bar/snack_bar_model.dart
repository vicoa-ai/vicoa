import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'dart:ui';
import 'snack_bar_widget.dart' show SnackBarWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class SnackBarModel extends FlutterFlowModel<SnackBarWidget> {
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
          'content': debugSerializeParam(
            widget?.content,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=snackBar',
            searchReference:
                'reference=ShkKEQoHY29udGVudBIGNmEwNHB4cgQIAyABUABaB2NvbnRlbnQ=',
            name: 'String',
            nullable: true,
          ),
          'waitTime': debugSerializeParam(
            widget?.waitTime,
            ParamType.int,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=snackBar',
            searchReference:
                'reference=SiQKEgoId2FpdFRpbWUSBnRiNXN1eCoGEgQxNTAwcgQIASAAegBQAFoId2FpdFRpbWU=',
            name: 'int',
            nullable: false,
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=snackBar',
        searchReference: 'reference=OghzbmFja0JhclAAWghzbmFja0Jhcg==',
        widgetClassName: 'snackBar',
      );
}
