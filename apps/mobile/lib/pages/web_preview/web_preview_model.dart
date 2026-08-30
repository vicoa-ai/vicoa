import '/flutter_flow/flutter_flow_util.dart';
import 'web_preview_widget.dart' show WebPreviewWidget;
import 'package:flutter/material.dart';

class WebPreviewModel extends FlutterFlowModel<WebPreviewWidget> {
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=WebPreview',
        searchReference: 'reference=DUMMY_WEB_PREVIEW',
        widgetClassName: 'WebPreview',
      );
}
