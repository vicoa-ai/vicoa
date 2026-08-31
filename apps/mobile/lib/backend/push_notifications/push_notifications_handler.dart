import 'dart:io';

import 'package:app_settings/app_settings.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_util.dart';
import '/index.dart';

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  if (kDebugMode) {
    print('Handling a background message: ${message.messageId}');
    print('Message data: ${message.data}');
    print('Message notification: ${message.notification?.title}');
  }
}

class PushNotificationsHandler with WidgetsBindingObserver {
  static final PushNotificationsHandler _instance = PushNotificationsHandler._internal();
  factory PushNotificationsHandler() => _instance;
  PushNotificationsHandler._internal();

  static const String _channelId = 'vicoa_high_importance_channel';
  static const String _channelName = 'Vicoa Notifications';
  static const String _channelDescription = 'This channel is used for important Vicoa notifications.';

  final FirebaseMessaging _firebaseMessaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _localNotifications = FlutterLocalNotificationsPlugin();

  String? _fcmToken;
  // The token we have confirmed is registered with the backend (HTTP 2xx).
  // Kept separate from _fcmToken so a fetched-but-not-yet-registered token
  // never blocks a retry.
  String? _registeredToken;
  bool _initialized = false;
  bool _tokenRefreshAttached = false;
  bool _syncInProgress = false;
  // Guards against two tap entry points (getInitialMessage + onMessageOpenedApp)
  // racing to open the same session twice.
  bool _openingSessionFromNotification = false;

  String? get fcmToken => _fcmToken;
  bool get initialized => _initialized;

  Future<void> initialize() async {
    if (_initialized) return;

    try {
      // Initialize local notifications without requesting permissions
      await _initializeLocalNotifications();

      // Set up message handlers first
      await _setupMessageHandlers();

      // Keep the backend in sync whenever Firebase rotates the token.
      _attachTokenRefreshListener();

      // Re-attempt registration each time the app returns to the foreground.
      // This is what recovers users who enabled notifications in system
      // Settings after an initial denial (iOS only prompts once), or whose
      // earlier registration attempt failed silently.
      WidgetsBinding.instance.addObserver(this);

      _initialized = true;

      if (kDebugMode) {
        print('Push notifications initialized successfully (without permissions)');
      }
    } catch (e) {
      _initialized = true; // Mark as initialized even if token fails
      if (kDebugMode) {
        print('Error initializing push notifications: $e');
      }
    }
  }

  Future<bool> checkPermission() async {
    try {
      if (Platform.isIOS) {
        final NotificationSettings settings = await _firebaseMessaging.getNotificationSettings();
        
        bool isGranted = settings.authorizationStatus == AuthorizationStatus.authorized ||
                        settings.authorizationStatus == AuthorizationStatus.provisional;
        
        debugPrint("iOS notification permission status: ${settings.authorizationStatus}");
        return isGranted;
        
      } else if (Platform.isAndroid) {
        // For Android, check if notifications are enabled
        FlutterLocalNotificationsPlugin flutterLocalNotificationsPlugin =
            FlutterLocalNotificationsPlugin();
        
        bool? granted = await flutterLocalNotificationsPlugin
            .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
            ?.areNotificationsEnabled();
        
        debugPrint("Android notification permission: $granted");
        return granted ?? false;
      }
      
      return false;
    } catch (error) {
      debugPrint("Failed to check notification permission: $error");
      return false;
    }
  }

  /// Combined method to check and request permissions if needed
  Future<bool> ensurePermissions() async {
    final bool alreadyGranted = await checkPermission();
    if (alreadyGranted) {
      // Make sure the backend actually has the current token. syncPushRegistration
      // is idempotent, so this also repairs a token that was fetched earlier but
      // never successfully registered.
      await syncPushRegistration();
      return true;
    }

    return await requestPermissions();
  }

