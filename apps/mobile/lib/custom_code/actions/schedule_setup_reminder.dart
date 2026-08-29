// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart';
import '/flutter_flow/custom_functions.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import '/flutter_flow/app_locale.dart';
import 'local_notifications.dart';

// Fixed id so re-scheduling replaces (not stacks) the reminder.
const int _kSetupReminderNotificationId = 920001;

/// Schedule a friendly reminder for tonight at 9pm (device-local) nudging the
/// user to finish setting up Vicoa on their computer.
///
/// Called when a new user taps "I'll set up the CLI on my computer" in the
/// welcome demo. Requests notification permission first; reuses a fixed id so
/// tapping the button again just reschedules rather than stacking reminders.
Future<bool> scheduleSetupReminder() async {
  try {
    await LocalNotifications.requestPermission();

    final when = LocalNotifications.nextDailyTime(21, 0); // 9:00 PM local

    await LocalNotifications.scheduleAt(
      id: _kSetupReminderNotificationId,
      title: tr().setupReminderNotificationTitle,
      body: tr().setupReminderNotificationBody,
      when: when,
      payload: 'setup_reminder',
    );
    return true;
  } catch (e) {
    debugPrint('scheduleSetupReminder error: $e');
    return false;
  }
}

/// Cancel the setup reminder (e.g. once the user has connected a real session).
Future<void> cancelSetupReminder() async {
  await LocalNotifications.cancel(_kSetupReminderNotificationId);
}
