import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_drop_down.dart';
import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_video_player.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/form_field_controller.dart';
import 'dart:math';
import 'dart:ui';
import '/custom_code/actions/index.dart' as actions;
import 'tutorial_widget.dart' show TutorialWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class TutorialModel extends FlutterFlowModel<TutorialWidget> {
  ///  Local state fields for this page.

  String _videoPath = 'https://i.imgur.com/V4EpW3y.mp4';
  set videoPath(String value) {
    _videoPath = value;
    debugLogWidgetClass(this);
  }

  String get videoPath => _videoPath;

  ///  State fields for stateful widgets in this page.

  // Stores action output result for [Custom Action - apiGetTutorialVideo] action in Tutorial widget.
  String? _url;
  set url(String? value) {
    _url = value;
    debugLogWidgetClass(this);
  }

  String? get url => _url;

  // State field(s) for DropDown widget.
  String? _dropDownValue;
  set dropDownValue(String? value) {
    _dropDownValue = value;
    debugLogWidgetClass(this);
  }

  String? get dropDownValue => _dropDownValue;

  FormFieldController<String>? dropDownValueController;

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
          'videoPath': debugSerializeParam(
            videoPath,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Tutorial',
            searchReference:
                'reference=QiMKEgoJdmlkZW9QYXRoEgUxbDB1ZyoHEgVmYWxzZXIECAogAVABWgl2aWRlb1BhdGhiCFR1dG9yaWFs',
            name: 'String',
            nullable: false,
          )
        },
        widgetStates: {
          'dropDownValue': debugSerializeParam(
            dropDownValue,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Tutorial',
            name: 'String',
            nullable: true,
          )
        },
        actionOutputs: {
          'url': debugSerializeParam(
            url,
            ParamType.String,
            link:
                'https://app.flutterflow.io/project/vicoa-ivq0oy?tab=uiBuilder&page=Tutorial',
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
            'https://app.flutterflow.io/project/vicoa-ivq0oy/tab=uiBuilder&page=Tutorial',
        searchReference: 'reference=OghUdXRvcmlhbFABWghUdXRvcmlhbA==',
        widgetClassName: 'Tutorial',
      );
}
