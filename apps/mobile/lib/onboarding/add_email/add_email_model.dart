import 'package:flutter/material.dart';

import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_util.dart';
import 'add_email_widget.dart' show AddEmailWidget;

final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

/// State for the Add email page: the field, the in-flight flag, and the last
/// outcome, which the widget turns into a message.
class AddEmailModel extends FlutterFlowModel<AddEmailWidget> {
  TextEditingController? emailController;
  FocusNode? emailFocusNode;
  bool isSaving = false;
  actions.AddEmailOutcome? outcome;

  VoidCallback? _notify;

  void setNotify(VoidCallback cb) => _notify = cb;
  void _bump() => _notify?.call();

  @override
  void initState(BuildContext context) {
    emailController = TextEditingController();
    emailFocusNode = FocusNode();
  }

  @override
  void dispose() {
    emailController?.dispose();
    emailFocusNode?.dispose();
  }

  /// Saves the typed address. Returns true once the account has it.
  Future<bool> submit() async {
    final email = (emailController?.text ?? '').trim();
    if (!_emailPattern.hasMatch(email)) {
      outcome = actions.AddEmailOutcome.invalid;
      _bump();
      return false;
    }
    isSaving = true;
    outcome = null;
    _bump();
    try {
      outcome = await actions.apiAddEmail(email);
    } finally {
      isSaving = false;
      _bump();
    }
    return outcome == actions.AddEmailOutcome.added;
  }
}
