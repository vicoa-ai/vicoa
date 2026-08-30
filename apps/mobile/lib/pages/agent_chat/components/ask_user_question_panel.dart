import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/app_locale.dart';
import '/l10n/app_localizations.dart';
import 'package:flutter/material.dart';

class AskUserQuestionOption {
  final String label;
  final String description;

  const AskUserQuestionOption({
    required this.label,
    required this.description,
  });
}

class AskUserQuestionItem {
  final String question;
  final String header;
  final List<AskUserQuestionOption> options;
  final bool multiSelect;

  const AskUserQuestionItem({
    required this.question,
    required this.header,
    required this.options,
    required this.multiSelect,
  });
}

class AskUserQuestionPayload {
  final String? toolUseId;
  final String? prompt;
  final List<AskUserQuestionItem> questions;

  const AskUserQuestionPayload({
    required this.toolUseId,
    required this.prompt,
    required this.questions,
  });
}

class AskUserQuestionAnswer {
  final String mode;
  final int? optionIndex;
  final List<int>? optionIndexes;
  final bool? questionMultiSelect;
  final int? optionCount;
  final String? text;

  const AskUserQuestionAnswer._({
    required this.mode,
    this.optionIndex,
    this.optionIndexes,
    this.questionMultiSelect,
    this.optionCount,
    this.text,
  });

  factory AskUserQuestionAnswer.option({
    int? optionIndex,
    List<int>? optionIndexes,
    bool questionMultiSelect = false,
    int? optionCount,
  }) {
    return AskUserQuestionAnswer._(
      mode: 'option',
      optionIndex: optionIndex,
      optionIndexes: optionIndexes,
      questionMultiSelect: questionMultiSelect,
      optionCount: optionCount,
    );
  }

  factory AskUserQuestionAnswer.text({
    required String text,
    int? optionCount,
  }) {
    return AskUserQuestionAnswer._(
      mode: 'text',
      text: text,
      optionCount: optionCount,
    );
  }

  Map<String, dynamic> toJson() {
    if (mode == 'text') {
      return {
        'mode': 'text',
        'text': text ?? '',
        if (optionCount != null) 'option_count': optionCount,
      };
    }

    return {
      'mode': 'option',
      if (optionIndex != null) 'option_index': optionIndex,
      if (optionIndexes != null) 'option_indexes': optionIndexes,
      if (questionMultiSelect != null) 'question_multi_select': questionMultiSelect,
      if (optionCount != null) 'option_count': optionCount,
    };
  }
}

class AskUserQuestionSubmitPayload {
  final String messageId;
  final List<AskUserQuestionAnswer> answers;
  final List<Map<String, String>>? displayAnswers;

  const AskUserQuestionSubmitPayload({
    required this.messageId,
    required this.answers,
    this.displayAnswers,
  });

  Map<String, dynamic> toJson() {
    return {
      'message_id': messageId,
      'answers': answers.map((answer) => answer.toJson()).toList(),
      if (displayAnswers != null) 'display_answers': displayAnswers,
    };
  }
}

AskUserQuestionPayload? parseAskUserQuestionPayload(dynamic message) {
  if (message is! Map) return null;
  final metadataRaw = message['message_metadata'];
  if (metadataRaw is! Map) return null;
  final askPayloadRaw = metadataRaw['ask_user_question'];
  if (askPayloadRaw is! Map) return null;
  final questionsRaw = askPayloadRaw['questions'];
  if (questionsRaw is! List || questionsRaw.isEmpty) return null;

  final questions = <AskUserQuestionItem>[];
  for (var i = 0; i < questionsRaw.length; i++) {
    final itemRaw = questionsRaw[i];
    if (itemRaw is! Map) continue;
    final question = (itemRaw['question'] ?? '').toString().trim();
    if (question.isEmpty) continue;

    final defaultHeader = tr().askUserQuestionPanelQuestionNumber(i + 1);
    final headerRaw = (itemRaw['header'] ?? defaultHeader).toString().trim();
    final header = headerRaw.isEmpty ? defaultHeader : headerRaw;

    final options = <AskUserQuestionOption>[];
    final optionsRaw = itemRaw['options'];
    if (optionsRaw is List) {
      for (final optionRaw in optionsRaw) {
        if (optionRaw is! Map) continue;
        final label = (optionRaw['label'] ?? '').toString().trim();
        if (label.isEmpty) continue;
        final description = (optionRaw['description'] ?? '').toString();
        options.add(AskUserQuestionOption(label: label, description: description));
      }
    }

    questions.add(
      AskUserQuestionItem(
        question: question,
        header: header,
        options: options,
        multiSelect: itemRaw['multi_select'] == true,
      ),
    );
  }

  if (questions.isEmpty) return null;

  return AskUserQuestionPayload(
    toolUseId: askPayloadRaw['tool_use_id']?.toString(),
    prompt: askPayloadRaw['prompt']?.toString(),
    questions: questions,
  );
}

