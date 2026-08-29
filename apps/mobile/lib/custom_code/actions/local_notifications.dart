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

import 'dart:io' show Platform;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

/// General-purpose local (on-device) push notification helpers.
///
/// This is the reusable layer — schedule / cancel / permission. Specific
/// product reminders (e.g. the "finish setting up Vicoa" nudge) live in their
/// own action files and call into this module so the scheduling details stay
/// in one place. Remote/FCM notifications are handled separately by
/// `push_notifications_handler.dart`; this only covers locally-scheduled ones.
///
/// Reuses the app's existing Android channel + launcher icon so scheduled
/// notifications look consistent with the FCM ones.
class LocalNotifications {
  LocalNotifications._();

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  // Match the channel the FCM handler already creates so Android doesn't end
  // up with two near-identical channels.
  static const String _channelId = 'vicoa_high_importance_channel';
  static const String _channelName = 'Vicoa Notifications';
  static const String _channelDescription =
      'This channel is used for important Vicoa notifications.';

  static bool _initialized = false;

  /// Idempotent init: timezone DB + plugin + Android channel. Safe to call
  /// from multiple entry points; only the first call does work.
  static Future<void> ensureInitialized() async {
    if (_initialized) return;

    tzdata.initializeTimeZones();

    const AndroidInitializationSettings androidInit =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    const DarwinInitializationSettings iosInit = DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
    );
    const InitializationSettings initSettings =
        InitializationSettings(android: androidInit, iOS: iosInit);

    await _plugin.initialize(initSettings);

    if (Platform.isAndroid) {
      await _plugin
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.createNotificationChannel(
            const AndroidNotificationChannel(
              _channelId,
              _channelName,
              description: _channelDescription,
              importance: Importance.high,
              enableVibration: true,
              playSound: true,
            ),
          );
    }

    _initialized = true;
  }

  /// Ask the OS for permission to show notifications. Returns true when granted
  /// (or already authorized). No-op-safe on platforms that grant implicitly.
  static Future<bool> requestPermission() async {
    await ensureInitialized();
    try {
      if (Platform.isIOS) {
        final granted = await _plugin
            .resolvePlatformSpecificImplementation<
                IOSFlutterLocalNotificationsPlugin>()
            ?.requestPermissions(alert: true, badge: true, sound: true);
        return granted ?? false;
      }
      if (Platform.isAndroid) {
        final granted = await _plugin
            .resolvePlatformSpecificImplementation<
                AndroidFlutterLocalNotificationsPlugin>()
            ?.requestNotificationsPermission();
        return granted ?? true;
      }
    } catch (e) {
      debugPrint('LocalNotifications.requestPermission error: $e');
    }
    return true;
  }

  static NotificationDetails _details() {
    const AndroidNotificationDetails android = AndroidNotificationDetails(
      _channelId,
      _channelName,
      channelDescription: _channelDescription,
      importance: Importance.high,
      priority: Priority.high,
      icon: '@mipmap/ic_launcher',
    );
    const DarwinNotificationDetails ios = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
    );
    return const NotificationDetails(android: android, iOS: ios);
  }

  /// Schedule a one-off notification at an absolute device-local [when].
  ///
  /// [when] is interpreted in the device's local clock; if it's already in the
  /// past the call is skipped. Reusing the same [id] replaces any previously
  /// scheduled notification with that id.
  static Future<void> scheduleAt({
    required int id,
    required String title,
    required String body,
    required DateTime when,
    String? payload,
  }) async {
    await ensureInitialized();

    // Build the TZDateTime from the absolute instant of `when`. We don't rely
    // on tz.local being the device zone (it defaults to UTC) — the epoch is
    // what matters, and absoluteTime interpretation fires at that instant.
    final scheduled = tz.TZDateTime.from(when, tz.local);
    if (scheduled.isBefore(tz.TZDateTime.now(tz.local))) {
      debugPrint('LocalNotifications.scheduleAt skipped — $scheduled is past');
      return;
    }

    await _plugin.zonedSchedule(
      id,
      title,
      body,
      scheduled,
      _details(),
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      // Inexact is fine for a day-part reminder and avoids the Android 13+
      // SCHEDULE_EXACT_ALARM permission that exact modes require.
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      payload: payload,
    );
    debugPrint('LocalNotifications scheduled id=$id at $scheduled');
  }

  /// Returns the next occurrence of [hour]:[minute] in device-local time —
  /// today if it's still ahead, otherwise tomorrow.
  static DateTime nextDailyTime(int hour, int minute) {
    final now = DateTime.now();
    var next = DateTime(now.year, now.month, now.day, hour, minute);
    if (!next.isAfter(now)) {
      next = next.add(const Duration(days: 1));
    }
    return next;
  }

  /// Cancel a single scheduled/shown notification by id.
  static Future<void> cancel(int id) async {
    await ensureInitialized();
    await _plugin.cancel(id);
  }
}
