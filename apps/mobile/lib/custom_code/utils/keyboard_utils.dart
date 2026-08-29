// Small keyboard helpers shared by bottom-sheet editors (tasks, automations).
// The goal is a calm keyboard: opening a picker or tapping empty space should
// dismiss the keyboard and keep it dismissed, instead of letting it flash back
// when the picker closes and focus is restored to the text field.

import 'package:flutter/material.dart';

/// Clears the current focus, dismissing the on-screen keyboard. Safe to call
/// when nothing is focused.
void dismissKeyboard() => FocusManager.instance.primaryFocus?.unfocus();

/// Dismisses the keyboard and waits (bounded) for the keyboard inset to animate
/// back to zero. Callers that measure layout right afterwards — e.g. anchored
/// popovers positioned against a widget inside a keyboard-lifted sheet — should
/// await this first, otherwise they capture the mid-animation geometry and the
/// popover ends up detached from its anchor once the sheet settles.
Future<void> dismissKeyboardAndSettle(BuildContext context) async {
  final hadKeyboard = MediaQuery.of(context).viewInsets.bottom > 0;
  dismissKeyboard();
  if (!hadKeyboard) return;
  // Poll the inset instead of a fixed delay so we return as soon as the
  // keyboard is gone; capped at ~480ms so a slow/absent animation can't hang.
  for (var i = 0; i < 30; i++) {
    await Future<void>.delayed(const Duration(milliseconds: 16));
    if (!context.mounted || MediaQuery.of(context).viewInsets.bottom == 0) {
      return;
    }
  }
}