class AskUserQuestionPanel extends StatefulWidget {
  const AskUserQuestionPanel({
    super.key,
    required this.messageId,
    required this.payload,
    this.onSubmit,
    this.onCancel,
    this.onTextInputFocusChanged,
    this.onRequestScrollToBottom,
    this.initialAnswers,
    this.onAnswersChanged,
  });

  final String messageId;
  final AskUserQuestionPayload payload;
  final Future<void> Function(AskUserQuestionSubmitPayload payload)? onSubmit;
  final Future<void> Function(String messageId)? onCancel;
  final ValueChanged<bool>? onTextInputFocusChanged;
  final VoidCallback? onRequestScrollToBottom;

  /// Previously-made selections to restore (e.g. when this panel's State is
  /// rebuilt after scrolling out of a lazy list). When non-null and matching
  /// the question count, these seed the panel instead of the defaults.
  final List<AskUserQuestionAnswer>? initialAnswers;

  /// Called whenever the user changes a selection, so the parent can persist
  /// the answers and pass them back via [initialAnswers] on rebuild.
  final ValueChanged<List<AskUserQuestionAnswer>>? onAnswersChanged;

  @override
  State<AskUserQuestionPanel> createState() => _AskUserQuestionPanelState();
}

class _AskUserQuestionPanelState extends State<AskUserQuestionPanel> {
  int _activeTab = 0;
  late List<AskUserQuestionAnswer> _answers;
  final Map<int, TextEditingController> _textControllers = {};
  final Map<int, FocusNode> _textFocusNodes = {};
  final Map<int, GlobalKey> _textFieldKeys = {};
  bool _isSubmitting = false;
  bool _isCancelling = false;
  bool _isAnyTextFieldFocused = false;
  bool _isDisposing = false;

  @override
  void initState() {
    super.initState();
    _resetAnswers();
  }

  @override
  void didUpdateWidget(covariant AskUserQuestionPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    final didQuestionsChange = oldWidget.payload.toolUseId != widget.payload.toolUseId || oldWidget.payload.questions.length != widget.payload.questions.length;
    if (didQuestionsChange) {
      _resetAnswers();
    }
  }

  void _resetAnswers() {
    _disposeTextInputs();
    // Restore prior selections when the parent provides them (survives State
    // recreation after the panel scrolls out of a lazy list).
    final restored = widget.initialAnswers;
    if (restored != null && restored.length == widget.payload.questions.length) {
      _answers = List.of(restored);
      _activeTab = 0;
      return;
    }
    _answers = widget.payload.questions.map((question) {
      if (question.options.isEmpty) {
        return AskUserQuestionAnswer.text(text: '');
      }
      if (question.multiSelect) {
        return AskUserQuestionAnswer.option(
          optionIndexes: const <int>[],
          questionMultiSelect: true,
          optionCount: question.options.length,
        );
      }
      return AskUserQuestionAnswer.option(
        optionIndex: 0,
        questionMultiSelect: false,
        optionCount: question.options.length,
      );
    }).toList();
    _activeTab = 0;
  }

  /// Notify the parent of the current answers so they survive a State rebuild.
  void _emitAnswersChanged() {
    widget.onAnswersChanged?.call(List.of(_answers));
  }

  @override
  void dispose() {
    _isDisposing = true;
    _disposeTextInputs();
    super.dispose();
  }

