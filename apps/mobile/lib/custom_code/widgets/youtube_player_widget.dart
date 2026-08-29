// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/l10n/app_localizations.dart';
import 'index.dart'; // Imports other custom widgets
import '/custom_code/actions/index.dart'; // Imports custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom widget code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:youtube_player_flutter/youtube_player_flutter.dart';

class YoutubePlayerWidget extends StatefulWidget {
  const YoutubePlayerWidget({
    super.key,
    this.width,
    this.height,
    this.videoUrl,
    this.autoPlay = false,
    this.mute = false,
    this.showControls = true,
  });

  final double? width;
  final double? height;
  final String? videoUrl;
  final bool autoPlay;
  final bool mute;
  final bool showControls;

  @override
  State<YoutubePlayerWidget> createState() => _YoutubePlayerWidgetState();
}

class _YoutubePlayerWidgetState extends State<YoutubePlayerWidget> {
  late YoutubePlayerController _controller;
  bool _isReady = false;

  @override
  void initState() {
    super.initState();
    if (widget.videoUrl != null) {
      final videoId = YoutubePlayer.convertUrlToId(widget.videoUrl!);
      if (videoId != null) {
        _controller = YoutubePlayerController(
          initialVideoId: videoId,
          flags: YoutubePlayerFlags(
            autoPlay: widget.autoPlay,
            mute: widget.mute,
            hideControls: !widget.showControls,
          ),
        );
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.videoUrl == null) {
      return Container(
        width: widget.width,
        height: widget.height,
        color: Colors.black,
        child: Center(
          child: Text(
            AppLocalizations.of(context).youtubeXNoVideoUrl,
            style: const TextStyle(color: Colors.white),
          ),
        ),
      );
    }

    final videoId = YoutubePlayer.convertUrlToId(widget.videoUrl!);
    if (videoId == null) {
      return Container(
        width: widget.width,
        height: widget.height,
        color: Colors.black,
        child: Center(
          child: Text(
            AppLocalizations.of(context).youtubeXInvalidUrl,
            style: const TextStyle(color: Colors.white),
          ),
        ),
      );
    }

    return YoutubePlayer(
      controller: _controller,
      width: widget.width,
      showVideoProgressIndicator: true,
      progressIndicatorColor: FlutterFlowTheme.of(context).primary,
      progressColors: ProgressBarColors(
        playedColor: FlutterFlowTheme.of(context).primary,
        handleColor: FlutterFlowTheme.of(context).secondary,
      ),
      onReady: () {
        setState(() {
          _isReady = true;
        });
      },
    );
  }
}
