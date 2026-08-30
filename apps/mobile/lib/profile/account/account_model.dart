import '/auth/base_auth_user_provider.dart';
import '/auth/supabase_auth/auth_util.dart';
import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import 'dart:math';
import 'dart:ui';
import '/custom_code/actions/index.dart' as actions;
import '/index.dart';
import 'account_widget.dart' show AccountWidget;
import 'package:easy_debounce/easy_debounce.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class AccountModel extends FlutterFlowModel<AccountWidget> {
  ///  Local state fields for this page.

  String _name = 'Guest';
  set name(String value) {
    _name = value;
    debugLogWidgetClass(this);
  }

  String get name => _name;

  bool _updated = false;
  set updated(bool value) {
    _updated = value;
    debugLogWidgetClass(this);
  }

  bool get updated => _updated;

  ///  State fields for stateful widgets in this page.

  final formKey = GlobalKey<FormState>();
  // State field(s) for TextField widget.
  FocusNode? textFieldFocusNode1;
  TextEditingController? textController1;
  String? Function(BuildContext, String?)? textController1Validator;
  String? _textController1Validator(BuildContext context, String? val) {
    if (val == null || val.isEmpty) {
      return 'Field is required';
    }

    if (val.length < 2) {
      return 'Requires at least 2 characters.';
    }

    return null;
  }

  // State field(s) for TextField widget.
  FocusNode? textFieldFocusNode2;
  TextEditingController? textController2;
  String? Function(BuildContext, String?)? textController2Validator;
  // Stores action output result for [Alert Dialog - Custom Dialog] action in Container widget.
  bool? _confirmed;
  set confirmed(bool? value) {
    _confirmed = value;
    debugLogWidgetClass(this);
  }

  bool? get confirmed => _confirmed;

  final Map<String, DebugDataField> debugGeneratorVariables = {};
  final Map<String, DebugDataField> debugBackendQueries = {};
  final Map<String, FlutterFlowModel> widgetBuilderComponents = {};
  @override
  void initState(BuildContext context) {
    textController1Validator = _textController1Validator;

    debugLogWidgetClass(this);
  }

  @override
  void dispose() {
    textFieldFocusNode1?.dispose();
    textController1?.dispose();

    textFieldFocusNode2?.dispose();
    textController2?.dispose();
  }

  @override
  WidgetClassDebugData toWidgetClassDebugData() => WidgetClassDebugData(
        localStates: {
          'name': debugSerializeParam(
            name,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Account',
            searchReference:
                'reference=QhkKDQoEbmFtZRIFcGQ5bWwqAhIAcgQIAyABUAFaBG5hbWViB0FjY291bnQ=',
            name: 'String',
            nullable: false,
          ),
          'updated': debugSerializeParam(
            updated,
            ParamType.bool,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Account',
            searchReference:
                'reference=QiEKEAoHdXBkYXRlZBIFZzZoc3YqBxIFZmFsc2VyBAgFIAFQAVoHdXBkYXRlZGIHQWNjb3VudA==',
            name: 'bool',
            nullable: false,
          )
        },
        widgetStates: {
          'textFieldText1': debugSerializeParam(
            textController1?.text,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Account',
            name: 'String',
            nullable: true,
          ),
          'textFieldText2': debugSerializeParam(
            textController2?.text,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Account',
            name: 'String',
            nullable: true,
          )
        },
        actionOutputs: {
          'confirmed': debugSerializeParam(
            confirmed,
            ParamType.bool,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Account',
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=Account',
        searchReference: 'reference=OgdBY2NvdW50UAFaB0FjY291bnQ=',
        widgetClassName: 'Account',
      );
}
