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

import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:intl/intl.dart';

Future saveAndShareMarkdownFile(String content) async {
  // Add your function code here!
  try {
    final now = DateTime.now();
    final formattedDate = DateFormat('yyyy-MM-dd_HH-mm').format(now);

    // Get the temporary directory
    final directory = await getTemporaryDirectory();

    // Create a file path with timestamp
    final fileName = 'vicoa_chat_$formattedDate.md';
    final filePath = '${directory.path}/$fileName';

    // Write content to the file
    final file = File(filePath);
    await file.writeAsString(content);

    // Share the file
    await SharePlus.instance.share(
      ShareParams(
        files: [
          XFile(
            filePath,
            mimeType: 'text/markdown',
            name: fileName,
          )
        ],
        subject: fileName,
        sharePositionOrigin: Rect.largest,
      ),
    );
  } catch (e) {
    debugPrint('Error saving and sharing markdown file: $e');
  }
}
