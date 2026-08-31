import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:timeago/timeago.dart' as timeago;
import 'lat_lng.dart';
import 'place.dart';
import 'uploaded_file.dart';
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/auth/supabase_auth/auth_util.dart';
import 'flutter_flow_util.dart';
import 'app_locale.dart';

bool isActiveSubscription(String subscriptionStatus) {
  if (subscriptionStatus == "active") {
    return true;
  }
  return false;
}

bool isTodayOrFuture(String number) {
  if (number == "") {
    return false;
  }

  int inputDay = int.parse(number);

  // Get today's day number.
  DateTime now = DateTime.now();
  int todayDay = now.day;

  // Check if the input day is today or in the future.
  return inputDay >= todayDay;
}

DateTime getLastDayOfMonth(DateTime date) {
  return DateTime(date.year, date.month + 1, 0);
}

List<int> getDaysInMonth(DateTime date) {
  int lastDay = getLastDayOfMonth(date).day;
  List<int> daysInMonth = List<int>.generate(lastDay, (i) => i + 1);
  return daysInMonth;
}

// NOTE: `initSurveys()` and `localizedSurveyText()` used to live here. They are
// onboarding-funnel/growth content and are dead code in the open self-host
// build, so they were moved to the closed overlay at
// vicoa-cloud/apps/mobile/lib/onboarding/survey/survey_questions.dart.

bool isSameMonth(
  DateTime? date1,
  DateTime? date2,
) {
  if (date1 == null || date2 == null) {
    return false;
  }
  return date1.year == date2.year && date1.month == date2.month;
}

bool lockFeature(String subscriptionStatus) {
  if (subscriptionStatus == "active") {
    return false;
  }
  return true;
}

bool isNewerVersion(
  String version1,
  String version2,
) {
  // Check whether version2 is newer than version1.

  // Split the versions into their components (major, minor, patch)

  List<int> v1Parts = version1.split('.').map(int.parse).toList();
  List<int> v2Parts = version2.split('.').map(int.parse).toList();

  // Compare each part (major, minor, patch)
  for (int i = 0; i < v1Parts.length; i++) {
    if (v2Parts[i] > v1Parts[i]) {
      return true; // v2 is newer
    } else if (v2Parts[i] < v1Parts[i]) {
      return false; // v1 is newer
    }
  }

  return false;
}

double sumAccountBalances(List accounts) {
  double sum = 0;
  for (var account in accounts) {
    sum += account.balance;
  }

  return sum;
}