  Future<bool> requestPermissions() async {
    try {
      bool granted = false;
      
      // First try to request local notification permissions
      if (Platform.isIOS) {
        final bool? localResult = await _localNotifications
            .resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>()
            ?.requestPermissions(
              alert: true,
              badge: true,
              sound: true,
            );
        granted = localResult ?? false;
      }

      if (Platform.isAndroid) {
        final bool? localResult = await _localNotifications
            .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
            ?.requestNotificationsPermission();
        granted = localResult ?? false;
      }

      // Also request Firebase permissions
      final NotificationSettings settings = await _firebaseMessaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );

      // Consider granted if either local or Firebase permissions are granted
      final bool firebaseGranted = settings.authorizationStatus == AuthorizationStatus.authorized ||
                                   settings.authorizationStatus == AuthorizationStatus.provisional;
      
      granted = granted || firebaseGranted;

      if (kDebugMode) {
        print('Local notification permission: $granted');
        print('Firebase permission status: ${settings.authorizationStatus}');
        print('Overall permission granted: $granted');
      }

      // If permissions granted, setup FCM token
      if (granted) {
        await syncPushRegistration();
      } else if (settings.authorizationStatus == AuthorizationStatus.denied) {
        // If Firebase permissions are explicitly denied, open app settings
        if (kDebugMode) {
          print('Firebase notification permissions denied, opening app settings');
        }
        await AppSettings.openAppSettings(type: AppSettingsType.notification);
      }

      return granted;
    } catch (e) {
      if (kDebugMode) {
        print('Error requesting notification permissions: $e');
      }
      return false;
    }
  }

  Future<void> _initializeLocalNotifications() async {
    const AndroidInitializationSettings initializationSettingsAndroid =
        AndroidInitializationSettings('@mipmap/ic_launcher');

    const DarwinInitializationSettings initializationSettingsIOS =
        DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
    );

    const InitializationSettings initializationSettings = InitializationSettings(
      android: initializationSettingsAndroid,
      iOS: initializationSettingsIOS,
    );

    await _localNotifications.initialize(
      initializationSettings,
      onDidReceiveNotificationResponse: _onNotificationTap,
    );

    // Create notification channel for Android
    if (Platform.isAndroid) {
      const AndroidNotificationChannel channel = AndroidNotificationChannel(
        _channelId,
        _channelName,
        description: _channelDescription,
        importance: Importance.high,
        enableVibration: true,
        playSound: true,
      );

      await _localNotifications
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
          ?.createNotificationChannel(channel);
    }
  }

  /// Backwards-compatible entry point (called from the Home page on load).
  /// Delegates to [syncPushRegistration], which owns permission-gating, the
  /// APNS wait, and awaited registration.
  Future<void> getFCMToken() => syncPushRegistration();

  /// Idempotently ensure the device's current FCM token is registered with the
  /// backend. Safe to call repeatedly — on app launch, when the Home page
  /// loads, when the user enables notifications, and on every app resume.
  ///
  /// It never triggers a permission prompt (only reads permission state), only
  /// hits the network when there is a new/unregistered token to send, and — via
  /// the resume observer — is what recovers a user who granted notifications
  /// after an initial denial or whose earlier registration silently failed.
  Future<void> syncPushRegistration() async {
    if (_syncInProgress) return;
    _syncInProgress = true;
    try {
      // Nothing to register until the OS will actually deliver notifications.
      final bool granted = await checkPermission();
      if (!granted) return;

      // iOS: FirebaseMessaging.getToken() requires the APNS token to be set
      // first, which can lag slightly behind app launch.
      if (Platform.isIOS) {
        final apnsToken = await _waitForApnsToken();
        if (apnsToken == null) {
          if (kDebugMode) {
            print('APNS token not ready; will retry on next resume');
          }
          return; // A later resume / home load will retry.
        }
      }

      final String? token = await _firebaseMessaging.getToken();
      if (token == null || token.isEmpty) return;
      _fcmToken = token;

      // Already confirmed registered with the backend — nothing to do.
      if (token == _registeredToken) return;

      final bool ok = await actions.apiRegisterFcmToken(token);
      if (ok) {
        _registeredToken = token;
        if (kDebugMode) {
          print('FCM token registered with backend: ${token.substring(0, 12)}...');
        }
      }
      // On failure we intentionally leave _registeredToken unset so the next
      // resume / home load retries.
    } catch (e) {
      if (kDebugMode) {
        print('syncPushRegistration error: $e');
      }
    } finally {
      _syncInProgress = false;
    }
  }

  /// Poll briefly for the iOS APNS token (null right after launch until the
  /// device registers with APNs). Returns null if it never arrives in the
  /// window, in which case the caller retries on the next resume.
  Future<String?> _waitForApnsToken({int maxAttempts = 5}) async {
    for (var attempt = 0; attempt < maxAttempts; attempt++) {
      final apns = await _firebaseMessaging.getAPNSToken();
      if (apns != null) return apns;
      await Future.delayed(const Duration(seconds: 1));
    }
    return _firebaseMessaging.getAPNSToken();
  }

  void _attachTokenRefreshListener() {
    if (_tokenRefreshAttached) return;
    _tokenRefreshAttached = true;
    _firebaseMessaging.onTokenRefresh.listen((newToken) {
      _fcmToken = newToken;
      _onTokenRefresh(newToken);
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // The user may have just toggled notifications on in system Settings, or
      // a previous registration attempt may have failed silently. Re-sync.
      syncPushRegistration();
      // Reconcile the launcher badge with server truth: a push may have set it
      // while backgrounded, but the user could have answered on another device
      // since — recompute so a stale (or now-zero) count is corrected on open.
      actions.refreshAppBadge();
    }
  }

  Future<void> _setupMessageHandlers() async {
    // Handle background messages
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Handle foreground messages
    FirebaseMessaging.onMessage.listen(_handleForegroundMessage);

    // Handle notification taps when app is in background but not terminated
    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);

    // Handle notification tap when app is terminated
    final RemoteMessage? initialMessage = await _firebaseMessaging.getInitialMessage();
    if (initialMessage != null) {
      _handleNotificationTap(initialMessage);
    }
  }

  Future<void> _handleForegroundMessage(RemoteMessage message) async {
    if (kDebugMode) {
      print('Received foreground message: ${message.messageId}');
      print('Message data: ${message.data}');
      print('Message notification: ${message.notification?.title}');
    }

    // iOS doesn't apply aps.badge while the app is foregrounded (we intercept
    // the notification here), so mirror the count the backend stamped onto the
    // payload ourselves. Background/terminated badges are handled by the OS.
    _applyBadgeFromMessage(message);

    // Show local notification when app is in foreground
    if (message.notification != null) {
      await _showLocalNotification(message);
    }
  }

  /// Set the launcher badge to the awaiting-input count carried in the push
  /// data payload (added by the backend FCM service). Silently ignores a
  /// missing/unparseable value so a malformed push never disturbs the badge.
  void _applyBadgeFromMessage(RemoteMessage message) {
    final raw = message.data['badge'];
    if (raw == null) return;
    final count = int.tryParse(raw.toString());
    if (count == null) return;
    actions.setAppBadge(count);
  }

  Future<void> _showLocalNotification(RemoteMessage message) async {
    final RemoteNotification? notification = message.notification;
    if (notification == null) return;

    const AndroidNotificationDetails androidNotificationDetails = AndroidNotificationDetails(
      _channelId,
      _channelName,
      channelDescription: _channelDescription,
      importance: Importance.high,
      priority: Priority.high,
      enableVibration: true,
      playSound: true,
      icon: '@mipmap/ic_launcher',
    );

    const DarwinNotificationDetails iOSNotificationDetails = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
    );

    const NotificationDetails notificationDetails = NotificationDetails(
      android: androidNotificationDetails,
      iOS: iOSNotificationDetails,
    );

    await _localNotifications.show(
      message.hashCode,
      notification.title,
      notification.body,
      notificationDetails,
      payload: jsonEncode(message.data),
    );
  }

  void _handleNotificationTap(RemoteMessage message) {
    if (kDebugMode) {
      print('Notification tapped: ${message.messageId}');
      print('Message data: ${message.data}');
    }

    _navigateFromNotification(message.data);
  }

  void _onNotificationTap(NotificationResponse notificationResponse) {
    if (kDebugMode) {
      print('Local notification tapped: ${notificationResponse.id}');
      print('Payload: ${notificationResponse.payload}');
    }

    if (notificationResponse.payload != null) {
      try {
        final Map<String, dynamic> data = jsonDecode(notificationResponse.payload!);
        _navigateFromNotification(data);
      } catch (e) {
        if (kDebugMode) {
          print('Error parsing notification payload: $e');
        }
      }
    }
  }

  void _navigateFromNotification(Map<String, dynamic> data) {
    final BuildContext? context = appNavigatorKey.currentContext;
    if (context == null) {
      if (kDebugMode) {
        print('Navigation context not available');
      }
      return;
    }

    // Handle different notification types based on data
    final String? type = data['type'];
    final String? instanceId = data['instance_id'] ?? data['instanceId'];

    switch (type) {
      case 'new_question':
        if (instanceId != null) {
          _openSessionFromNotification(instanceId);
        }
        break;
      case 'credit_update':
        context.go('/profile/usage-credits');
        break;
      case 'activation_nudge':
        // Re-engagement nudge for signups who haven't connected a computer yet:
        // land them on Start Session, which hosts ConnectComputerWidget.
        context.go('/start-session');
        break;
      default:
        context.go('/home');
        break;
    }
  }

  /// Open an agent session from a `new_question` notification.
  ///
  /// A cold-start / background tap fires before the auth token is ready, and
  /// the shared fetchers swallow errors into `[]`/`null` — so naively pushing
  /// the chat page (which then re-fetches) used to render a permanently-empty
  /// "Waiting for messages" screen when that first load silently failed. So we
  /// resolve the session FIRST (token-ready wait + retries) and only push the
  /// chat once we actually have it. A confirmed-gone (404) or still-failing
  /// session leaves the user on Home instead of opening a dead page we'd only
  /// have to bounce back — which is the jarring part we're avoiding.
  Future<void> _openSessionFromNotification(String instanceId) async {
    if (_openingSessionFromNotification) return;
    _openingSessionFromNotification = true;
    try {
      // Land on Home first: it's the fallback screen when the open fails, and
      // it hosts the chat page's back destination on success.
      appNavigatorKey.currentContext?.goNamed(HomeWidget.routeName);

      // Cap the whole resolve so a hung socket (the app's http calls have no
      // per-request timeout) can't pin the reentrancy guard until restart.
      final result = await actions
          .apiPrefetchNotificationInstance(instanceId)
          .timeout(const Duration(seconds: 8),
              onTimeout: () => const actions.NotificationPrefetchResult());

      // Re-read the context after the await (don't hold one across the gap).
      final context = appNavigatorKey.currentContext;
      if (context == null || !context.mounted) return;

      if (!result.ok) {
        // Confirmed gone (404) or transient failure after retries: stay on
        // Home. (No auto-bounce off an opened page — see doc comment.)
        if (kDebugMode) {
          print(result.gone
              ? 'Session $instanceId is gone (404); staying on Home'
              : 'Session $instanceId failed to prefetch; staying on Home');
        }
        return;
      }

      // Seed the per-instance cache so the chat opens instantly with content
      // (no empty flash). The page still background-refreshes and starts
      // streaming on open. An empty list is left unseeded — a valid session
      // with no messages yet correctly shows "Waiting for messages".
      if (result.messages.isNotEmpty) {
        FFAppState().setCachedMessages(instanceId, result.messages);
      }

      context.pushNamed(
        AgentChatWidget.routeName,
        pathParameters: {
          'instanceId': instanceId,
        },
        extra: <String, dynamic>{
          // Prefetched from the authoritative REST API (not the wake-only FCM
          // payload), so the header + streaming gate render immediately.
          if (result.instanceData != null) 'instanceData': result.instanceData,
          kTransitionInfoKey: const TransitionInfo(
            hasTransition: true,
            transitionType: PageTransitionType.rightToLeft,
          ),
        },
      );
    } finally {
      _openingSessionFromNotification = false;
    }
  }

  Future<void> _onTokenRefresh(String newToken) async {
    if (kDebugMode) {
      print('FCM token refreshed');
    }

    // Register new token with backend.
    final bool ok = await actions.apiRegisterFcmToken(newToken);
    if (ok) {
      _registeredToken = newToken;
    }
  }

  Future<void> subscribeToTopic(String topic) async {
    try {
      await _firebaseMessaging.subscribeToTopic(topic);
      if (kDebugMode) {
        print('Subscribed to topic: $topic');
      }
    } catch (e) {
      if (kDebugMode) {
        print('Error subscribing to topic $topic: $e');
      }
    }
  }

  Future<void> unsubscribeFromTopic(String topic) async {
    try {
      await _firebaseMessaging.unsubscribeFromTopic(topic);
      if (kDebugMode) {
        print('Unsubscribed from topic: $topic');
      }
    } catch (e) {
      if (kDebugMode) {
        print('Error unsubscribing from topic $topic: $e');
      }
    }
  }

  Future<void> clearNotifications() async {
    await _localNotifications.cancelAll();
  }

  Future<void> clearNotification(int id) async {
    await _localNotifications.cancel(id);
  }

  /// Manually refresh FCM token (useful for debugging iOS APNS issues)
  Future<String?> refreshFCMToken() async {
    try {
      if (Platform.isIOS) {
        // Wait for APNS token on iOS
        int retries = 0;
        while (retries < 5) {
          final apnsToken = await _firebaseMessaging.getAPNSToken();
          if (apnsToken != null) {
            if (kDebugMode) {
              print('APNS token available: ${apnsToken.substring(0, 10)}...');
            }
            break;
          }
          retries++;
          await Future.delayed(const Duration(seconds: 2));
          if (kDebugMode) {
            print('Waiting for APNS token, retry $retries/5');
          }
        }
      }

      _fcmToken = await _firebaseMessaging.getToken();
      if (_fcmToken != null) {
        final bool ok = await actions.apiRegisterFcmToken(_fcmToken);
        if (ok) {
          _registeredToken = _fcmToken;
        }
        if (kDebugMode) {
          print('FCM token refreshed: ${_fcmToken!.substring(0, 20)}...');
        }
      }
      return _fcmToken;
    } catch (e) {
      if (kDebugMode) {
        print('Error refreshing FCM token: $e');
      }
      return null;
    }
  }

  /// Clear FCM token locally (for logout/account deletion)
  Future<void> clearFCMToken() async {
    try {
      // Delete the token from Firebase
      // await _firebaseMessaging.deleteToken();
      
      // Clear the local cached token
      _fcmToken = null;
      _registeredToken = null;

      if (kDebugMode) {
        print('FCM token cleared locally');
      }
    } catch (e) {
      if (kDebugMode) {
        print('Error clearing FCM token: $e');
      }
    }
  }
}
