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

Future<int> codingMinutesPerYear() async {
  int hoursPerDay = 1;

  if (FFAppState().surveys.length > 4 &&
      FFAppState().surveys[4].answers.isNotEmpty) {
    String duration = FFAppState().surveys[4].answers[0].toLowerCase();
    switch (duration) {
      case '<1 hour':
        hoursPerDay = 1;
        break;
      case '1–2 hours':
        hoursPerDay = 2;
        break;
      case '2–4 hours':
        hoursPerDay = 3;
        break;
      case '4–8 hours':
        hoursPerDay = 6;
        break;
      case '>8 hours':
        hoursPerDay = 8;
        break;
      default:
        hoursPerDay = 1;
    }
  }

  const int daysPerYear = 365;
  const int minutesPerHour = 60;
  return hoursPerDay * minutesPerHour * daysPerYear;
}