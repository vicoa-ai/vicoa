import { expect, test } from 'vitest';
import { extractMessageOptions, formatDiffLines } from '@/components/ui/message-markdown-utils';

test('merges verbose diff while preserving context lines', () => {
  const input = [
    "  import 'dart:convert';",
    "- import 'dart:math' as math;",
    "- ",
    "- import 'package:flutter/material.dart';",
    "- import 'package:google_fonts/google_fonts.dart';",
    "- import 'package:intl/intl.dart';",
    "- import 'package:timeago/timeago.dart' as timeago;",
    "- import 'lat_lng.dart';",
    "- import 'place.dart';",
    "- import 'uploaded_file.dart';",
    "- import '/backend/schema/structs/index.dart';",
    "- import '/backend/supabase/supabase.dart';",
    "- import '/auth/supabase_auth/auth_util.dart';",
    "+ import 'dart:io';",
    "+ import 'dart:math' as math;",
    "+ ",
    "+ import 'package:flutter/material.dart';",
    "+ import 'package:google_fonts/google_fonts.dart';",
    "+ import 'package:intl/intl.dart';",
    "+ import 'package:timeago/timeago.dart' as timeago;",
    "+ import 'lat_lng.dart';",
    "+ import 'place.dart';",
    "+ import 'uploaded_file.dart';",
    "+ import '/backend/schema/structs/index.dart';",
    "+ import '/backend/supabase/supabase.dart';",
    "+ import '/auth/supabase_auth/auth_util.dart';",
    "+ import 'flutter_flow_util.dart';",
  ].join('\n');

  const output = formatDiffLines(input, true, { compactContext: false }).map((line) => line.content);

  expect(output).toEqual([
    "  import 'dart:convert';",
    "+ import 'dart:io';",
    "  import 'dart:math' as math;",
    '  ',
    "  import 'package:flutter/material.dart';",
    "  import 'package:google_fonts/google_fonts.dart';",
    "  import 'package:intl/intl.dart';",
    "  import 'package:timeago/timeago.dart' as timeago;",
    "  import 'lat_lng.dart';",
    "  import 'place.dart';",
    "  import 'uploaded_file.dart';",
    "  import '/backend/schema/structs/index.dart';",
    "  import '/backend/supabase/supabase.dart';",
    "  import '/auth/supabase_auth/auth_util.dart';",
    "+ import 'flutter_flow_util.dart';",
  ]);
});

test('extracts bracket-delimited options from message content', () => {
  const input = [
    'Pick one:',
    '[OPTIONS]',
    '1. Keep current branch',
    '2. Create a new worktree',
    '[/OPTIONS]',
  ].join('\n');

  const output = extractMessageOptions(input);

  expect(output.content).toBe('Pick one:');
  expect(output.options).toEqual(['Keep current branch', 'Create a new worktree']);
});

test('extracts slash-delimited options from message content', () => {
  const input = [
    'Need a choice',
    'options/',
    '1. Approve',
    '2. Reject',
    '\\options',
  ].join('\n');

  const output = extractMessageOptions(input);

  expect(output.content).toBe('Need a choice');
  expect(output.options).toEqual(['Approve', 'Reject']);
});
