import '/flutter_flow/flutter_flow_util.dart';
import 'rename_dialog_widget.dart' show RenameDialogWidget;
import 'package:flutter/material.dart';

class RenameDialogModel extends FlutterFlowModel<RenameDialogWidget> {
  // State field(s) for TextField widget.
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
        widgetParameters: {
          'title': debugSerializeParam(
            widget?.title,
            ParamType.String,
            name: 'String',
            nullable: true,
          ),
          'initialValue': debugSerializeParam(
            widget?.initialValue,
            ParamType.String,
            name: 'String',
            nullable: true,
          ),
          'placeholder': debugSerializeParam(
            widget?.placeholder,
            ParamType.String,
            name: 'String',
            nullable: true,
          ),
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
        widgetClassName: 'renameDialog',
      );
}