String formatDurationAsTimer(int milliseconds) {
  final duration = Duration(milliseconds: milliseconds);
  final hours = duration.inHours;
  final minutes = duration.inMinutes.remainder(60);
  final seconds = duration.inSeconds.remainder(60);

  if (hours > 0) {
    return '${hours.toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
  return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
}

DateTime getOneHourLater(DateTime time) {
  // add 1 minute buffer
  return time.add(Duration(minutes: 59));
}


String surveyInputOthers(
  SurveyStruct survey,
  List<String> selectedOptions,
) {
  for (var option in selectedOptions) {
    if (!survey.options.contains(option)) {
      return option;
    }
  }
  return "";
}

bool isAfter(
  DateTime? date1,
  DateTime? date2,
) {
  if (date1 == null) {
    return false;
  }

  if (date2 == null) {
    return false;
  }

  return date1.isAfter(date2);
}



bool isSameDate(DateTime? date) {
  if (date == null) {
    return false;
  }
  final now = DateTime.now();
  return date.year == now.year &&
      date.month == now.month &&
      date.day == now.day;
}

bool hasRemoteSessionStartMessage(List<dynamic> messages) {
  const scanLimit = 10;
  final limit = messages.length < scanLimit ? messages.length : scanLimit;

  for (int i = 0; i < limit; i++) {
    final message = messages[i];
    if (message is! Map) {
      continue;
    }
    final senderType = message['sender_type']?.toString().toLowerCase() ?? '';
    final isUser = senderType == 'user' || senderType == 'human';
    if (!isUser) {
      continue;
    }

    final content = message['content']?.toString().toLowerCase() ?? '';
    if (content.contains('you are starting a coding session')) {
      return true;
    }
  }

  return false;
}

bool hasInitialBypassPermissionMode(List<dynamic> messages) {
  for (final message in messages) {
    if (message is! Map) {
      continue;
    }
    final content = message['content']?.toString();
    if (content == null || content.isEmpty) {
      continue;
    }
    final detected = extractPermissionModeFromContent(content);
    if (detected != null) {
      return detected == 'bypassPermissions';
    }
  }
  return false;
}

String? extractPermissionModeFromContent(String content) {
  final controlValue = _extractControlSettingValue(content, 'permission_mode');
  if (controlValue != null) {
    return _permissionModeFromValue(controlValue);
  }

  final normalized = content.toLowerCase().trim();
  if (!normalized.startsWith('permission mode')) {
    return null;
  }

  final separatorIndex = normalized.indexOf(':');
  final searchBlock = separatorIndex == -1
      ? normalized
      : normalized.substring(separatorIndex + 1).trim();

  if (searchBlock.contains('bypass permissions') ||
      searchBlock.contains('bypass-permissions') ||
      searchBlock.contains('bypass_permissions') ||
      searchBlock.contains('bypasspermissions') ||
      searchBlock.contains('yolo')) {
    return 'bypassPermissions';
  }
  if (searchBlock.contains('accept edits') ||
      searchBlock.contains('accept-edits') ||
      searchBlock.contains('acceptedits') ||
      searchBlock.contains('auto accept')) {
    return 'acceptEdits';
  }
  if (searchBlock.contains('auto mode') || searchBlock.contains('auto')) {
    return 'auto';
  }
  if (searchBlock.contains('plan mode') || searchBlock.contains('plan')) {
    return 'plan';
  }
  if (searchBlock.contains('default') ||
      searchBlock.contains('manual approval') ||
      searchBlock.contains('shortcuts')) {
    return 'default';
  }

  return null;
}

String? _extractControlSettingValue(String content, String setting) {
  final matches = _controlCommandJsonRegex.allMatches(content);
  for (final match in matches) {
    final snippet = match.group(0);
    final parsed = _parseControlCommand(snippet);
    final parsedSetting = parsed?['setting']?.toString();
    final parsedValue = parsed?['value'];
    if (parsedSetting == setting && parsedValue is String) {
      return parsedValue;
    }
  }
  return null;
}

Map<String, dynamic>? _parseControlCommand(String? value) {
  if (value == null || value.isEmpty) {
    return null;
  }

  try {
    final parsed = jsonDecode(value);
    if (parsed is Map && parsed['type'] == 'control') {
      return Map<String, dynamic>.from(parsed);
    }
  } catch (_) {
    return null;
  }
  return null;
}

String? _permissionModeFromValue(String raw) {
  final normalized = raw.toLowerCase();
  if (normalized == 'bypass_permissions' ||
      normalized == 'bypass-permissions' ||
      normalized == 'bypasspermissions') {
    return 'bypassPermissions';
  }
  if (normalized == 'acceptedits' || normalized == 'accept-edits') {
    return 'acceptEdits';
  }
  if (normalized == 'auto') {
    return 'auto';
  }
  if (normalized == 'plan') {
    return 'plan';
  }
  if (normalized == 'default') {
    return 'default';
  }
  return null;
}

final RegExp _controlCommandJsonRegex = RegExp(
  r'\{\s*"type"\s*:\s*"control"[^}]*\}',
  caseSensitive: false,
);

String formatDurationAsReadableText(int durationInSeconds) {
  final duration = Duration(seconds: durationInSeconds);
  final hours = duration.inHours;
  final minutes = duration.inMinutes.remainder(60);
  final seconds = duration.inSeconds.remainder(60);

  if (hours > 0) {
    // return '${hours}h ${minutes}m ${seconds}s';
    return '${hours}h ${minutes}m';
  } else if (minutes > 0) {
    // return '${minutes}m ${seconds}s';
    return '${minutes}m';
  } else {
    return '${seconds}s';
  }
}

String formatTimestampDate(int timestamp) {
  DateTime date = timestampToDate(timestamp);
  return DateFormat('yyyy-MM-dd').format(date); // Customize format as
}

DateTime timestampToDate(int timestamp) {
  if (timestamp < 10000000000) {
    timestamp *= 1000;
  }

  return DateTime.fromMillisecondsSinceEpoch(timestamp);
}


const Set<String> _closedSessionStatuses = {
  'COMPLETED',
  'FAILED',
  'KILLED',
  'DELETED',
  'CANCELLED',
  'DISCONNECTED',
  'PAUSED',
  'STALE',
};

bool isSessionClosed(String? status) {
  if (status == null || status.isEmpty) return false;
  return _closedSessionStatuses.contains(status.toUpperCase());
}

Color getStatusColor(String status) {
  if (status == 'ACTIVE') {
    return Colors.blue;
  } else if (status == 'AWAITING_INPUT') {
    return Colors.orange;
  } else if (status == 'REVIEWED') {
    return Colors.green;
  } else if (status == 'STALE') {
    return Colors.orange;
  } else if (status == 'COMPLETED') {
    return Colors.grey;
  } else if (status == 'FAILED' ||
      status == 'KILLED' ||
      status == 'DISCONNECTED' ||
      status == 'DELETED') {
    return Colors.grey;
  } else if (status == 'PAUSED') {
    return Colors.grey;
  } else {
    return Colors.grey;
  }
}

String formatRelativeTimeShort(DateTime dateTime) {
  final now = DateTime.now();
  final difference = now.difference(dateTime);
  final l = tr();

  if (difference.inDays > 0) {
    final formatter = dateTime.year == now.year
        ? DateFormat.MMMd()
        : DateFormat.yMMMd();
    return formatter.format(dateTime);
  } else if (difference.inHours > 0) {
    return l.relativeTimeHours(difference.inHours);
  } else if (difference.inMinutes > 0) {
    return l.relativeTimeMinutes(difference.inMinutes);
  } else if (difference.inSeconds > 0) {
    return l.relativeTimeSeconds(difference.inSeconds);
  } else {
    return l.relativeTimeNow;
  }
}

/// Convert a project path with tilde (~) to an absolute path using the home directory
/// Based on vicoa-web/lib/utils.ts
String? toAbsolutePath(String? project, String? homeDir) {
  if (project == null || project.isEmpty) return null;
  if (!project.startsWith('~')) return project; // Already absolute
  if (homeDir == null || homeDir.isEmpty) return project; // Can't convert, return as-is
  return project.replaceFirst(RegExp(r'^~'), homeDir);
}

/// Error types for application error handling
enum ErrorType { none, network, authentication, server }

/// Get the color associated with an error type
Color getErrorColor(ErrorType errorType) {
  switch (errorType) {
    case ErrorType.authentication:
      return Colors.red;
    case ErrorType.network:
      return Colors.orange;
    case ErrorType.server:
      return Colors.amber;
    default:
      return Colors.grey;
  }
}

/// Get the icon associated with an error type
IconData getErrorIcon(ErrorType errorType) {
  switch (errorType) {
    case ErrorType.authentication:
      return Icons.lock_outline;
    case ErrorType.network:
      return Icons.wifi_off_rounded;
    case ErrorType.server:
      return Icons.warning_amber_rounded;
    default:
      return Icons.info_outline;
  }
}

/// Get the title text for an error type
String getErrorTitle(ErrorType errorType) {
  switch (errorType) {
    case ErrorType.authentication:
      return 'Session Expired';
    case ErrorType.network:
      return 'No Connection';
    case ErrorType.server:
      return 'Service Unavailable';
    default:
      return 'Error';
  }
}

/// Construct the feedback email body with device and app information
String buildFeedbackEmailBody() {
  final platform = Platform.operatingSystem;
  final platformVersion = Platform.operatingSystemVersion;
  final appVersion = FFAppState().appVersion;

  return 'Hi,\nI ... \n\n\n\n---\nApp Version: $appVersion\nPlatform: $platform\nOS: $platformVersion';
}

String capitalizeFirst(String text) {
  if (text.isEmpty) return text;
  return text[0].toUpperCase() + text.substring(1);
}

/// Extract motivation phrase from survey answer
String getMotivationPhrase() {
  const defaultPhrase = 'build faster';

  // Find the "Why vibe code on your phone?" survey
  SurveyStruct? vibeCodeSurvey;
  try {
    vibeCodeSurvey = FFAppState().surveys.firstWhere(
      (survey) => survey.question.contains('Why vibe code on your phone'),
    );
  } catch (e) {
    return defaultPhrase;
  }

  // If no answers selected, return default
  if (vibeCodeSurvey.answers.isEmpty) {
    return defaultPhrase;
  }

  // Get the first answer and extract motivation phrase
  final answer = vibeCodeSurvey.answers.join(", ");

  if (answer.contains('Keep progress moving')) {
    return 'build faster';
  } else if (answer.contains('Ship faster')) {
    return 'ship faster';
  } else if (answer.contains('Capture ideas instantly')) {
    return 'capture ideas';
  } else if (answer.contains('Handle small tasks fast')) {
    return 'handle tasks fast';
  } else if (answer.contains('Use short idle moments')) {
    return 'use idle moments';
  } else if (answer.contains('Respond to agent updates')) {
    return 'build faster';
  } else if (answer.contains('Monitor agent progress')) {
    return 'monitor progress';
  } else if (answer.contains('Code while relaxing')) {
    return 'code easily';
  } else if (answer.contains('Just trying it out')) {
    return 'try vibe coding';
  } else {
    return 'build faster';
  }
}