  void _disposeTextInputs() {
    _notifyTextInputFocusChanged(false);
    for (final controller in _textControllers.values) {
      controller.dispose();
    }
    for (final focusNode in _textFocusNodes.values) {
      focusNode.dispose();
    }
    _textControllers.clear();
    _textFocusNodes.clear();
    _textFieldKeys.clear();
  }

  TextEditingController _controllerForQuestion(int questionIndex) {
    if (_textControllers.containsKey(questionIndex)) {
      return _textControllers[questionIndex]!;
    }
    final controller = TextEditingController(text: _currentAnswerText(_answers[questionIndex]));
    _textControllers[questionIndex] = controller;
    return controller;
  }

  FocusNode _focusNodeForQuestion(int questionIndex) {
    if (_textFocusNodes.containsKey(questionIndex)) {
      return _textFocusNodes[questionIndex]!;
    }
    final focusNode = FocusNode(debugLabel: 'ask-user-question-$questionIndex');
    focusNode.addListener(_handleTextFieldFocusChange);
    _textFocusNodes[questionIndex] = focusNode;
    return focusNode;
  }

  void _handleTextFieldFocusChange() {
    final anyFocused = _textFocusNodes.values.any((node) => node.hasFocus);
    _notifyTextInputFocusChanged(anyFocused);
  }

