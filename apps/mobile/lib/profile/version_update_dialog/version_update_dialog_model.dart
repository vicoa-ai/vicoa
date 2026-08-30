import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'dart:ui';
import 'version_update_dialog_widget.dart' show VersionUpdateDialogWidget;
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class VersionUpdateDialogModel
    extends FlutterFlowModel<VersionUpdateDialogWidget> {
  ///  State fields for stateful widgets in this component.

  // State field(s) for Checkbox widget.
  late LoggableMap<String, bool> _checkboxValueMap1 = LoggableMap({});
  set checkboxValueMap1(Map<String, bool> value) {
    if (value != null) {
      _checkboxValueMap1 = LoggableMap(value);
    }

    debugLogWidgetClass(this);
  }

  Map<String, bool> get checkboxValueMap1 =>
      _checkboxValueMap1?..logger = () => debugLogWidgetClass(this);

  List<String> get checkboxCheckedItems1 => checkboxValueMap1.entries
      .where((e) => e.value)
      .map((e) => e.key)
      .toList();

  // State field(s) for Checkbox widget.
  late LoggableMap<String, bool> _checkboxValueMap2 = LoggableMap({});
  set checkboxValueMap2(Map<String, bool> value) {
    if (value != null) {
      _checkboxValueMap2 = LoggableMap(value);
    }

    debugLogWidgetClass(this);
  }

  Map<String, bool> get checkboxValueMap2 =>
      _checkboxValueMap2?..logger = () => debugLogWidgetClass(this);

  List<String> get checkboxCheckedItems2 => checkboxValueMap2.entries
      .where((e) => e.value)
      .map((e) => e.key)
      .toList();

  // State field(s) for Checkbox widget.
  late LoggableMap<String, bool> _checkboxValueMap3 = LoggableMap({});
  set checkboxValueMap3(Map<String, bool> value) {
    if (value != null) {
      _checkboxValueMap3 = LoggableMap(value);
    }

    debugLogWidgetClass(this);
  }

  Map<String, bool> get checkboxValueMap3 =>
      _checkboxValueMap3?..logger = () => debugLogWidgetClass(this);

  List<String> get checkboxCheckedItems3 => checkboxValueMap3.entries
      .where((e) => e.value)
      .map((e) => e.key)
      .toList();

  // State field(s) for Checkbox widget.
  late LoggableMap<String, bool> _checkboxValueMap4 = LoggableMap({});
  set checkboxValueMap4(Map<String, bool> value) {
    if (value != null) {
      _checkboxValueMap4 = LoggableMap(value);
    }

    debugLogWidgetClass(this);
  }

  Map<String, bool> get checkboxValueMap4 =>
      _checkboxValueMap4?..logger = () => debugLogWidgetClass(this);

  List<String> get checkboxCheckedItems4 => checkboxValueMap4.entries
      .where((e) => e.value)
      .map((e) => e.key)
      .toList();

  // State field(s) for Checkbox widget.
  late LoggableMap<String, bool> _checkboxValueMap5 = LoggableMap({});
  set checkboxValueMap5(Map<String, bool> value) {
    if (value != null) {
      _checkboxValueMap5 = LoggableMap(value);
    }

    debugLogWidgetClass(this);
  }

  Map<String, bool> get checkboxValueMap5 =>
      _checkboxValueMap5?..logger = () => debugLogWidgetClass(this);

  List<String> get checkboxCheckedItems5 => checkboxValueMap5.entries
      .where((e) => e.value)
      .map((e) => e.key)
      .toList();

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
          'updates': debugSerializeParam(
            widget?.updates,
            ParamType.String,
            isList: true,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=versionUpdateDialog',
            searchReference:
                'reference=ShsKEQoHdXBkYXRlcxIGNW1jYjRhcgYSAggDIABQAFoHdXBkYXRlcw==',
            name: 'String',
            nullable: true,
          )
        }.withoutNulls,
        widgetStates: {
          'checkboxCheckedItems1': debugSerializeParam(
            checkboxCheckedItems1,
            ParamType.String,
            isList: true,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=versionUpdateDialog',
            name: 'String',
            nullable: true,
          ),
          'checkboxCheckedItems2': debugSerializeParam(
            checkboxCheckedItems2,
            ParamType.String,
            isList: true,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=versionUpdateDialog',
            name: 'String',
            nullable: true,
          ),
          'checkboxCheckedItems3': debugSerializeParam(
            checkboxCheckedItems3,
            ParamType.String,
            isList: true,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=versionUpdateDialog',
            name: 'String',
            nullable: true,
          ),
          'checkboxCheckedItems4': debugSerializeParam(
            checkboxCheckedItems4,
            ParamType.String,
            isList: true,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=versionUpdateDialog',
            name: 'String',
            nullable: true,
          ),
          'checkboxCheckedItems5': debugSerializeParam(
            checkboxCheckedItems5,
            ParamType.String,
            isList: true,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=versionUpdateDialog',
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=versionUpdateDialog',
        searchReference:
            'reference=OhN2ZXJzaW9uVXBkYXRlRGlhbG9nUABaE3ZlcnNpb25VcGRhdGVEaWFsb2c=',
        widgetClassName: 'versionUpdateDialog',
      );
}
