import 'package:flutter/foundation.dart';

import '/backend/push_notifications/push_notifications_handler.dart';

Future<String> testPushNotifications() async {
  try {
    final pushHandler = PushNotificationsHandler();
    
    if (!pushHandler.initialized) {
      await pushHandler.initialize();
    }
    
    String? token = pushHandler.fcmToken;
    
    // If no token initially, try refreshing (especially useful for iOS)
    if (token == null) {
      if (kDebugMode) {
        print('No initial token, attempting refresh...');
      }
      token = await pushHandler.refreshFCMToken();
    }
    
    if (token != null) {
      if (kDebugMode) {
        print('Push notifications initialized successfully');
        print('FCM Token: $token');
      }
      
      // Test topic subscription
      await pushHandler.subscribeToTopic('test_topic');
      
      return 'Push notifications working! Token: ${token.substring(0, 20)}...';
    } else {
      return 'Failed to get FCM token - check APNS setup for iOS';
    }
  } catch (e) {
    if (kDebugMode) {
      print('Error testing push notifications: $e');
    }
    return 'Error: $e';
  }
}