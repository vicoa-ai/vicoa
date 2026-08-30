import '/auth/supabase_auth/auth_util.dart';
import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/confirm_dialog/confirm_dialog_widget.dart';
import '/pages/info_dialog/info_dialog_widget.dart';
import 'dart:ui';
import '/actions/actions.dart' as action_blocks;
import '/custom_code/actions/index.dart' as actions;
import '/index.dart';
import 'sign_up_widget.dart' show SignUpWidget;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class SignUpModel extends FlutterFlowModel<SignUpWidget> {
  ///  Local state fields for this page.

  String _confirmPassword = 'NULL';
  set confirmPassword(String value) {
    _confirmPassword = value;
  }

  String get confirmPassword => _confirmPassword;

  bool _isSignUp = true;
  set isSignUp(bool value) {
    _isSignUp = value;
  }

  bool get isSignUp => _isSignUp;

  bool _showReferralCode = false;
  set showReferralCode(bool value) {
    _showReferralCode = value;
  }

  bool get showReferralCode => _showReferralCode;

  bool _showEmailForm = false;
  set showEmailForm(bool value) {
    _showEmailForm = value;
  }

  bool get showEmailForm => _showEmailForm;

  ///  State fields for stateful widgets in this page.

  final formKey = GlobalKey<FormState>();
  // Stores action output result for [Custom Action - getSuperWallUserId] action in SignUp widget.
  String? _superWallUserId;
  set superWallUserId(String? value) {
    _superWallUserId = value;
  }

  String? get superWallUserId => _superWallUserId;

  // Stores action output result for [Custom Action - getRevenueCatUserId] action in SignUp widget.
  String? _revenueCatUserId;
  set revenueCatUserId(String? value) {
    _revenueCatUserId = value;
  }

  String? get revenueCatUserId => _revenueCatUserId;

  // Stores action output result for [Alert Dialog - Custom Dialog] action in Text widget.
  bool? _confirmedDialog;
  set confirmedDialog(bool? value) {
    _confirmedDialog = value;
  }

  bool? get confirmedDialog => _confirmedDialog;

  // State field(s) for emailAddress widget.
  FocusNode? emailAddressFocusNode;
  TextEditingController? emailAddressTextController;
  String? Function(BuildContext, String?)? emailAddressTextControllerValidator;
  String? _emailAddressTextControllerValidator(
      BuildContext context, String? val) {
    if (val == null || val.isEmpty) {
      return 'Field is required';
    }

    if (!RegExp(kTextValidatorEmailRegex).hasMatch(val)) {
      return 'Has to be a valid email address.';
    }
    return null;
  }

  // State field(s) for password widget.
  FocusNode? passwordFocusNode;
  TextEditingController? passwordTextController;
  late bool passwordVisibility;
  String? Function(BuildContext, String?)? passwordTextControllerValidator;
  String? _passwordTextControllerValidator(BuildContext context, String? val) {
    if (val == null || val.isEmpty) {
      return 'Field is required';
    }

    if (val.length < 8) {
      return 'Requires at least 8 characters.';
    }

    return null;
  }

  // State field(s) for referralCode widget.
  FocusNode? referralCodeFocusNode;
  TextEditingController? referralCodeTextController;
  String? Function(BuildContext, String?)? referralCodeTextControllerValidator;
  String? _referralCodeTextControllerValidator(
      BuildContext context, String? val) {
    if (val == null || val.isEmpty) {
      return 'Field is required';
    }

    if (val.length < 8) {
      return 'Referral code is 8 characters long.';
    }
    if (val.length > 8) {
      return 'Referral code is 8 characters long.';
    }

    return null;
  }

  // Stores action output result for [Custom Action - supabaseGetReferrerId] action in Button widget.
  String? _referrerId;
  set referrerId(String? value) {
    _referrerId = value;
  }

  String? get referrerId => _referrerId;

  // Stores action output result for [Custom Action - supabaseApplyReferralCode] action in Button widget.
  bool? _referred;
  set referred(bool? value) {
    _referred = value;
  }

  bool? get referred => _referred;

  // Stores action output result for [Alert Dialog - Custom Dialog] action in Button widget.
  bool? _confirmed;
  set confirmed(bool? value) {
    _confirmed = value;
  }

  bool? get confirmed => _confirmed;

  final Map<String, DebugDataField> debugGeneratorVariables = {};
  final Map<String, DebugDataField> debugBackendQueries = {};
  final Map<String, FlutterFlowModel> widgetBuilderComponents = {};
  @override
  void initState(BuildContext context) {
    emailAddressTextControllerValidator = _emailAddressTextControllerValidator;
    passwordVisibility = false;
    passwordTextControllerValidator = _passwordTextControllerValidator;
    referralCodeTextControllerValidator = _referralCodeTextControllerValidator;

  }

  @override
  void dispose() {
    emailAddressFocusNode?.dispose();
    emailAddressTextController?.dispose();

    passwordFocusNode?.dispose();
    passwordTextController?.dispose();

    referralCodeFocusNode?.dispose();
    referralCodeTextController?.dispose();
  }
}
