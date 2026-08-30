import 'package:vicoa/backend/push_notifications/push_notifications_handler.dart';

final _pushNotificationsHandler = PushNotificationsHandler();
PushNotificationsHandler get notificationHandler => _pushNotificationsHandler;