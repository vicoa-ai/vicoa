import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'dart:ui';
import '/custom_code/actions/index.dart' as actions;
import '/index.dart';
import 'no_credit_sheet_widget.dart' show NoCreditSheetWidget;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class NoCreditSheetModel extends FlutterFlowModel<NoCreditSheetWidget> {
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
          'paywall': debugSerializeParam(
            widget?.paywall,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=noCreditSheet',
            searchReference:
                'reference=ShkKEQoHcGF5d2FsbBIGYjBzcjh2cgQIAyABUABaB3BheXdhbGw=',
            name: 'String',
            nullable: true,
          ),
          'creditsNeeded': debugSerializeParam(
            widget?.creditsNeeded,
            ParamType.int,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=noCreditSheet',
            searchReference:
                'reference=Sh8KFwoNY3JlZGl0c05lZWRlZBIGcTBkbWRtcgQIASAAUABaDWNyZWRpdHNOZWVkZWQ=',
            name: 'int',
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=noCreditSheet',
        searchReference:
            'reference=Og1ub0NyZWRpdFNoZWV0UABaDW5vQ3JlZGl0U2hlZXQ=',
        widgetClassName: 'noCreditSheet',
      );
}
