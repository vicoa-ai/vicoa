import '/flutter_flow/flutter_flow_util.dart';
import 'report_issue_dialog_widget.dart' show ReportIssueDialogWidget;
import 'package:flutter/material.dart';

class ReportIssueDialogModel
    extends FlutterFlowModel<ReportIssueDialogWidget> {
  FocusNode? textFieldFocusNode;
  TextEditingController? textController;
  String? Function(BuildContext, String?)? textControllerValidator;

  final Map<String, DebugDataField> debugGeneratorVariables = {};
  final Map<String, DebugDataField> debugBackendQueries = {};
  final Map<String, FlutterFlowModel> widgetBuilderComponents = {};

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    textFieldFocusNode?.dispose();
    textController?.dispose();
  }

  @override
  WidgetClassDebugData toWidgetClassDebugData() => WidgetClassDebugData(
        widgetParameters: {},
        generatorVariables: debugGeneratorVariables,
        backendQueries: debugBackendQueries,
        componentStates: {
          ...widgetBuilderComponents.map(
            (key, value) => MapEntry(key, value.toWidgetClassDebugData()),
          ),
        }.withoutNulls,
        widgetClassName: 'reportIssueDialog',
      );
}
