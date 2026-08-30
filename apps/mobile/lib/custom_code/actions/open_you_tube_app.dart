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

// Set your action name, define your arguments and return parameter,
// and then add the boilerplate code using the green button on the right!
import 'package:url_launcher/url_launcher.dart';

Future<void> openYouTubeApp(String videoUrl) async {
  final uri = Uri.parse(videoUrl);
  String? videoId;

  // Extract video ID from different YouTube URL formats
  if (uri.host.contains('youtube.com') ||
      uri.host.contains('www.youtube.com')) {
    if (uri.path.contains('/watch')) {
      videoId = uri.queryParameters['v'];
    } else if (uri.path.contains('/shorts/')) {
      videoId = uri.pathSegments.length >= 2 ? uri.pathSegments[1] : null;
    } else if (uri.path.contains('/embed/')) {
      videoId = uri.pathSegments.length >= 2 ? uri.pathSegments[1] : null;
    }
  } else if (uri.host.contains('youtu.be')) {
    videoId = uri.pathSegments.isNotEmpty ? uri.pathSegments.first : null;
  } else if (uri.host.contains('m.youtube.com')) {
    if (uri.path.contains('/watch')) {
      videoId = uri.queryParameters['v'];
    }
  }

  if (videoId == null || videoId.isEmpty) {
    print("Invalid YouTube URL or Video ID not found.");
    return;
  }

  // Clean video ID (remove any extra parameters)
  videoId = videoId.split('&').first;

  // Try multiple YouTube app URL schemes
  final List<String> appSchemes = [
    'youtube://watch?v=$videoId',
    'vnd.youtube://$videoId',
    'youtube://$videoId',
  ];

  bool appLaunched = false;

  // Try each app scheme
  for (String scheme in appSchemes) {
    final Uri appUri = Uri.parse(scheme);
    if (await canLaunchUrl(appUri)) {
      try {
        await launchUrl(appUri, mode: LaunchMode.externalApplication);
        appLaunched = true;
        break;
      } catch (e) {
        print('Failed to launch with scheme: $scheme');
        continue;
      }
    }
  }

  // Fallback to web if app couldn't be launched
  if (!appLaunched) {
    final Uri webUri = Uri.parse('https://www.youtube.com/watch?v=$videoId');
    try {
      await launchUrl(webUri, mode: LaunchMode.externalApplication);
    } catch (e) {
      print('Failed to launch YouTube URL: $e');
    }
  }
}
