// ignore_for_file: unnecessary_getters_setters

import '/backend/schema/util/schema_util.dart';

import 'index.dart';
import '/flutter_flow/flutter_flow_util.dart';

class SurveyStruct extends BaseStruct {
  SurveyStruct({
    String? question,
    List<String>? options,
    List<String>? answers,
    bool? isMultiSelect,
  })  : _question = question,
        _options = options != null ? LoggableList(options) : null,
        _answers = answers != null ? LoggableList(answers) : null,
        _isMultiSelect = isMultiSelect;

  // "question" field.
  String? _question;
  String get question => _question ?? '';
  set question(String? val) {
    _question = val;
    debugLog();
  }

  bool hasQuestion() => _question != null;

  // "options" field.
  LoggableList<String>? _options;
  List<String> get options =>
      (_options ?? LoggableList(const []))..logger = logger;
  set options(List<String>? val) {
    if (val != null) {
      _options = LoggableList(val);
    } else {
      _options = null;
    }
    debugLog();
  }

  void updateOptions(Function(List<String>) updateFn) {
    updateFn(_options ??= LoggableList([]));
    debugLog();
  }

  bool hasOptions() => _options != null;

  // "answers" field.
  LoggableList<String>? _answers;
  List<String> get answers =>
      (_answers ?? LoggableList(const []))..logger = logger;
  set answers(List<String>? val) {
    if (val != null) {
      _answers = LoggableList(val);
    } else {
      _answers = null;
    }
    debugLog();
  }

  void updateAnswers(Function(List<String>) updateFn) {
    updateFn(_answers ??= LoggableList([]));
    debugLog();
  }

  bool hasAnswers() => _answers != null;

  // "isMultiSelect" field.
  bool? _isMultiSelect;
  bool get isMultiSelect => _isMultiSelect ?? false;
  set isMultiSelect(bool? val) {
    _isMultiSelect = val;
    debugLog();
  }

  bool hasIsMultiSelect() => _isMultiSelect != null;

  static SurveyStruct fromMap(Map<String, dynamic> data) => SurveyStruct(
        question: data['question'] as String?,
        options: getDataList(data['options']),
        answers: getDataList(data['answers']),
        isMultiSelect: data['isMultiSelect'] as bool?,
      );

  static SurveyStruct? maybeFromMap(dynamic data) =>
      data is Map ? SurveyStruct.fromMap(data.cast<String, dynamic>()) : null;

  Map<String, dynamic> toMap() => {
        'question': _question,
        'options': _options,
        'answers': _answers,
        'isMultiSelect': _isMultiSelect,
      }.withoutNulls;

  @override
  Map<String, dynamic> toSerializableMap() => {
        'question': serializeParam(
          _question,
          ParamType.String,
        ),
        'options': serializeParam(
          _options,
          ParamType.String,
          isList: true,
        ),
        'answers': serializeParam(
          _answers,
          ParamType.String,
          isList: true,
        ),
        'isMultiSelect': serializeParam(
          _isMultiSelect,
          ParamType.bool,
        ),
      }.withoutNulls;

  static SurveyStruct fromSerializableMap(Map<String, dynamic> data) =>
      SurveyStruct(
        question: deserializeParam(
          data['question'],
          ParamType.String,
          false,
        ),
        options: deserializeParam<String>(
          data['options'],
          ParamType.String,
          true,
        ),
        answers: deserializeParam<String>(
          data['answers'],
          ParamType.String,
          true,
        ),
        isMultiSelect: deserializeParam(
          data['isMultiSelect'],
          ParamType.bool,
          false,
        ),
      );
  @override
  Map<String, DebugDataField> toDebugSerializableMap() => {
        'question': debugSerializeParam(
          question,
          ParamType.String,
          name: 'String',
          nullable: false,
        ),
        'options': debugSerializeParam(
          _options,
          ParamType.String,
          isList: true,
          name: 'String',
          nullable: false,
        ),
        'answers': debugSerializeParam(
          _answers,
          ParamType.String,
          isList: true,
          name: 'String',
          nullable: false,
        ),
        'isMultiSelect': debugSerializeParam(
          isMultiSelect,
          ParamType.bool,
          name: 'bool',
          nullable: false,
        ),
      };

  @override
  String toString() => 'SurveyStruct(${toMap()})';

  @override
  bool operator ==(Object other) {
    const listEquality = ListEquality();
    return other is SurveyStruct &&
        question == other.question &&
        listEquality.equals(options, other.options) &&
        listEquality.equals(answers, other.answers) &&
        isMultiSelect == other.isMultiSelect;
  }

  @override
  int get hashCode =>
      const ListEquality().hash([question, options, answers, isMultiSelect]);
}

SurveyStruct createSurveyStruct({
  String? question,
  bool? isMultiSelect,
}) =>
    SurveyStruct(
      question: question,
      isMultiSelect: isMultiSelect,
    );
