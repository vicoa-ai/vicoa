import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'dart:ui';
import 'gift_dialog_widget.dart' show GiftDialogWidget;
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lottie/lottie.dart';
import 'package:provider/provider.dart';

class GiftDialogModel extends FlutterFlowModel<GiftDialogWidget> {
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
          'text': debugSerializeParam(
            widget?.text,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=giftDialog',
            searchReference:
                'reference=ShYKDgoEdGV4dBIGc3RlbGJkcgQIAyABUABaBHRleHQ=',
            name: 'String',
            nullable: true,
          ),
          'buttonText': debugSerializeParam(
            widget?.buttonText,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=giftDialog',
            searchReference:
                'reference=ShwKFAoKYnV0dG9uVGV4dBIGNTFvc2Z2cgQIAyABUABaCmJ1dHRvblRleHQ=',
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=giftDialog',
        searchReference: 'reference=OgpnaWZ0RGlhbG9nUABaCmdpZnREaWFsb2c=',
        widgetClassName: 'giftDialog',
      );
}