  void _notifyTextInputFocusChanged(bool focused) {
    if (_isAnyTextFieldFocused == focused) return;
    _isAnyTextFieldFocused = focused;
    if (_isDisposing) {
      // The widget tree is locked during finalization — defer to the next frame
      // so the parent callback doesn't call setState while the tree is locked.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        widget.onTextInputFocusChanged?.call(focused);
      });
    } else {
      widget.onTextInputFocusChanged?.call(focused);
    }
  }

  GlobalKey _textFieldKeyForQuestion(int questionIndex) {
    if (_textFieldKeys.containsKey(questionIndex)) {
      return _textFieldKeys[questionIndex]!;
    }
    final key = GlobalKey();
    _textFieldKeys[questionIndex] = key;
    return key;
  }

  void _focusTextInput(int questionIndex) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final focusNode = _focusNodeForQuestion(questionIndex);
      focusNode.requestFocus();

      // Wait for keyboard to appear, then scroll to bottom and lock scroll
      Future.delayed(const Duration(milliseconds: 400), () {
        if (!mounted) return;
        widget.onRequestScrollToBottom?.call();
      });
    });
  }

  String _currentAnswerText(AskUserQuestionAnswer? answer) {
    if (answer == null || answer.mode != 'text') return '';
    return answer.text ?? '';
  }

  @override
  Widget build(BuildContext context) {
    const mutedBg = Colors.transparent;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final selectedBg = isDark
        ? FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.15)
        : FlutterFlowTheme.of(context).codeBlockBackground;
    final activeBg = selectedBg;

    return GestureDetector(
      onTap: () {},
      behavior: HitTestBehavior.translucent,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 12.0),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (var i = 0; i < widget.payload.questions.length; i++)
                  Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(0, 0, 8, 0),
                    child: _buildTabButton(
                      context,
                      label: widget.payload.questions[i].header,
                      icon: widget.payload.questions[i].multiSelect ? Icons.checklist_rounded : null,
                      active: _activeTab == i,
                      activeBg: activeBg,
                      mutedBg: mutedBg,
                      onTap: () => setState(() => _activeTab = i),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12.0),
          // IndexedStack keeps questions anchored to the top when switching tabs
          IndexedStack(
            index: _activeTab,
            alignment: Alignment.topCenter,
            children: [
              for (var i = 0; i < widget.payload.questions.length; i++)
                _buildQuestionTabWithoutTextField(context, i),
            ],
          ),
          // Text input rendered outside IndexedStack to avoid height jumps
          if (_answers[_activeTab].mode == 'text') ...[
            const SizedBox(height: 8.0),
            _buildTextInputField(context, _activeTab),
          ],
          const SizedBox(height: 16.0),
          _buildActionButtons(context),
        ],
      ),
    );
  }

  Widget _buildTabButton(
    BuildContext context, {
    required String label,
    required IconData? icon,
    required bool active,
    required Color activeBg,
    required Color mutedBg,
    required VoidCallback onTap,
  }) {
    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsetsDirectional.fromSTEB(10, 6, 10, 6),
        decoration: BoxDecoration(
          color: active ? activeBg : mutedBg,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: active ? 0.45 : 0.25),
            width: active ? 0.6 : 0.5,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(
                icon,
                size: 14,
                color: FlutterFlowTheme.of(context).primaryText.withValues(alpha: active ? 0.95 : 0.8),
              ),
              const SizedBox(width: 6),
            ],
            Text(
              label,
              style: FlutterFlowTheme.of(context).bodySmall.override(
                color: FlutterFlowTheme.of(context).primaryText,
                fontSize: 14,
                fontWeight: active ? FontWeight.w500 : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuestionTabWithoutTextField(BuildContext context, int questionIndex) {
    final question = widget.payload.questions[questionIndex];
    final answer = _answers[questionIndex];
    final isMultiSelect = question.multiSelect;
    final selectedIndexes = answer.mode == 'option' ? (answer.optionIndexes ?? const <int>[]) : const <int>[];

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          question.question,
          style: FlutterFlowTheme.of(context).bodyMedium.override(
            color: FlutterFlowTheme.of(context).primaryText,
            fontSize: 15,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10.0),
        for (var optionIndex = 0; optionIndex < question.options.length; optionIndex++)
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(0, 0, 0, optionIndex == question.options.length - 1 ? 0 : 8),
            child: _buildOptionButton(
              context,
              question: question,
              questionIndex: questionIndex,
              optionIndex: optionIndex,
              isSelected: answer.mode == 'option' && (isMultiSelect ? selectedIndexes.contains(optionIndex) : answer.optionIndex == optionIndex),
            ),
          ),
        const SizedBox(height: 8.0),
        _buildTypeSomethingButton(context, question, questionIndex),
      ],
    );
  }

  Widget _buildActionButtons(BuildContext context) {
    return Row(
      children: [
        FFButtonWidget(
          onPressed: _isSubmitting || _isCancelling
              ? null
              : () async {
                  setState(() => _isSubmitting = true);
                  final payload = AskUserQuestionSubmitPayload(
                    messageId: widget.messageId,
                    answers: _buildSubmitAnswers(),
                    displayAnswers: _buildDisplayAnswers(),
                  );
                  try {
                    debugPrint('[AskUserQuestion] Submitting answers: ${payload.toJson()}');
                    if (widget.onSubmit != null) {
                      await widget.onSubmit!(payload);
                    }
                  } finally {
                    if (mounted) {
                      setState(() => _isSubmitting = false);
                    }
                  }
                },
          text: _isSubmitting
              ? AppLocalizations.of(context).askUserQuestionPanelSubmitting
              : AppLocalizations.of(context).askUserQuestionPanelSubmit,
          options: FFButtonOptions(
            height: 34,
            padding: const EdgeInsetsDirectional.fromSTEB(20, 0, 20, 0),
            color: FlutterFlowTheme.of(context).secondaryBackground,
            textStyle: FlutterFlowTheme.of(context).bodySmall.override(
              color: FlutterFlowTheme.of(context).primaryText,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
            elevation: 0,
            borderSide: BorderSide(
              color: FlutterFlowTheme.of(context).primaryText,
              width: 1,
            ),
            borderRadius: BorderRadius.circular(10),
            loadingIndicatorSize: 14,
          ),
        ),
        const SizedBox(width: 8.0),
        FFButtonWidget(
          onPressed: _isSubmitting || _isCancelling
              ? null
              : () async {
                  setState(() => _isCancelling = true);
                  try {
                    if (widget.onCancel != null) {
                      await widget.onCancel!(widget.messageId);
                    }
                  } finally {
                    if (mounted) {
                      setState(() => _isCancelling = false);
                    }
                  }
                },
          text: _isCancelling
              ? AppLocalizations.of(context).askUserQuestionPanelCancelling
              : AppLocalizations.of(context).commonCancel,
          options: FFButtonOptions(
            height: 34,
            padding: const EdgeInsetsDirectional.fromSTEB(16, 0, 16, 0),
            color: FlutterFlowTheme.of(context).secondaryBackground,
            textStyle: FlutterFlowTheme.of(context).bodySmall.override(
              color: FlutterFlowTheme.of(context).secondaryText,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
            elevation: 0,
            borderSide: BorderSide(color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3), width: 1.0),
            borderRadius: BorderRadius.circular(10),
            loadingIndicatorSize: 14,
          ),
        ),
      ],
    );
  }

  Widget _buildTextInputField(BuildContext context, int questionIndex) {
    final question = widget.payload.questions[questionIndex];
    final textController = _controllerForQuestion(questionIndex);
    final textFocusNode = _focusNodeForQuestion(questionIndex);
    final textFieldKey = _textFieldKeyForQuestion(questionIndex);

    return TextFormField(
      key: textFieldKey,
      controller: textController,
      focusNode: textFocusNode,
      scrollPadding: EdgeInsets.zero, // Disable auto-scroll - we want to stay at bottom
      minLines: 3,
      maxLines: 5,
      onChanged: (value) {
        _answers[questionIndex] = AskUserQuestionAnswer.text(
          text: value,
          optionCount: question.options.length,
        );
        _emitAnswersChanged();
        // No need to scroll - physics are locked while typing
      },
      decoration: InputDecoration(
        hintText: AppLocalizations.of(context).askUserQuestionPanelTypeYourAnswer,
        hintStyle: FlutterFlowTheme.of(context).bodySmall.override(
          color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.7),
          fontSize: 15,
        ),
        contentPadding: const EdgeInsetsDirectional.fromSTEB(10, 8, 10, 8),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.3), width: 0.7),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.35), width: 0.9),
        ),
      ),
      style: FlutterFlowTheme.of(context).bodyMedium.override(
        color: FlutterFlowTheme.of(context).primaryText,
      ),
    );
  }


  Widget _buildOptionButton(
    BuildContext context, {
    required AskUserQuestionItem question,
    required int questionIndex,
    required int optionIndex,
    required bool isSelected,
  }) {
    final option = question.options[optionIndex];

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: () {
          _focusNodeForQuestion(questionIndex).unfocus();
          setState(() {
            final current = _answers[questionIndex];
            if (question.multiSelect) {
              final existing = current.mode == 'option' ? List<int>.from(current.optionIndexes ?? const <int>[]) : <int>[];
              if (existing.contains(optionIndex)) {
                existing.remove(optionIndex);
              } else {
                existing.add(optionIndex);
                existing.sort();
              }
              _answers[questionIndex] = AskUserQuestionAnswer.option(
                optionIndexes: existing,
                questionMultiSelect: true,
                optionCount: question.options.length,
              );
            } else {
              _answers[questionIndex] = AskUserQuestionAnswer.option(
                optionIndex: optionIndex,
                questionMultiSelect: false,
                optionCount: question.options.length,
              );
            }
          });
          _emitAnswersChanged();
          if (!question.multiSelect && _activeTab < widget.payload.questions.length - 1) {
            Future.delayed(const Duration(milliseconds: 150), () {
              if (mounted) setState(() => _activeTab = _activeTab + 1);
            });
          }
        },
        child: Container(
          width: double.infinity,
          padding: const EdgeInsetsDirectional.fromSTEB(10, 10, 10, 10),
          decoration: BoxDecoration(
            color: isSelected
                ? FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.08)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected
                  ? FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.6)
                  : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.25),
              width: isSelected ? 1.3 : 0.8,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Leading circle: empty when unselected, filled check when selected.
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(0, 1, 10, 0),
                child: Icon(
                  isSelected
                      ? Icons.check_circle_rounded
                      : Icons.radio_button_unchecked,
                  size: 20,
                  color: isSelected
                      ? FlutterFlowTheme.of(context).primaryText
                      : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.6),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      option.label,
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
                        color: FlutterFlowTheme.of(context).primaryText,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    if (option.description.trim().isNotEmpty)
                      Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(0, 4, 0, 0),
                        child: Text(
                          option.description,
                          style: FlutterFlowTheme.of(context).bodySmall.override(
                            color: FlutterFlowTheme.of(context).secondaryText,
                            fontSize: 12,
                            fontWeight: FontWeight.w400,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTypeSomethingButton(BuildContext context, AskUserQuestionItem question, int questionIndex) {
    final isTextMode = _answers[questionIndex].mode == 'text';
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: () {
          final currentText = _controllerForQuestion(questionIndex).text;
          setState(() {
            _answers[questionIndex] = AskUserQuestionAnswer.text(
              text: currentText,
              optionCount: question.options.length,
            );
          });
          _emitAnswersChanged();
          _focusTextInput(questionIndex);
        },
        child: Container(
          width: double.infinity,
          padding: const EdgeInsetsDirectional.fromSTEB(10, 10, 10, 10),
          decoration: BoxDecoration(
            color: isTextMode
                ? FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.08)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isTextMode
                  ? FlutterFlowTheme.of(context).primaryText.withValues(alpha: 0.6)
                  : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.25),
              width: isTextMode ? 1.3 : 0.8,
            ),
          ),
          child: Row(
            children: [
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(0, 0, 10, 0),
                child: Icon(
                  isTextMode
                      ? Icons.check_circle_rounded
                      : Icons.radio_button_unchecked,
                  size: 20,
                  color: isTextMode
                      ? FlutterFlowTheme.of(context).primaryText
                      : FlutterFlowTheme.of(context).secondaryText.withValues(alpha: 0.6),
                ),
              ),
              Text(
                AppLocalizations.of(context).askUserQuestionPanelTypeSomething,
                style: FlutterFlowTheme.of(context).bodyMedium.override(
                  color: FlutterFlowTheme.of(context).primaryText,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<AskUserQuestionAnswer> _buildSubmitAnswers() {
    final submitAnswers = <AskUserQuestionAnswer>[];
    for (var i = 0; i < widget.payload.questions.length; i++) {
      final question = widget.payload.questions[i];
      final answer = i < _answers.length ? _answers[i] : null;
      if (answer == null) {
        submitAnswers.add(
          AskUserQuestionAnswer.option(
            optionIndex: 0,
            questionMultiSelect: question.multiSelect,
            optionCount: question.options.length,
          ),
        );
        continue;
      }

      if (answer.mode == 'text') {
        submitAnswers.add(
          AskUserQuestionAnswer.text(
            text: answer.text ?? '',
            optionCount: question.options.length,
          ),
        );
      } else {
        submitAnswers.add(
          AskUserQuestionAnswer.option(
            optionIndex: answer.optionIndex,
            optionIndexes: answer.optionIndexes,
            questionMultiSelect: question.multiSelect,
            optionCount: question.options.length,
          ),
        );
      }
    }
    return submitAnswers;
  }

  List<Map<String, String>> _buildDisplayAnswers() {
    final display = <Map<String, String>>[];
    for (var i = 0; i < widget.payload.questions.length; i++) {
      final question = widget.payload.questions[i];
      final answer = i < _answers.length ? _answers[i] : null;
      if (answer == null) {
        display.add({
          'question': question.question,
          'header': question.header,
          'label': question.options.isNotEmpty ? question.options.first.label : '',
        });
        continue;
      }
      if (answer.mode == 'text') {
        display.add({
          'question': question.question,
          'header': question.header,
          'label': (answer.text ?? '').trim(),
        });
        continue;
      }
      if (question.multiSelect) {
        final labels = (answer.optionIndexes ?? const <int>[])
            .map((idx) => (idx >= 0 && idx < question.options.length) ? question.options[idx].label : '')
            .where((label) => label.trim().isNotEmpty)
            .join(', ');
        display.add({
          'question': question.question,
          'header': question.header,
          'label': labels,
        });
        continue;
      }
      final fallbackIndex = answer.optionIndex ?? 0;
      final label = (fallbackIndex >= 0 && fallbackIndex < question.options.length) ? question.options[fallbackIndex].label : '';
      display.add({
        'question': question.question,
        'header': question.header,
        'label': label,
      });
    }
    return display;
  }
}
