// Automatic FlutterFlow imports
import '/backend/supabase/supabase.dart';
import 'index.dart';
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

Future<dynamic> apiCreateAgentInstance(
  String agentId,
  String prompt,
  String? name,
  String? worktreeName,
) async {
  try {
    final body = {
      'prompt': prompt,
      if (name != null) 'name': name,
      if (worktreeName != null) 'worktree_name': worktreeName,
    };
    
    final result = await vicoaApiRequest('post', '/api/v1/user-agents/$agentId/instances', body);
    return result;
  } catch (e) {
    debugPrint('Error creating agent instance: $e');
    return null;
  }
}