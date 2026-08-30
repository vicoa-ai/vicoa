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

Future supabaseUploadSurveys() async {
  final supabase = SupaFlow.client;
  final now = DateTime.now().toIso8601String();

  final userId = FFAppState().user.id;
  final totalSurveys = FFAppState().surveys.length;

  debugPrint("[surveys] upload started — userId=$userId, totalSurveys=$totalSurveys");
  for (int i = 0; i < FFAppState().surveys.length; i++) {
    final s = FFAppState().surveys[i];
    debugPrint("[surveys]   [$i] question=${s.question}, answers=${s.answers}");
  }

  try {
    int uploadedCount = 0;
    int skippedCount = 0;

    for (final survey in FFAppState().surveys) {
      if (survey.answers.isEmpty) {
        debugPrint("[surveys] skipping (no answers): ${survey.question}");
        skippedCount++;
        continue;
      }

      final sanitizedAnswers = _sanitizeAnswers(survey.answers);
      if (sanitizedAnswers.isEmpty) {
        debugPrint("[surveys] skipping (all answers filtered): ${survey.question}");
        skippedCount++;
        continue;
      }

      Map<String, dynamic> surveyData = {
        'question': survey.question.replaceAll('\n', ''),
        'answers': sanitizedAnswers,
        'created_at': now,
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

      debugPrint("[surveys] upserting: ${survey.question} → ${survey.answers}");
      try {
        await supabase
            .from('surveys')
            .upsert(surveyData, onConflict: onConflict);
        uploadedCount++;
        debugPrint("[surveys] upsert OK: ${survey.question}");
      } catch (e) {
        debugPrint("[surveys] upsert FAILED: ${survey.question} — $e");
        skippedCount++;
      }
    }

    debugPrint("[surveys] upload complete — uploaded=$uploadedCount, skipped=$skippedCount");
  } catch (error) {
    debugPrint("[surveys] upload ERROR: $error");
  }
}
