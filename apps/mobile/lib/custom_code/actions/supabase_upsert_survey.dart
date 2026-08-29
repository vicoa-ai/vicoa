// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

final _suspiciousPattern = RegExp(
  r'<[a-z]|function\s*\(|WebSocket|eval\s*\(|setTimeout|setInterval'
  r'|document\.|window\.|SELECT\s+\*|DROP\s+TABLE|INSERT\s+INTO'
  r'|<script|<iframe|javascript:',
  caseSensitive: false,
);

List<String> _sanitizeAnswers(List<String> answers) => answers
    .where((a) => a.trim().isNotEmpty)
    .where((a) => a.length <= 200)
    .where((a) => !_suspiciousPattern.hasMatch(a))
    .toList();

/// Upsert a single survey answer to the Supabase `surveys` table.
///
/// Mirrors [supabaseUploadSurveys] but for one question — same table and
/// `onConflict` keys, so re-answering the same [question] for the same user
/// overrides the previous row instead of inserting a duplicate.
///
/// Returns true on success.
Future<bool> supabaseUpsertSurvey(
  String question,
  List<String> answers,
) async {
  final sanitized = _sanitizeAnswers(answers);
  if (question.trim().isEmpty || sanitized.isEmpty) {
    return false;
  }

  final supabase = SupaFlow.client;
  final userId = FFAppState().user.id;

  final Map<String, dynamic> surveyData = {
    'question': question.replaceAll('\n', ''),
    'answers': sanitized,
    'created_at': DateTime.now().toIso8601String(),
  };

  String onConflict;
  if (userId.isNotEmpty && !userId.contains('Superwall')) {
    surveyData['user_id'] = userId;
    onConflict = 'user_id,question';
  } else {
    final superwallId = await getSuperWallUserId();
    surveyData['superwall_id'] = superwallId;
    onConflict = 'superwall_id,question';
  }

  try {
    await supabase.from('surveys').upsert(surveyData, onConflict: onConflict);
    debugPrint('[surveys] single upsert OK: $question → $sanitized');
    return true;
  } catch (e) {
    debugPrint('[surveys] single upsert FAILED: $question — $e');
    return false;
  }
}
