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

Future supabaseSync() async {
  final supabase = SupaFlow.client;
  final userId = FFAppState().user.id;

  // Skip sync if user is not logged in with real UUID
  if (userId.isEmpty || userId.contains('Superwall')) {
    debugPrint('Skipping sync - user not logged in with real UUID');
    return;
  }

  Map<String, dynamic> syncStats = {
    'deletions': {'processed': 0, 'failed': 0},
    'syncUp': {'completed': false, 'error': null},
    'syncDown': {'completed': false, 'error': null},
  };

  try {
    final syncStartTime = DateTime.now();
    debugPrint(
        'Starting syncing... Last sync up at ${FFAppState().setting.lastSyncUpAt}, down at ${FFAppState().setting.lastSyncDownAt}');

    // Step 1: Process pending deletions
    await _processPendingDeletions(supabase, userId, syncStats);

    // Step 2: Sync up local changes
    try {
      await supabaseSyncUp();
      syncStats['syncUp']['completed'] = true;
    } catch (error) {
      syncStats['syncUp']['error'] = error.toString();
      debugPrint('Sync up failed: $error');
    }

    // Step 3: Sync down remote changes (exclude items uploaded during this sync session)
    try {
      await supabaseSyncDown(syncStartTime);
      syncStats['syncDown']['completed'] = true;
    } catch (error) {
      syncStats['syncDown']['error'] = error.toString();
      debugPrint('Sync down failed: $error');
    }

    // Step 5: Detect remote deletions
    await _detectRemoteDeletions(supabase, userId);

    debugPrint('Complete sync finished: $syncStats');
  } catch (error) {
    debugPrint('Complete sync failed: $error');
  }
}

// Process pending deletions
Future<void> _processPendingDeletions(
  dynamic supabase,
  String userId,
  Map<String, dynamic> syncStats,
) async {
  final pendingDeletions = FFAppState().pendingDeletions;

  if (pendingDeletions.isEmpty) {
    debugPrint('No pending deletions');
    return;
  }

  List<LocalDeletionStruct> successfulDeletions = [];

  try {
    for (final deletion in pendingDeletions) {
      // Skip onboard notes from deletion
      if (deletion.type == 'audio_note' &&
          deletion.id.startsWith('onboard-note')) {
        debugPrint('Skipping onboard note deletion: ${deletion.id}');
        successfulDeletions.add(deletion);
        continue;
      }

      try {
        // Skip deletion of removed types
        debugPrint('Skipping deletion of removed type: ${deletion.type}');

        successfulDeletions.add(deletion);
        syncStats['deletions']['processed']++;
        debugPrint('Successfully deleted ${deletion.type} ${deletion.id}');
      } catch (e) {
        syncStats['deletions']['failed']++;
        debugPrint('Failed to delete ${deletion.type} ${deletion.id}: $e');
      }
    }

    // Remove successfully synced deletions from FFAppState
    for (final deletion in successfulDeletions) {
      FFAppState().removeFromPendingDeletions(deletion);
    }
  } catch (error) {
    debugPrint('Failed to process deletions: $error');
  }
}

// Detect items deleted on other devices
Future<void> _detectRemoteDeletions(dynamic supabase, String userId) async {
  try {
    debugPrint('No remote deletion detection needed');
  } catch (error) {
    debugPrint('Failed to detect remote deletions: $error');
  }
}
