import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import '/backend/push_notifications/push_notifications_handler.dart';

Future<String> debugPushNotifications() async {
  StringBuffer debug = StringBuffer();
  
  try {
    debug.writeln('=== Push Notification Debug Report ===');
    debug.writeln('Platform: ${Platform.isIOS ? 'iOS' : 'Android'}');
    debug.writeln('Environment: ${kDebugMode ? 'Debug' : 'Release'}');
    debug.writeln('');
    
    // Initialize Firebase Messaging
    final messaging = FirebaseMessaging.instance;
    
    // Check permissions
    debug.writeln('--- Permission Status ---');
    final settings = await messaging.getNotificationSettings();
    debug.writeln('Authorization Status: ${settings.authorizationStatus}');
    debug.writeln('Alert Setting: ${settings.alert}');
    debug.writeln('Badge Setting: ${settings.badge}');
    debug.writeln('Sound Setting: ${settings.sound}');
    debug.writeln('');
    
    // Check APNS token for iOS
    if (Platform.isIOS) {
      debug.writeln('--- iOS APNS Token ---');
      try {
        final apnsToken = await messaging.getAPNSToken();
        if (apnsToken != null) {
          debug.writeln('APNS Token: ${apnsToken.substring(0, 20)}...');
          debug.writeln('APNS Token Length: ${apnsToken.length}');
        } else {
          debug.writeln('APNS Token: NULL - This is likely the issue!');
          debug.writeln('Waiting 5 seconds and retrying...');
          await Future.delayed(const Duration(seconds: 5));
          final retryToken = await messaging.getAPNSToken();
          if (retryToken != null) {
            debug.writeln('APNS Token (retry): ${retryToken.substring(0, 20)}...');
          } else {
            debug.writeln('APNS Token (retry): Still NULL');
          }
        }
      } catch (e) {
        debug.writeln('APNS Token Error: $e');
      }
      debug.writeln('');
    }
    
    // Get FCM token
    debug.writeln('--- FCM Token ---');
    try {
      final fcmToken = await messaging.getToken();
      if (fcmToken != null) {
        debug.writeln('FCM Token: $fcmToken');
        debug.writeln('FCM Token Length: ${fcmToken.length}');
      } else {
        debug.writeln('FCM Token: NULL');
      }
    } catch (e) {
      debug.writeln('FCM Token Error: $e');
    }
    debug.writeln('');
    
    // Check handler state
    debug.writeln('--- Push Handler State ---');
    final handler = PushNotificationsHandler();
    debug.writeln('Handler Initialized: ${handler.initialized}');
    debug.writeln('Handler FCM Token: ${handler.fcmToken?.substring(0, 20) ?? 'NULL'}...');
    debug.writeln('');
    
    // Test initialization
    debug.writeln('--- Testing Initialization ---');
    if (!handler.initialized) {
      debug.writeln('Initializing handler...');
      await handler.initialize();
      debug.writeln('Handler initialized: ${handler.initialized}');
      debug.writeln('Handler token after init: ${handler.fcmToken?.substring(0, 20) ?? 'NULL'}...');
    }
    
    // Try manual token refresh
    debug.writeln('--- Manual Token Refresh ---');
    final refreshedToken = await handler.refreshFCMToken();
    debug.writeln('Refreshed Token: ${refreshedToken?.substring(0, 20) ?? 'NULL'}...');
    debug.writeln('');
    
    debug.writeln('=== End Debug Report ===');
    
  } catch (e) {
    debug.writeln('Debug Error: $e');
  }
  
  final result = debug.toString();
  if (kDebugMode) {
    print(result);
  }
  
  return result;
}